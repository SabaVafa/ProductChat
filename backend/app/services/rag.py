from app.services.mistral import MistralService
from app.services.retrieval import RetrievalService
from app.services.settings_service import SettingsService
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

# Short connective phrases that signal a typed message is a follow-up refining
# the previous turn (so it should keep context) rather than a new topic.
_FOLLOWUP_PREFIXES = (
    "and ", "also ", "or ", "what about", "how about", "cheaper", "cheapest",
    "under ", "over ", "with ", "without ", "in ", "same ", "any ", "more ", "less ",
)


def _looks_like_followup(message: str) -> bool:
    """True if a typed message reads like a refinement of the previous turn.

    Detected by connective wording only — NOT by length, so a short but
    self-contained new topic like "show me mailboxes" is treated as a new
    subject, not a refinement of whatever came before.
    """
    m = (message or "").strip().lower()
    if not m:
        return False
    return m.startswith(_FOLLOWUP_PREFIXES)


def _active_subject(prior_user: list) -> str:
    """The most recent user turn that established a subject (i.e. not itself a
    follow-up), so refinements/follow-ups anchor on the CURRENT topic rather
    than the conversation's first message."""
    for turn in reversed(prior_user):
        if turn and not _looks_like_followup(turn):
            return turn
    return prior_user[-1] if prior_user else ""


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

            # Build a retrieval query that carries recent context, so short
            # follow-ups ("and with LED?", "cheaper?") still search sensibly.
            # The generation step gets the full turn history separately; here we
            # only need enough context for the vector search to land in the
            # right neighbourhood, so the last couple of user turns is plenty.
            history_list = history or []
            prior_user = [
                (h.get("content") or "").strip()
                for h in history_list
                if h.get("role") == "user" and (h.get("content") or "").strip()
            ]
            # Build the retrieval query so it lands on the RIGHT products:
            #  - a refinement chip ("With LED") must keep the current subject, so
            #    anchor on the first + most recent user turns;
            #  - a short typed follow-up ("cheaper?", "in anthracite?") keeps the
            #    immediately preceding turn for context;
            #  - any other typed question is a NEW topic and drives retrieval on
            #    its own, so asking about a different product switches context.
            if is_refinement and prior_user:
                # A tapped refine chip ("With LED") keeps the CURRENT subject —
                # anchor on the most recent topic turn.
                subject = _active_subject(prior_user)
                retrieval_query = (subject + " " + message).strip() if subject else message.strip()
            else:
                # Every typed question searches for exactly what was typed — no
                # bleed from earlier turns. This is the precise, stateless search
                # behaviour; a new question always switches topic cleanly.
                retrieval_query = message.strip()

            # Retrieve relevant products (vector search in Qdrant)
            retrieved_products = self.retrieval.retrieve(
                query=retrieval_query,
                limit=num_retrieved,
                score_threshold=similarity_threshold
            )

            add_step(
                "2_vector_search",
                embedding_model=self.retrieval.embeddings.model,
                retrieval_query=retrieval_query,
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
            formatted_products = []
            if "recommendations" in response:
                for rec in response["recommendations"]:
                    # Find full product details
                    product_details = next(
                        (p for p in retrieved_products if p.get("product_id") == rec.get("product_id")),
                        None
                    )
                    if product_details:
                        formatted_products.append({
                            "id": product_details.get("product_id"),
                            "name": product_details.get("name"),
                            "price": product_details.get("price"),
                            "image": product_details.get("image_url"),
                            "url": product_details.get("product_url"),
                            "reason": rec.get("reason", ""),
                            "score": rec.get("score", product_details.get("score", 0.0))
                        })

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
