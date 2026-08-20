from app.services.qdrant_service import QdrantService
from app.services.embeddings import EmbeddingsService
from app.services.settings_service import SettingsService
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# --- Bestseller tie-break tuning --------------------------------------------
# Popularity must never override relevance, so we only let it reorder results
# that are ALREADY comparably relevant. Scores within TIER_WIDTH of each other
# form one "relevance tier"; within a tier, a better bestseller band wins, then
# raw score. A stronger semantic match in a higher tier is never displaced.
# TIER_WIDTH is deliberately small (cosine scores of good matches sit ~0.7–0.85
# and adjacent results differ by ~0.005–0.02) so only genuine near-ties reorder.
_TIER_WIDTH = 0.02


def _bestseller_band(rank: Optional[int]) -> int:
    """Coarse popularity band (lower = more popular; 4 = unranked)."""
    if rank is None:
        return 4
    if rank <= 5:
        return 0
    if rank <= 15:
        return 1
    if rank <= 50:
        return 2
    return 3


def _apply_bestseller_tiebreak(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Relevance-gated, banded tie-break. Stable within ties.

    Relevance tiers are measured as distance BELOW the top score (in _TIER_WIDTH
    bands), not against a fixed absolute grid — so eligibility to be reordered
    depends on how close two results actually are, not on where their scores
    happen to fall relative to a global 0/0.02/0.04 lattice (M-4). Within a tier,
    a better bestseller band wins, then the higher score; a clearly-more-relevant
    result (a lower tier number) is never displaced by popularity.
    """
    if len(products) < 2:
        return products

    top = max((p.get("score") or 0.0) for p in products)

    def sort_key(p: Dict[str, Any]):
        score = p.get("score") or 0.0
        tier = round((top - score) / _TIER_WIDTH)   # 0 = within a band of the top
        return (tier, _bestseller_band(p.get("bestseller_rank")), -score)

    return sorted(products, key=sort_key)


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
    
    @staticmethod
    def _format(results) -> List[Dict[str, Any]]:
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
                "bestseller_rank": payload.get("bestseller_rank"),
                "score": result.get("score", 0.0)
            })
        return products

    def retrieve(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
        categories: Optional[List[str]] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve products by semantic similarity, with structured filters
        (category / price) applied by the vector DB. If the filtered search
        returns too few results (e.g. the parsed category was off), fall back to
        an unfiltered semantic search so the user still gets useful matches.
        """
        try:
            query_vector = self.embeddings.embed_text(query)

            results = self.qdrant.search(
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                filter_conditions=filters,
                categories=categories,
                price_min=price_min,
                price_max=price_max,
            )
            products = self._format(results)

            # A category/price filter that yields almost nothing is worse than
            # plain semantic search — retry unfiltered as a safety net.
            if (categories or price_min is not None or price_max is not None) and len(products) < 3:
                logger.info("Filtered search returned %d; falling back to unfiltered", len(products))
                results = self.qdrant.search(
                    query_vector=query_vector,
                    limit=limit,
                    score_threshold=score_threshold,
                    filter_conditions=filters,
                )
                products = self._format(results)

            # Relevance-gated bestseller tie-break: reorders only comparably
            # relevant results, so category/price routing above is preserved.
            return _apply_bestseller_tiebreak(products)

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
