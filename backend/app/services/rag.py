from app.services.mistral import MistralService
from app.services.retrieval import RetrievalService, _apply_bestseller_tiebreak
from app.services.settings_service import SettingsService
from app.services.query_understanding import understand_query
from app.models.product import Product
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


def _catalog_categories(db: Session) -> List[str]:
    """Distinct non-empty catalog categories, for the query-understanding step."""
    rows = db.query(Product.category).distinct().filter(
        Product.category.isnot(None), Product.category != ""
    ).all()
    return [r[0] for r in rows if r[0]]


def _order_recommendations(
    recommendations: List[Dict[str, Any]],
    retrieved_products: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Turn the LLM's chosen recommendations into API product cards.

    The LLM selects which products to show (relevance/intent) and writes the
    reasons, but it never sees bestseller_rank — so on its own the popularity
    tie-break never reaches the user. To fix that (finding C-1) we re-apply the
    SAME relevance-gated banded tie-break as the retrieval layer, but to the
    LLM's SELECTED set. Tiering uses the objective retrieval score (not the
    LLM's self-reported score), so a clearly-more-relevant pick is never demoted
    by popularity — popularity only reorders comparably-relevant picks.
    """
    by_id = {p.get("product_id"): p for p in retrieved_products}
    picked: List[Dict[str, Any]] = []
    for rec in recommendations:
        details = by_id.get(rec.get("product_id"))
        if not details:
            continue  # skip hallucinated ids not in the retrieved set
        picked.append({
            # tie-break inputs: the OBJECTIVE retrieval score + rank
            "score": details.get("score", 0.0) or 0.0,
            "bestseller_rank": details.get("bestseller_rank"),
            "_card": {
                "id": details.get("product_id"),
                "name": details.get("name"),
                "price": details.get("price"),
                "image": details.get("image_url"),
                "url": details.get("product_url"),
                "reason": rec.get("reason", ""),
                "score": rec.get("score", details.get("score", 0.0)),
            },
        })

    # Reuse the retrieval layer's relevance-gated banded tie-break verbatim, so
    # the chat path and /test/retrieval order identically (single source of truth).
    return [it["_card"] for it in _apply_bestseller_tiebreak(picked)]


class RAGService:
    def __init__(self, db: Session):
        self.db = db
        self.retrieval = RetrievalService(db)
        self.settings_service = SettingsService(db)
    
    # Attribute values worth offering as one-tap refinements when they show up
    # in the retrieved set. Kept as a template (no LLM call) so it's free.
    REFINE_KEYWORDS = [
        "LED", "engraving", "Gravur", "facial recognition", "fingerprint",
        "wireless", "Funkklingel", "anthracite", "Anthrazit", "stainless steel",
        "exchangeable", "newspaper", "illuminated",
    ]

    def _build_refine_suggestions(self, retrieved_products: List[Dict[str, Any]]) -> List[str]:
        """Derive cheap refine chips from the facets of the retrieved products."""
        if not retrieved_products:
            return []

        categories = []
        for p in retrieved_products:
            c = p.get("category")
            if c and c not in categories:
                categories.append(c)

        prices = [p.get("price") for p in retrieved_products if isinstance(p.get("price"), (int, float))]

        # Which keyword facets actually appear in the retrieved set.
        blob = " ".join(
            f"{p.get('name','')} {p.get('description','')} {p.get('attributes','')}"
            for p in retrieved_products
        ).lower()
        present = []
        for kw in self.REFINE_KEYWORDS:
            if kw.lower() in blob and kw.lower() not in [x.lower() for x in present]:
                present.append(kw)

        suggestions: List[str] = []
        if len(categories) > 1:
            suggestions.append(f"Only show {categories[0]}")
        for kw in present[:2]:
            suggestions.append(f"With {kw}")
        if len(prices) >= 3:
            srt = sorted(prices)
            mid = srt[len(srt) // 2]
            hi = srt[-1]
            # Round to a friendly threshold based on the price band.
            if mid >= 100:
                threshold = int(round(mid / 50.0) * 50)
            elif mid >= 20:
                threshold = int(round(mid / 10.0) * 10)
            else:
                threshold = int(round(mid / 5.0) * 5)
            # Only offer a price chip when it's a meaningful filter: a sane
            # minimum and genuinely below the most expensive item (so it narrows
            # the set). This avoids degenerate chips like "Under €3".
            if threshold >= 10 and threshold < hi:
                suggestions.append(f"Under €{threshold}")

        return suggestions[:4]

    def chat(self, message: str, history: Optional[List[Dict[str, Any]]] = None, is_refinement: bool = False, include_debug: bool = True) -> Dict[str, Any]:
        """Process a chat message using RAG.

        When `include_debug` is True, the response carries a `debug` object
        tracing every step of the pipeline: retrieval settings, the query
        embedding, the products returned from the vector search (with scores),
        the exact prompt sent to the LLM, and its raw response.
        """
        # Step trace, returned to the client so the whole RAG flow is visible.
        debug: Dict[str, Any] = {
            "query": message,
            "steps": [],
            "embedding_model": self.retrieval.embeddings.model,
        }

        def add_step(name: str, **info):
            debug["steps"].append({"step": name, **info})

        try:
            # Guardrail (runs BEFORE retrieval/LLM): a prompt-injection or
            # system-prompt/model-disclosure attempt is refused here, so a
            # jailbroken prompt never reaches generation.
            from app.services.guardrails import blocked_reason, BLOCKED_REPLY
            reason = blocked_reason(message)
            if reason:
                add_step("0_guardrail_blocked", reason=reason)
                try:
                    from app.services.ops import record_operation
                    record_operation(self.db, "chat", "blocked", {"reason": reason})
                except Exception:
                    pass
                result = {"answer": BLOCKED_REPLY, "products": [], "follow_up_question": ""}
                if include_debug:
                    result["debug"] = debug
                return result

            # Get settings
            settings_dict = self.settings_service.get_all_settings()

            # Get retrieval settings
            retrieval_settings = settings_dict.get("retrieval", {})
            num_retrieved = retrieval_settings.get("num_retrieved", 10)
            similarity_threshold = retrieval_settings.get("similarity_threshold", 0.0)
            enable_filters = retrieval_settings.get("enable_metadata_filters", False)

            # Get output settings
            output_settings = settings_dict.get("output", {})

            add_step(
                "1_retrieval_config",
                num_retrieved=num_retrieved,
                similarity_threshold=similarity_threshold,
                enable_metadata_filters=enable_filters,
            )

            history_list = history or []
            prior_user = [
                (h.get("content") or "").strip()
                for h in history_list
                if h.get("role") == "user" and (h.get("content") or "").strip()
            ]

            # Text to understand: a typed question stands alone (precise, stateless);
            # a refinement chip carries recent context so "With LED" is parsed
            # against the current subject.
            if is_refinement and prior_user:
                understand_text = " ".join(prior_user[-2:] + [message]).strip()
            else:
                understand_text = message.strip()

            # LLM query understanding -> structured query (primary categories,
            # clean search phrase, price bounds). This replaces the old keyword
            # heuristics; the categories/price are applied as Qdrant filters.
            mistral_settings = settings_dict.get("mistral", {})
            uq_service = MistralService(api_key=mistral_settings.get("api_key"))
            parsed = understand_query(uq_service, _catalog_categories(self.db), understand_text)

            add_step(
                "1b_query_understanding",
                understand_text=understand_text,
                categories=parsed["categories"],
                search_text=parsed["search_text"],
                price_min=parsed["price_min"],
                price_max=parsed["price_max"],
            )

            # Filtered semantic retrieval — category + price enforced by the
            # vector DB (with an unfiltered fallback if the filter is too tight).
            retrieved_products = self.retrieval.retrieve(
                query=parsed["search_text"],
                limit=num_retrieved,
                score_threshold=similarity_threshold,
                categories=parsed["categories"] or None,
                price_min=parsed["price_min"],
                price_max=parsed["price_max"],
            )

            add_step(
                "2_vector_search",
                embedding_model=self.retrieval.embeddings.model,
                retrieval_query=parsed["search_text"],
                filtered_categories=parsed["categories"],
                retrieved_count=len(retrieved_products),
                results=[
                    {
                        "product_id": p.get("product_id"),
                        "name": p.get("name"),
                        "category": p.get("category"),
                        "score": round(p.get("score", 0.0), 4),
                    }
                    for p in retrieved_products
                ],
            )

            if not retrieved_products:
                result = {
                    "answer": "I couldn't find any products matching your request. Please try different keywords or browse our catalog.",
                    "products": [],
                }
                if include_debug:
                    result["debug"] = debug
                return result

            # Get Mistral settings
            mistral_settings = settings_dict.get("mistral", {})
            api_key = mistral_settings.get("api_key")
            model = mistral_settings.get("model", "mistral-large-latest")
            temperature = mistral_settings.get("temperature", 0.7)
            max_tokens = mistral_settings.get("max_tokens", 1000)

            # Initialize Mistral service
            mistral = MistralService(api_key=api_key)
            mistral.set_config(api_key, model, temperature, max_tokens)

            # Generate recommendation (LLM re-ranks + explains)
            llm_debug: Dict[str, Any] = {}
            # Give the model prior turns ONLY for a refine chip (so it can keep
            # the subject). A typed question is answered statelessly — precise,
            # no drift to an earlier topic.
            llm_history = history_list if is_refinement else []
            response = mistral.generate_recommendation(
                query=message,
                retrieved_products=retrieved_products,
                config=output_settings,
                debug=llm_debug,
                history=llm_history,
                is_refinement=is_refinement
            )

            add_step(
                "3_llm_prompt",
                model=llm_debug.get("model"),
                temperature=llm_debug.get("temperature"),
                max_tokens=llm_debug.get("max_tokens"),
                system_prompt=llm_debug.get("system_prompt"),
                user_message=llm_debug.get("user_message"),
            )
            add_step(
                "4_llm_response",
                raw_response=llm_debug.get("raw_response"),
                token_usage=llm_debug.get("token_usage"),
                dropped_hallucinated_ids=llm_debug.get("dropped_hallucinated_ids", []),
                error=llm_debug.get("error"),
            )

            # Format response for API
            formatted_products = _order_recommendations(
                response.get("recommendations", []), retrieved_products
            )

            add_step(
                "5_final_products",
                recommended_count=len(formatted_products),
                product_ids=[p["id"] for p in formatted_products],
            )

            result = {
                "answer": response.get("answer", ""),
                "products": formatted_products,
                "follow_up_question": response.get("follow_up_question", ""),
                "refine_suggestions": self._build_refine_suggestions(retrieved_products),
            }
            if include_debug:
                result["debug"] = debug
            return result

        except Exception as e:
            logger.error(f"RAG chat error: {e}")
            add_step("error", message=str(e))
            result = {
                "answer": "I apologize, but I encountered an error processing your request. Please try again.",
                "products": []
            }
            if include_debug:
                result["debug"] = debug
            return result
