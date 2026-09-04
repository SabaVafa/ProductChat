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
import re

logger = logging.getLogger(__name__)

# Small, fast, cheap model for parsing — not the answer-generation model.
# Provider-aware: the actual id comes from `mistral.small_model` (Mistral small
# or the Groq small model); this constant is only the Mistral fallback.
UNDERSTANDING_MODEL = "mistral-small-latest"


def _expand_category_families(cats: List[str], all_categories: List[str]) -> List[str]:
    """Widen a family-head category to its sub-category siblings.

    The shop splits a product family across sibling categories (e.g. an intercom
    lives in "Video Sprechanlagen"/"Audio Sprechanlagen"/"Sprechanlagen Sets",
    while the bare "Sprechanlagen" category holds almost nothing). If the model
    picks only the head, the category filter matches ~nothing and retrieval falls
    back to an UNFILTERED search that drifts to unrelated products (a
    "Sprechanlage" query returning security cameras). So when a chosen category
    appears as a whole word inside other catalog categories, include those too.

    Asymmetric on purpose: "Sprechanlagen" pulls in "Video Sprechanlagen", but a
    specific "Video Sprechanlagen" pick is NOT widened back to the whole family —
    an explicit sub-type stays narrow.
    """
    if not cats:
        return cats
    out = list(cats)
    for head in cats:
        pat = re.compile(r"\b" + re.escape(head) + r"\b", re.IGNORECASE)
        for cat in all_categories:
            if cat not in out and pat.search(cat):
                out.append(cat)
    return out


def understand_query(
    mistral: MistralService,
    categories: List[str],
    text: str,
    context: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return {categories, search_text, price_min, price_max}.

    `context` is the recent prior USER turns (oldest first), used to resolve a
    follow-up that only modifies an earlier request — e.g. after "I need a
    mailbox" the shopper types "without gravur" or "cheaper". Such a fragment
    has no product type of its own, so the product type is inherited from the
    conversation; a message that names a new product type switches to it.
    """
    fallback = {"categories": [], "search_text": text, "price_min": None, "price_max": None,
                "gravur": None}
    if not text or not text.strip():
        return fallback

    cat_list = ", ".join(f'"{c}"' for c in categories)
    system = (
        "You convert a shopper's request into a structured product query for a store that "
        "sells doorbells, mailboxes, intercoms, package boxes, house numbers, cameras, lights "
        "and accessories.\n\n"
        "Respond with ONLY a JSON object of this exact shape:\n"
        '{"categories": [string], "search_text": string, "price_min": number|null, "price_max": number|null, "gravur": "ohne"|null}\n\n'
        "Rules:\n"
        "0. \"gravur\": set to \"ohne\" ONLY when the shopper wants a MAILBOX/Briefkasten "
        "explicitly WITHOUT engraving — 'ohne Gravur', 'without engraving/gravur', 'no "
        "engraving', 'nicht graviert', 'mit austauschbarem Namensschild statt Gravur'. "
        "Otherwise null. (Do NOT set it for 'mit Gravur', for a plain 'Briefkasten', or "
        "for any non-mailbox product.)\n"
        "1. \"categories\": pick ALL entries from the AVAILABLE CATEGORIES below that match the "
        "shopper's PRIMARY product type. If that type is split across several sub-categories "
        "(e.g. an intercom spans 'Video Sprechanlagen', 'Audio Sprechanlagen', 'Sprechanlagen "
        "Sets'; a mailbox spans 'Einfamilien Briefkasten', 'Mehrfamilien Briefkästen'), include "
        "ALL of those sub-categories — do NOT pick only the bare head category, which may be "
        "nearly empty. Narrow to one sub-category only when the shopper is specific (e.g. 'Video-"
        "Sprechanlage'). If the request combines a product with a feature (e.g. 'mailbox with a "
        "doorbell'), choose the categories of the PRODUCT (mailbox), NOT the feature. Use [] only "
        "if the product type is genuinely unclear.\n"
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
        "- 'intercom' -> Sprechanlagen categories; 'camera' -> 'IP Kameras' / 'Sicherheitstechnik'.\n"
    )
    prior = [c.strip() for c in (context or []) if c and c.strip()]
    if prior:
        system += (
            "\nFOLLOW-UP HANDLING: The CURRENT MESSAGE may refine the recent conversation. "
            "If it only adds or removes a feature, colour, material, or price — or says "
            "'without/ohne X', 'cheaper', 'the second one' — with NO product type of its own, "
            "KEEP the product type from the recent conversation and fold the modifier into "
            "search_text (e.g. after 'mailbox', 'without gravur' -> categories stay the mailbox "
            "category, search_text 'Briefkasten ohne Gravur'). If the CURRENT MESSAGE names a "
            "NEW product type, switch to it and ignore the earlier topic.\n"
        )
    system += f"\nAVAILABLE CATEGORIES: [{cat_list}]"

    if prior:
        user_content = (
            "RECENT CONVERSATION (oldest to newest):\n"
            + "\n".join(f"- {c}" for c in prior[-3:])
            + f"\n\nCURRENT MESSAGE: {text}"
        )
    else:
        user_content = text
    try:
        content = mistral.chat_content(
            messages=[ChatMessage("system", system), ChatMessage("user", user_content)],
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"},
            model=getattr(mistral, "small_model", UNDERSTANDING_MODEL),
        )
        data = json.loads(content)
    except Exception as e:
        logger.warning(f"Query understanding failed, falling back to plain search: {e}")
        return fallback

    valid = set(categories)
    cats = [c for c in (data.get("categories") or []) if c in valid]
    cats = _expand_category_families(cats, categories)

    def _num(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    gravur = data.get("gravur")
    gravur = "ohne" if (isinstance(gravur, str) and gravur.lower() == "ohne") else None

    return {
        "categories": cats,
        "search_text": (data.get("search_text") or text).strip() or text,
        "price_min": _num(data.get("price_min")),
        "price_max": _num(data.get("price_max")),
        "gravur": gravur,
    }
