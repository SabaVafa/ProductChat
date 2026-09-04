from app.services.mistral import MistralService
from app.services.retrieval import RetrievalService, _apply_bestseller_tiebreak
from app.services.settings_service import SettingsService
from app.services.query_understanding import understand_query
from app.models.product import Product
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
import logging
import re

logger = logging.getLogger(__name__)

# Words after "ohne/without/kein" that are not product features.
_NEG_STOP = {"die", "der", "das", "eine", "einen", "einem", "the", "a", "an", "und", "and"}
_NEG_RE = re.compile(r"\b(?:ohne|without|kein|keine|no)\s+([a-zA-ZäöüÄÖÜß]{3,})", re.IGNORECASE)


def _apply_negation_filter(products: List[Dict[str, Any]], message: str) -> List[Dict[str, Any]]:
    """Drop products that HEADLINE a feature the user asked to exclude.

    Vector search can't do negation — "Briefkasten ohne Gravur" retrieves lots of
    "mit Lasergravur" products because the token overlap is huge. When the message
    says "ohne X" / "without X", drop products whose NAME contains X — unless the
    name marks *that feature* optional ("Gravur optional" stays — it can be ordered
    without). The "optional" must qualify the negated term itself: a product named
    "... mit Gravur | Zeitungsfach optional ..." has Gravur INCLUDED (only the
    newspaper slot is optional), so it must still be dropped.
    """
    terms = [m.group(1).lower() for m in _NEG_RE.finditer(message or "")]
    terms = [t for t in terms if t not in _NEG_STOP]
    if not terms:
        return products

    def _term_is_optional(name: str, t: str) -> bool:
        # True only when "optional"/"ohne" qualifies THIS term with no other
        # word between them (e.g. "gravur optional", "optional gravur", "ohne
        # gravur") — not a stray "optional" elsewhere in the name.
        et = re.escape(t)
        return re.search(rf"{et}\W{{1,4}}optional|optional\W{{1,4}}{et}|ohne\W{{1,4}}{et}", name) is not None

    def keep(p: Dict[str, Any]) -> bool:
        name = (p.get("name") or "").lower()
        for t in terms:
            if t in name and not _term_is_optional(name, t):
                return False
        return True

    filtered = [p for p in products if keep(p)]
    if len(filtered) != len(products):
        logger.info("Negation filter %s: %d -> %d products", terms, len(products), len(filtered))
    # Return the filtered set even if it's small/empty: showing a product the
    # user explicitly excluded ("ohne Gravur" → a "mit Lasergravur" item) is worse
    # than showing fewer. An empty result then routes to the German
    # no-results + offer-to-broaden path rather than to wrong recommendations —
    # this is what stops the drift-to-nameplates screenshot from recurring.
    return filtered


def _catalog_categories(db: Session) -> List[str]:
    """Distinct non-empty catalog categories, for the query-understanding step."""
    rows = db.query(Product.category).distinct().filter(
        Product.category.isnot(None), Product.category != ""
    ).all()
    return [r[0] for r in rows if r[0]]


def _product_to_dict(p, score: float = 1.0) -> Dict[str, Any]:
    """Map a Product row to the same shape retrieval._format returns, so a
    launch-context product can join the candidate set (grounding + citation)."""
    return {
        "product_id": p.product_id, "name": p.name, "description": p.description,
        "category": p.category, "brand": p.brand, "price": p.price,
        "image_url": p.image_url, "product_url": p.product_url,
        "attributes": p.attributes, "bestseller_rank": getattr(p, "bestseller_rank", None),
        "score": score,
    }


def _anchor_note(name: str, product_id: str) -> str:
    """Prefix that tells the model which product 'this/that' refers to."""
    return (f"[Kontext: Der Kunde betrachtet gerade das Produkt \"{name}\" "
            f"(product_id {product_id}). Beziehe Formulierungen wie \"dieses Produkt\", "
            f"\"das\", \"die Farben\" auf dieses Produkt. Seine Felder stehen in der Liste.] ")


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
        attrs = details.get("attributes")
        rank = details.get("bestseller_rank")
        picked.append({
            # tie-break inputs: the OBJECTIVE retrieval score + rank
            "score": details.get("score", 0.0) or 0.0,
            "bestseller_rank": rank,
            "_card": {
                "id": details.get("product_id"),
                "name": details.get("name"),
                "price": details.get("price"),
                "image": details.get("image_url"),
                "url": details.get("product_url"),
                "reason": rec.get("reason", ""),
                "score": rec.get("score", details.get("score", 0.0)),
                # honest "Beliebt" pill: only genuine shop bestsellers (top band)
                "popular": rank is not None and rank <= 15,
                # variant products (Farbe/Größe option lists) → price shown as "ab"
                "has_variants": isinstance(attrs, dict) and any(
                    isinstance(v, list) and len(v) > 1 for v in attrs.values()
                ),
            },
        })

    # Reuse the retrieval layer's relevance-gated banded tie-break verbatim, so
    # the chat path and /test/retrieval order identically (single source of truth).
    return [it["_card"] for it in _apply_bestseller_tiebreak(picked)]


# Shown when the LLM is unavailable (e.g. Mistral rate-limited) but retrieval —
# which only needs the embeddings endpoint — still works.
DEGRADED_ANSWER = ("Unser KI-Assistent ist gerade stark ausgelastet – hier sind schon "
                   "einmal passende Produkte aus unserem Sortiment. Für eine "
                   "ausführliche Beratung frag bitte gleich noch einmal.")


def _degraded_cards(retrieved_products: List[Dict[str, Any]], limit: int = 4) -> List[Dict[str, Any]]:
    """Build product cards straight from the retrieved set (no LLM selection).

    Used as an insurance fallback: if answer generation fails, the shopper still
    sees relevant products (retrieval already ran) instead of an error. Cards use
    the same shape as _order_recommendations, minus the per-product reason.
    """
    cards: List[Dict[str, Any]] = []
    for p in retrieved_products[:limit]:
        attrs = p.get("attributes")
        rank = p.get("bestseller_rank")
        cards.append({
            "id": p.get("product_id"),
            "name": p.get("name"),
            "price": p.get("price"),
            "image": p.get("image_url"),
            "url": p.get("product_url"),
            "reason": "",
            "score": p.get("score", 0.0),
            "popular": rank is not None and rank <= 15,
            "has_variants": isinstance(attrs, dict) and any(
                isinstance(v, list) and len(v) > 1 for v in attrs.values()
            ),
        })
    return cards


class RAGService:
    def __init__(self, db: Session):
        self.db = db
        self.retrieval = RetrievalService(db)
        self.settings_service = SettingsService(db)
    
    # Attribute facets worth offering as one-tap refinements when they show up
    # in the retrieved set. Kept as a template (no LLM call) so it's free.
    # (match_term, german_chip_label): match terms cover DE+EN product text,
    # but the chip the customer sees is ALWAYS German (design-audit finding:
    # English chips flipped the whole conversation into English).
    REFINE_KEYWORDS = [
        ("LED", "LED"), ("Gravur", "Gravur"), ("engraving", "Gravur"),
        ("fingerprint", "Fingerprint"), ("Funkklingel", "Funk"), ("wireless", "Funk"),
        ("Anthrazit", "Anthrazit"), ("anthracite", "Anthrazit"),
        ("Edelstahl", "Edelstahl"), ("stainless steel", "Edelstahl"),
        ("Zeitungsfach", "Zeitungsfach"), ("newspaper", "Zeitungsfach"),
        ("beleuchtet", "beleuchtet"), ("illuminated", "beleuchtet"),
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
        present: List[str] = []   # german chip labels, deduped
        for term, label in self.REFINE_KEYWORDS:
            if term.lower() in blob and label not in present:
                present.append(label)

        suggestions: List[str] = []
        if len(categories) > 1:
            suggestions.append(f"Nur {categories[0]}")
        for label in present[:2]:
            suggestions.append(f"Mit {label}")
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
                suggestions.append(f"Unter {threshold} €")

        return suggestions[:4]

    def chat(self, message: str, history: Optional[List[Dict[str, Any]]] = None, is_refinement: bool = False, include_debug: bool = True, product_id: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
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

            # Launch context: the embedding page (e.g. the JTL widget on a product
            # page) may pass the product the user is currently viewing so answers
            # are anchored to it without the user restating what they're looking at.
            viewed = None
            if product_id:
                viewed = self.db.query(Product).filter(
                    Product.product_id == str(product_id)).first()
            effective_message = (message or "").strip()
            if not effective_message and viewed:
                effective_message = ("Bitte gib mir einen kurzen Überblick zu diesem "
                                     "Produkt und passende Alternativen.")
            add_step("0b_launch_context", product_id=product_id, category=category,
                     viewed=(viewed.product_id if viewed else None))

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

            # Text to understand is always the CURRENT message; recent prior
            # user turns go in as context so a follow-up that only modifies an
            # earlier request ("without gravur", "cheaper", "the second one")
            # inherits its product type — whether it was typed or a refine chip.
            # A message that names a new product type still switches topic.
            understand_text = effective_message
            understand_context = prior_user

            # LLM query understanding -> structured query (primary categories,
            # clean search phrase, price bounds). This replaces the old keyword
            # heuristics; the categories/price are applied as Qdrant filters.
            mistral_settings = settings_dict.get("mistral", {})
            uq_service = MistralService(api_key=mistral_settings.get("api_key"))
            parsed = understand_query(
                uq_service, _catalog_categories(self.db), understand_text,
                context=understand_context,
            )

            # "ohne Gravur" is answered from the shop's curated category
            # membership (a Qdrant payload tag), NOT by guessing from names.
            # That tag is the only ohne-gravur category and it means mailboxes,
            # so it replaces the category filter and constrains the whole result.
            gravur = parsed.get("gravur")
            gravur_filter = {"gravur": "ohne"} if gravur == "ohne" else None
            categories_filter = (parsed["categories"] or ([category] if category else None))
            if gravur_filter:
                categories_filter = None

            add_step(
                "1b_query_understanding",
                understand_text=understand_text,
                categories=parsed["categories"],
                search_text=parsed["search_text"],
                price_min=parsed["price_min"],
                price_max=parsed["price_max"],
                gravur=gravur,
            )

            # Filtered semantic retrieval — category/price/gravur enforced by the
            # vector DB (with an unfiltered fallback if category/price is too tight;
            # the gravur filter is always kept, so "mit Gravur" can't leak back).
            retrieved_products = self.retrieval.retrieve(
                query=parsed["search_text"] or effective_message,
                limit=num_retrieved,
                score_threshold=similarity_threshold,
                filters=gravur_filter,
                categories=categories_filter,
                price_min=parsed["price_min"],
                price_max=parsed["price_max"],
            )

            # Negation guard for OTHER "ohne X" / "without X" features (vector
            # search can't negate). Gravur is handled authoritatively above by the
            # curated category tag, so skip the name heuristic there — a tagged
            # "ohne Gravur" box may still say "Gravur optional" in its name.
            if not gravur_filter:
                retrieved_products = _apply_negation_filter(retrieved_products, effective_message)

            # Ensure the currently-viewed product is in the candidate set, so the
            # model can answer about it (grounded by rule 12) and cite it.
            if viewed and not any(p.get("product_id") == viewed.product_id for p in retrieved_products):
                top = max((p.get("score") or 0.0) for p in retrieved_products) if retrieved_products else 1.0
                retrieved_products.append(_product_to_dict(viewed, score=top))

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
                # German dead-end WITH recovery chips (top categories), so the
                # customer always has a way forward (design-audit finding).
                from sqlalchemy import func
                top_cats = [
                    c for (c, _) in self.db.query(Product.category, func.count(Product.id))
                    .filter(Product.category.isnot(None), Product.category != "")
                    .group_by(Product.category)
                    .order_by(func.count(Product.id).desc()).limit(3).all()
                ]
                result = {
                    "answer": ("Dazu habe ich leider nichts Passendes gefunden. "
                               "Magst du es mit anderen Begriffen versuchen – z. B. "
                               "„Briefkasten mit Klingel“ oder „Video-Sprechanlage“?"),
                    "products": [],
                    "refine_suggestions": [f"Nur {c}" for c in top_cats],
                }
                if include_debug:
                    result["debug"] = debug
                return result

            # Get Mistral settings
            mistral_settings = settings_dict.get("mistral", {})
            api_key = mistral_settings.get("api_key")
            model = mistral_settings.get("model", "mistral-medium-latest")
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
            # Anchor the turn to the viewed product so "this", "das", "the colours"
            # resolve without the user restating it.
            llm_query = effective_message
            if viewed:
                llm_query = _anchor_note(viewed.name, viewed.product_id) + effective_message
            response = mistral.generate_recommendation(
                query=llm_query,
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

            # Insurance fallback: generation failed (e.g. Mistral chat models
            # rate-limited) BUT retrieval succeeded (embeddings still work). Show
            # the retrieved products with a short notice instead of an error — a
            # degraded-but-useful result. A genuine "no products" answer (no error,
            # LLM chose nothing) is left untouched.
            if llm_debug.get("error") and retrieved_products:
                formatted_products = _degraded_cards(retrieved_products, limit=4)
                answer = DEGRADED_ANSWER
                follow_up = ""
                add_step("5_degraded_fallback", reason=llm_debug.get("error"),
                         product_count=len(formatted_products))
            else:
                formatted_products = _order_recommendations(
                    response.get("recommendations", []), retrieved_products
                )
                answer = response.get("answer", "")
                follow_up = response.get("follow_up_question", "")

            add_step(
                "5_final_products",
                recommended_count=len(formatted_products),
                product_ids=[p["id"] for p in formatted_products],
            )

            result = {
                "answer": answer,
                "products": formatted_products,
                "follow_up_question": follow_up,
                "refine_suggestions": self._build_refine_suggestions(retrieved_products),
            }
            if include_debug:
                result["debug"] = debug
            return result

        except Exception as e:
            logger.error(f"RAG chat error: {e}")
            add_step("error", message=str(e))
            result = {
                "answer": "Entschuldigung, da ist etwas schiefgelaufen. Bitte versuche es gleich noch einmal.",
                "products": []
            }
            if include_debug:
                result["debug"] = debug
            return result
