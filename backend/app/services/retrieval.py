from app.services.qdrant_service import QdrantService
from app.services.embeddings import EmbeddingsService
from app.services.settings_service import SettingsService
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def _fold(s: str) -> str:
    """Lowercase + umlaut-fold so 'Briefkästen' matches 'briefkast'."""
    s = (s or "").lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        s = s.replace(a, b)
    return s


# When a query names a product type, prefer products whose CATEGORY matches.
# This stops pure semantic search from returning "Paketbox mit Briefkasten"
# (a package box) for "mailbox" just because it contains the word Briefkasten.
# (query trigger terms, category-name substrings to prefer) — all umlaut-folded.
_CATEGORY_HINTS = [
    (("mailbox", "briefkast", "letterbox", "letter box", "postbox"), ("briefkast",)),
    (("paketbox", "package box", "parcel", "paketkasten"), ("paketbox",)),
    (("doorbell", "turklingel", "funkklingel", "door bell", "klingel"),
     ("turklingel", "funkklingel")),
    (("intercom", "sprechanlage", "tursprech"), ("sprechanlage",)),
    (("house number", "hausnummer"), ("hausnummer",)),
    (("camera", "kamera", "surveillance", "cctv"), ("kamera",)),
    (("mulltonne", "waste bin", "trash", "bin box", "dustbin"), ("mulltonne",)),
    (("gong", "chime"), ("gong",)),
    (("outdoor light", "leuchte", "lamp", "lighting"), ("leuchte", "garten")),
]


def _preferred_categories(query: str):
    q = _fold(query)
    subs = set()
    for triggers, cats in _CATEGORY_HINTS:
        if any(t in q for t in triggers):
            subs.update(cats)
    return subs


class RetrievalService:
    def __init__(self, db: Optional[Session] = None):
        self.qdrant = QdrantService()
        self.embeddings = EmbeddingsService()

        # Embeddings must use the Mistral API key configured via the Admin
        # UI (stored encrypted in the DB), not just the process env var,
        # since that's how users actually set their key.
        if db is not None:
            api_key = SettingsService(db).get_category_settings("mistral").get("api_key")
            if api_key:
                self.embeddings.set_api_key(api_key)
    
    def retrieve(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant products for a query.

        When the query names a product type (e.g. "mailbox"), over-fetch a larger
        candidate pool and re-rank so products in the matching CATEGORY come
        first — otherwise semantically-close but wrong-type products (a package
        box that mentions "Briefkasten") can crowd out the real ones.
        """
        try:
            # Generate query embedding
            query_vector = self.embeddings.embed_text(query)

            preferred = _preferred_categories(query)
            # Over-fetch when we intend to re-rank, so category matches that the
            # pure vector ranked lower still make it into the candidate pool.
            fetch = max(limit * 6, 60) if preferred else limit

            results = self.qdrant.search(
                query_vector=query_vector,
                limit=fetch,
                score_threshold=score_threshold,
                filter_conditions=filters
            )

            # Format results
            products = []
            for result in results:
                payload = result.get("payload", {})
                products.append({
                    "product_id": payload.get("product_id"),
                    "name": payload.get("name"),
                    "description": payload.get("description"),
                    "category": payload.get("category"),
                    "brand": payload.get("brand"),
                    "price": payload.get("price"),
                    "image_url": payload.get("image_url"),
                    "product_url": payload.get("product_url"),
                    "attributes": payload.get("attributes"),
                    "score": result.get("score", 0.0)
                })

            if preferred:
                def is_pref(p):
                    cat = _fold(p.get("category"))
                    return any(sub in cat for sub in preferred)
                # Stable partition: category matches first (keeping vector order
                # within each group), then the rest as fallback.
                matches = [p for p in products if is_pref(p)]
                rest = [p for p in products if not is_pref(p)]
                products = (matches + rest)[:limit]
            else:
                products = products[:limit]

            return products
            
        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            return []
    
    def retrieve_with_metadata_filters(
        self,
        query: str,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Retrieve with metadata filters."""
        filters = {}
        
        if category:
            filters["category"] = category
        if brand:
            filters["brand"] = brand
        
        # Price filtering is done after retrieval since Qdrant doesn't support range filters well
        results = self.retrieve(query, limit * 2, score_threshold, filters)
        
        # Apply price filters
        if min_price is not None or max_price is not None:
            filtered = []
            for product in results:
                price = product.get("price")
                if price is not None:
                    if min_price is not None and price < min_price:
                        continue
                    if max_price is not None and price > max_price:
                        continue
                    filtered.append(product)
            results = filtered[:limit]
        
        return results
