"""Capture the shop's per-category "Bestseller" ordering as a rank signal.

The JTL shop exposes a Bestseller sort on every category listing page
(``?Sortierung=11``) — it reflects real paid orders over the last 90 days and
refreshes nightly. We crawl each category in that order, record each catalog
product's 1-based position, and keep its *best* (lowest) position across all the
categories it appears in. That rank is stored on the product and pushed into the
Qdrant payload, where retrieval uses it as a relevance-gated tie-break (never a
hard sort — see retrieval.py).

Design notes / why it's robust:
  * The sitemap is products-only, so category URLs are discovered from the shop
    nav on the homepage. Non-category (CMS) pages simply yield no ranked
    products and cost one wasted fetch.
  * Product tiles are identified by matching anchors against our OWN catalog
    ``product_url`` set. The JTL variation-option shells (price 0: "Schriftart
    7", "Unterputz", ...) that pollute the global /Bestseller page are not in
    our catalog, so they can never match — no junk-filtering logic needed.
  * Noise (a footer "recently viewed" slider) can only ever assign a *worse*
    position than the real grid placement, and we keep the min across
    categories, so a genuine top-N product always gets its true low rank.
  * Rank is NOT part of the embedding text or the content hash, so refreshing it
    never triggers a re-embed; the new value is patched straight onto the
    existing Qdrant points via set_payload.
"""

from sqlalchemy.orm import Session
from app.models.product import Product
from app.services.indexing import product_id_to_point_id
from app.services.qdrant_service import QdrantService
from app.services.scraper import BASE_URL, USER_AGENT, REQUEST_TIMEOUT, REQUEST_DELAY
from typing import Dict, Any, List, Set, Optional
from collections import defaultdict
from datetime import datetime, timezone
import logging
import threading
import re
import time

import requests

logger = logging.getLogger(__name__)

# In-process status for the (background) capture run, surfaced to the Admin UI
# and pollable while a run is in flight. Same pattern as scraper.SYNC_STATE.
CAPTURE_STATE: Dict[str, Any] = {
    "status": "idle",          # idle | running | completed | error
    "categories_total": 0,
    "categories_done": 0,
    "products_ranked": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
}
_capture_lock = threading.Lock()

BESTSELLER_SORT = "Sortierung=11"   # the "Bestseller" option in the sort dropdown
PAGE_PARAM = "seite"                # JTL pagination param (lowercase; ?seite=N)
MAX_PAGES_PER_CATEGORY = 40         # safety cap (largest category ~ a few pages)

# Homepage nav also links CMS/util pages; skip the obvious ones to save fetches.
# Anything not skipped that isn't a real category just yields no products.
_NON_CATEGORY_SLUGS = {
    "impressum", "datenschutz", "kontakt", "warenkorb", "agb", "widerrufsrecht",
    "widerruf", "zahlung-und-versand", "metzler-garantieerklaerung", "newsletter",
    "login", "registrieren", "merkzettel", "blog", "ueber-uns", "sitemap",
    "versandinformationen", "batteriegesetz", "streitschlichtung",
}

# Anchor to any internal single-segment slug URL, in document order.
_SLUG_RE = re.compile(r'href="' + re.escape(BASE_URL) + r'/([a-z0-9][a-z0-9\-]+)"')


class BestsellerService:
    def __init__(self, db: Session):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    # ---- HTTP -----------------------------------------------------------
    def _get(self, url: str) -> str:
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning(f"Bestseller GET failed for {url}: {e}")
            return ""

    # ---- Discovery ------------------------------------------------------
    def discover_category_urls(self, catalog_urls: Set[str]) -> List[str]:
        """Category listing URLs from the homepage nav.

        A homepage slug is a category candidate unless it's a known product (it's
        in our catalog) or an obvious CMS/util page. Order is preserved and
        deduped so the crawl is deterministic.
        """
        html = self._get(f"{BASE_URL}/")
        seen, cats = set(), []
        for slug in _SLUG_RE.findall(html):
            if slug in seen:
                continue
            seen.add(slug)
            full = f"{BASE_URL}/{slug}"
            if full in catalog_urls or slug in _NON_CATEGORY_SLUGS:
                continue
            cats.append(full)
        return cats

    # ---- Listing parsing ------------------------------------------------
    def _product_order(self, html: str, catalog_urls: Set[str]) -> List[str]:
        """Catalog product URLs in the page's DOM order (deduped, first-seen)."""
        order, seen = [], set()
        for slug in _SLUG_RE.findall(html):
            full = f"{BASE_URL}/{slug}"
            if full in catalog_urls and full not in seen:
                seen.add(full)
                order.append(full)
        return order

    def _crawl_category(self, cat_url: str, catalog_urls: Set[str]) -> Dict[str, int]:
        """Return {product_url: 1-based position} for one category (bestseller sort)."""
        positions: Dict[str, int] = {}
        pos = 0
        for page in range(1, MAX_PAGES_PER_CATEGORY + 1):
            sep = "&" if "?" in cat_url else "?"
            url = f"{cat_url}{sep}{BESTSELLER_SORT}"
            if page > 1:
                url += f"&{PAGE_PARAM}={page}"
            html = self._get(url)
            time.sleep(REQUEST_DELAY)
            order = self._product_order(html, catalog_urls)
            # A page that adds nothing new means we've run past the last page
            # (JTL echoes the last/first page for out-of-range ?seite values).
            new = [u for u in order if u not in positions]
            if not new:
                break
            for u in new:
                pos += 1
                positions[u] = pos
        return positions

    # ---- Capture --------------------------------------------------------
    def capture(self) -> Dict[str, Any]:
        with _capture_lock:
            CAPTURE_STATE.update({
                "status": "running", "error": None,
                "categories_total": 0, "categories_done": 0, "products_ranked": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
            })
        try:
            return self._capture()
        except Exception as e:
            logger.error(f"Bestseller capture error: {e}")
            with _capture_lock:
                CAPTURE_STATE.update({
                    "status": "error", "error": str(e),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                })
            from app.services.ops import record_operation
            record_operation(self.db, "bestsellers", "error", {"error": str(e)})
            return {"success": False, "error": str(e)}

    def _capture(self) -> Dict[str, Any]:
        catalog = {
            p.product_url: p
            for p in self.db.query(Product).filter(Product.product_url.isnot(None)).all()
        }
        catalog_urls = set(catalog)
        if not catalog_urls:
            CAPTURE_STATE.update({"status": "completed",
                                  "finished_at": datetime.now(timezone.utc).isoformat()})
            return {"success": False, "message": "No products with URLs to rank"}

        cats = self.discover_category_urls(catalog_urls)
        CAPTURE_STATE["categories_total"] = len(cats)
        logger.info("Bestseller capture: %d category pages to crawl", len(cats))

        best: Dict[str, int] = {}   # product_url -> best (min) position seen
        categories_used = 0
        for cat_url in cats:
            positions = self._crawl_category(cat_url, catalog_urls)
            CAPTURE_STATE["categories_done"] += 1
            if positions:
                categories_used += 1
            for url, position in positions.items():
                if url not in best or position < best[url]:
                    best[url] = position

        # Products that carried a rank before but don't now must be cleared too.
        previously_ranked = {
            p.product_id: p for p in self.db.query(Product).filter(
                Product.bestseller_rank.isnot(None)).all()
        }

        ranked_ids: Set[str] = set()
        by_rank: Dict[int, List[str]] = defaultdict(list)  # rank -> [point_id]
        for url, rank in best.items():
            p = catalog.get(url)
            if not p:
                continue
            p.bestseller_rank = rank
            ranked_ids.add(p.product_id)
            by_rank[rank].append(product_id_to_point_id(p.product_id))

        # Clear stale ranks in the DB.
        cleared_point_ids: List[str] = []
        for pid, p in previously_ranked.items():
            if pid not in ranked_ids:
                p.bestseller_rank = None
                cleared_point_ids.append(product_id_to_point_id(pid))

        self.db.commit()

        # Push to Qdrant payload without re-embedding (grouped by rank value so
        # it's a handful of calls, not one per product).
        qs = QdrantService()
        for rank, point_ids in by_rank.items():
            qs.set_payload_for_points(point_ids, {"bestseller_rank": rank})
        if cleared_point_ids:
            qs.set_payload_for_points(cleared_point_ids, {"bestseller_rank": None})

        result = {
            "success": True,
            "categories_crawled": len(cats),
            "categories_with_products": categories_used,
            "products_ranked": len(ranked_ids),
            "ranks_cleared": len(cleared_point_ids),
            "top_rank": min(best.values()) if best else None,
        }
        with _capture_lock:
            CAPTURE_STATE.update({
                "status": "completed",
                "products_ranked": len(ranked_ids),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
        from app.services.ops import record_operation
        record_operation(self.db, "bestsellers", "completed", result)
        logger.info("Bestseller capture done: %s", result)
        return result


def get_capture_status() -> Dict[str, Any]:
    return dict(CAPTURE_STATE)
