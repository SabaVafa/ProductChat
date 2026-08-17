"""LLM query understanding: turn a shopper's message into a structured query.

Replaces hand-written keyword rules. Given the REAL catalog categories, a small
model maps the request to the matching categories (of the PRIMARY product type),
a clean semantic search phrase, and any price bounds — which the retrieval layer
applies as Qdrant filters. Best-effort: on any failure it falls back to plain
semantic search on the raw text, so it can never do worse than before.
"""

from typing import Any, Dict, List, Optional
from app.services.mistral import MistralService, ChatMessage
import json
import logging

logger = logging.getLogger(__name__)

# Small, fast, cheap model for parsing — not the answer-generation model.
UNDERSTANDING_MODEL = "mistral-small-latest"


def understand_query(
    mistral: MistralService,
    categories: List[str],
    text: str,
) -> Dict[str, Any]:
    """Return {categories, search_text, price_min, price_max}."""
    fallback = {"categories": [], "search_text": text, "price_min": None, "price_max": None}
    if not text or not text.strip():
        return fallback

    cat_list = ", ".join(f'"{c}"' for c in categories)
    system = (
        "You convert a shopper's request into a structured product query for a store that "
        "sells doorbells, mailboxes, intercoms, package boxes, house numbers, cameras, lights "
        "and accessories.\n\n"
        "Respond with ONLY a JSON object of this exact shape:\n"
        '{"categories": [string], "search_text": string, "price_min": number|null, "price_max": number|null}\n\n'
        "Rules:\n"
        "1. \"categories\": pick the entries from the AVAILABLE CATEGORIES below that match the "
        "shopper's PRIMARY product type. Choose the category that NAMES the product itself, the "
        "most specific one. If the request combines a product with a feature (e.g. 'mailbox with "
        "a doorbell'), choose the categories of the PRODUCT (mailbox), NOT the feature. Use [] "
        "only if the product type is genuinely unclear.\n"
        "2. \"search_text\": a concise search phrase capturing the full need including features, "
        "colours and materials (used for semantic search).\n"
        "3. price_min/price_max: EUR numbers if the shopper stated a budget (e.g. 'under 200' -> "
        "price_max 200), else null.\n\n"
        "Disambiguation examples (map to the real categories in the list):\n"
        "- 'house number' / 'Hausnummer' -> Hausnummern categories (NOT nameplate/sign categories "
        "like 'Namens- & Hinweisschilder').\n"
        "- 'mailbox' / 'Briefkasten' -> Briefkasten categories (NOT 'Paketboxen').\n"
        "- 'doorbell' -> Türklingeln / Funkklingeln (NOT 'Klingeltaster & Lichtschalter', which are "
        "spare buttons).\n"
        "- 'intercom' -> Sprechanlagen categories; 'camera' -> 'IP Kameras' / 'Sicherheitstechnik'.\n\n"
        f"AVAILABLE CATEGORIES: [{cat_list}]"
    )
    try:
        content = mistral.chat_content(
            messages=[ChatMessage("system", system), ChatMessage("user", text)],
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"},
            model=UNDERSTANDING_MODEL,
        )
        data = json.loads(content)
    except Exception as e:
        logger.warning(f"Query understanding failed, falling back to plain search: {e}")
        return fallback

    valid = set(categories)
    cats = [c for c in (data.get("categories") or []) if c in valid]

    def _num(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "categories": cats,
        "search_text": (data.get("search_text") or text).strip() or text,
        "price_min": _num(data.get("price_min")),
        "price_max": _num(data.get("price_max")),
    }
