from app.services.qdrant_service import QdrantService
from app.services.embeddings import EmbeddingsService
from app.services.settings_service import SettingsService
from app.config import settings
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

# Max BM25-only products injected per query when hybrid search is on. Small, so a
# few exact-term matches surface without flooding the candidate set.
HYBRID_INJECT_MAX = 4


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
        self.db = db                      # kept for hybrid BM25 (catalog lookups)
        self.qdrant = QdrantService()
        self.embeddings = EmbeddingsService()

        # Embeddings API key resolution:
        # The process env var MISTRAL_API_KEY WINS when set — that's how a
        # deployment supplies it, and it must never be overridden by a DB value
        # that may be stale or encrypted with a different ENCRYPTION_KEY (e.g. a
        # baked/seeded DB), which would fail to decrypt and 401. When no env key
        # is set (local dev), fall back to the key configured via the Admin UI
        # (stored encrypted in the DB) — EmbeddingsService already defaults to
        # settings.MISTRAL_API_KEY, so we only reach for the DB key when empty.
        if db is not None and not (settings.MISTRAL_API_KEY or "").strip():
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
        hybrid: bool = False,
    ) -> List[Dict[str, Any]]:
        """Retrieve products by semantic similarity, with structured filters
        (category / price) applied by the vector DB. If the filtered search
        returns too few results (e.g. the parsed category was off), fall back to
        an unfiltered semantic search so the user still gets useful matches.

        When `hybrid` is set (the `enable_hybrid_search` setting), a lexical BM25
        pass over the same category scope INJECTS any strong exact-term matches
        the dense search missed (e.g. "Unterputz" mailboxes), fixing recall on
        precise tokens. It only ADDS candidates — dense order/scores are kept —
        so it can't regress the current semantic behaviour.
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

            if hybrid:
                products = self._inject_bm25(query, products, categories, price_min, price_max)

            # Relevance-gated bestseller tie-break: reorders only comparably
            # relevant results, so category/price routing above is preserved.
            return _apply_bestseller_tiebreak(products)

        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            return []

    def _inject_bm25(
        self,
        query: str,
        dense_products: List[Dict[str, Any]],
        categories: Optional[List[str]],
        price_min: Optional[float],
        price_max: Optional[float],
    ) -> List[Dict[str, Any]]:
        """Add strong BM25 exact-term matches the dense search missed.

        Recall booster: only ADDS candidates the dense list lacks (kept within the
        same category/price scope), scored as top-tier relevant since they are a
        strong literal match for the query. Never removes or reorders dense hits;
        any failure degrades silently to the dense-only result.
        """
        if self.db is None or not (query or "").strip():
            return dense_products
        try:
            from app.services.bm25_index import get_bm25_index
            from app.models.product import Product

            idx = get_bm25_index(self.db)
            allowed = set(categories) if categories else None
            hits = idx.search(query, top_n=12, allowed_categories=allowed)
            have = {p.get("product_id") for p in dense_products}
            inject_ids = [pid for pid, _ in hits if pid not in have][:HYBRID_INJECT_MAX]
            if not inject_ids:
                return dense_products

            rows = self.db.query(Product).filter(Product.product_id.in_(inject_ids)).all()
            by_id = {r.product_id: r for r in rows}
            # Score injected products BELOW the least-relevant dense hit, so they
            # sit in a lower relevance tier: purely additive (appended after the
            # dense results), never reordering the dense top-K or the bestseller
            # lead. The LLM still sees them and can pick them for an exact-term ask.
            if dense_products:
                inj_score = max(0.01, min((p.get("score") or 0.0) for p in dense_products) - 0.05)
            else:
                inj_score = 0.5
            extra: List[Dict[str, Any]] = []
            for pid in inject_ids:              # preserve BM25 rank order
                r = by_id.get(pid)
                if r is None:
                    continue
                if price_min is not None and (r.price is None or r.price < price_min):
                    continue
                if price_max is not None and (r.price is None or r.price > price_max):
                    continue
                extra.append({
                    "product_id": r.product_id, "name": r.name, "description": r.description,
                    "category": r.category, "brand": r.brand, "price": r.price,
                    "image_url": r.image_url, "product_url": r.product_url,
                    "attributes": r.attributes, "bestseller_rank": r.bestseller_rank,
                    "score": inj_score,
                })
            if extra:
                logger.info("Hybrid BM25 injected %d exact-term match(es): %s",
                            len(extra), [e["product_id"] for e in extra])
            return dense_products + extra
        except Exception as e:
            logger.warning("Hybrid BM25 injection skipped (%s)", e)
            return dense_products

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
