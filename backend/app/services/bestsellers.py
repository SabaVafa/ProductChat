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

Safety properties (see the audit findings they address):
  * A transient fetch failure marks the run *partial* and we then clear NOTHING,
    so a flaky category page can never erase real ranks (H-1).
  * Stale ranks are cleared in Qdrant FIRST; the DB rank is nulled only if that
    succeeded, so a failed clear is retried next run instead of lingering (H-2).
  * robots.txt is honored — disallowed categories are skipped (M-5).
"""

from sqlalchemy.orm import Session
from app.models.product import Product
from app.services.indexing import product_id_to_point_id
from app.services.qdrant_service import QdrantService
from app.services.scraper import BASE_URL, USER_AGENT, REQUEST_TIMEOUT, REQUEST_DELAY
from typing import Dict, Any, List, Set, Optional, Iterable
from collections import defaultdict
from datetime import datetime, timezone
from urllib.robotparser import RobotFileParser
import logging
import threading
import re
import time

import requests

logger = logging.getLogger(__name__)

# In-process status for the (background) capture run, surfaced to the Admin UI
# and pollable while a run is in flight. Same pattern as scraper.SYNC_STATE.
CAPTURE_STATE: Dict[str, Any] = {
    "status": "idle",          # idle | running | completed | partial | error
    "categories_total": 0,
    "categories_done": 0,
    "products_ranked": 0,
    "fetch_errors": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
}
# Held for the WHOLE run (non-blocking acquire), so a manual trigger and the
# nightly scheduler can never launch two overlapping crawls (M-1).
_run_lock = threading.Lock()
# Guards mutations of CAPTURE_STATE.
_state_lock = threading.Lock()

BESTSELLER_SORT = "Sortierung=11"   # the "Bestseller" option in the sort dropdown
PAGE_PARAM = "seite"                # JTL pagination param (lowercase; ?seite=N)
MAX_PAGES_PER_CATEGORY = 40         # safety cap (largest category ~ a few pages)
FETCH_RETRIES = 3                   # transient (5xx / timeout) retries per URL
LOW_COVERAGE_PCT = 30              # warn if fewer than this % of the catalog ranks

# Homepage nav also links CMS/util pages; skip the obvious ones to save fetches.
# Anything not skipped that isn't a real category just yields no products.
_NON_CATEGORY_SLUGS = {
    "impressum", "datenschutz", "kontakt", "warenkorb", "agb", "widerrufsrecht",
    "widerruf", "zahlung-und-versand", "metzler-garantieerklaerung", "newsletter",
    "login", "registrieren", "merkzettel", "blog", "ueber-uns", "sitemap",
    "versandinformationen", "batteriegesetz", "streitschlichtung",
}

# Anchor to internal slug URLs, in document order. Deliberately broad (audit
# finding: the old lowercase/single-segment/absolute-only pattern missed real
# JTL categories like /Paketboxen, /Muelltonnenbox and nested ones, costing
# bestseller-rank coverage): case-preserving, optional second path segment,
# and root-relative hrefs are all accepted.
_SLUG_RE = re.compile(
    r'href="(?:' + re.escape(BASE_URL) + r')?/([A-Za-z0-9][A-Za-z0-9\-]*(?:/[A-Za-z0-9][A-Za-z0-9\-]*)?)"'
)

# First path segments that are assets/system paths, never categories.
_ASSET_SEGMENTS = {"media", "includes", "templates", "gfx", "bilder", "export", "static"}


def _stale_ranks_to_clear(
    previously_ranked_ids: Iterable[str], ranked_ids: Set[str], partial: bool
) -> Set[str]:
    """Product ids whose bestseller_rank should be cleared this run.

    On a *partial* run (some category page failed to fetch) we clear NOTHING:
    a transient failure must never be mistaken for "this product is no longer a
    bestseller", which would erase real ranks until the next clean run (H-1).
    """
    if partial:
        return set()
    return set(previously_ranked_ids) - set(ranked_ids)


class BestsellerService:
    def __init__(self, db: Session):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._fetch_errors = 0          # transient (5xx/timeout) failures this run
        self._robots: Optional[RobotFileParser] = None

    # ---- HTTP -----------------------------------------------------------
    def _get(self, url: str) -> Optional[str]:
        """Fetch a page. Returns the body, or None on failure.

        A None return distinguishes a *failed* fetch from an empty page. Only
        transient failures (5xx / timeout / connection) are retried and counted
        in ``_fetch_errors`` (which drives the partial-run guard); a 4xx is a
        definitive "not here" and is neither retried nor counted.
        """
        last_exc = None
        for attempt in range(FETCH_RETRIES):
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                if resp.status_code >= 400:
                    logger.warning("Bestseller GET %s -> %s", url, resp.status_code)
                    return None  # client error: definitive, not a transient failure
                return resp.text
            except Exception as e:
                last_exc = e
                time.sleep(0.5 * (2 ** attempt))
        logger.warning("Bestseller GET failed after %d tries for %s: %s",
                       FETCH_RETRIES, url, last_exc)
        self._fetch_errors += 1
        return None

    # ---- robots.txt (M-5) ----------------------------------------------
    def _load_robots(self) -> None:
        """Best-effort load of robots.txt so we can honor Disallow rules."""
        rp = RobotFileParser()
        try:
            resp = self.session.get(f"{BASE_URL}/robots.txt", timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                self._robots = rp
                return
        except Exception as e:
            logger.warning("Could not load robots.txt (%s); proceeding without it", e)
        self._robots = None  # unreachable -> don't block (can't determine)

    def _robots_allows(self, url: str) -> bool:
        if self._robots is None:
            return True
        try:
            return self._robots.can_fetch(USER_AGENT, url)
        except Exception:
            return True

    # ---- Discovery ------------------------------------------------------
    def discover_category_urls(self, catalog_urls: Set[str]) -> List[str]:
        """Category listing URLs from the homepage nav.

        A homepage slug is a category candidate unless it's a known product (it's
        in our catalog) or an obvious CMS/util page. Order is preserved and
        deduped so the crawl is deterministic.
        """
        html = self._get(f"{BASE_URL}/") or ""
        seen, cats = set(), []
        for slug in _SLUG_RE.findall(html):
            key = slug.lower()          # dedupe case variants (/Paketboxen vs /paketboxen)
            if key in seen:
                continue
            seen.add(key)
            first_seg = key.split("/", 1)[0]
            if first_seg in _NON_CATEGORY_SLUGS or first_seg in _ASSET_SEGMENTS:
                continue
            full = f"{BASE_URL}/{slug}"
            if full in catalog_urls:
                continue
            cats.append(full)
        return cats

    # ---- Listing parsing ------------------------------------------------
    def _product_order(self, html: Optional[str], catalog_urls: Set[str]) -> List[str]:
        """Catalog product URLs in the page's DOM order (deduped, first-seen)."""
        order, seen = [], set()
        for slug in _SLUG_RE.findall(html or ""):
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
            if html is None:
                # Fetch failed (transient failures already counted in _get); stop
                # this category. The partial-run guard protects against erasure.
                break
            order = self._product_order(html, catalog_urls)
            # A page that adds nothing new means we've run past the last page
            # (JTL echoes the last/first page for out-of-range ?seite values).
            new = [u for u in order if u not in positions]
            if not new:
                break
            for u in new:
                pos += 1
                positions[u] = pos
            if page == MAX_PAGES_PER_CATEGORY:
                logger.warning("Bestseller: %s hit the %d-page cap without "
                               "terminating; ranks beyond it are dropped",
                               cat_url, MAX_PAGES_PER_CATEGORY)
        return positions

    # ---- Capture --------------------------------------------------------
    def capture(self) -> Dict[str, Any]:
        # A single run at a time across BOTH the endpoint and the scheduler (M-1).
        if not _run_lock.acquire(blocking=False):
            logger.info("Bestseller capture already running; skipping this trigger")
            from app.services.ops import record_operation
            record_operation(self.db, "bestsellers", "skipped",
                             {"reason": "another capture already running"})
            return {"success": False, "message": "Bestseller capture already in progress"}
        try:
            with _state_lock:
                CAPTURE_STATE.update({
                    "status": "running", "error": None,
                    "categories_total": 0, "categories_done": 0, "products_ranked": 0,
                    "fetch_errors": 0,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "finished_at": None,
                })
            try:
                return self._capture()
            except Exception as e:
                logger.error(f"Bestseller capture error: {e}")
                with _state_lock:
                    CAPTURE_STATE.update({
                        "status": "error", "error": str(e),
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                    })
                from app.services.ops import record_operation
                record_operation(self.db, "bestsellers", "error", {"error": str(e)})
                return {"success": False, "error": str(e)}
        finally:
            _run_lock.release()

    def _capture(self) -> Dict[str, Any]:
        self._fetch_errors = 0
        self._load_robots()

        catalog = {
            p.product_url: p
            for p in self.db.query(Product).filter(Product.product_url.isnot(None)).all()
        }
        catalog_urls = set(catalog)
        if not catalog_urls:
            with _state_lock:
                CAPTURE_STATE.update({"status": "completed",
                                      "finished_at": datetime.now(timezone.utc).isoformat()})
            return {"success": False, "message": "No products with URLs to rank"}

        discovered = self.discover_category_urls(catalog_urls)
        cats = [c for c in discovered if self._robots_allows(f"{c}?{BESTSELLER_SORT}")]
        skipped_by_robots = len(discovered) - len(cats)
        if skipped_by_robots:
            logger.info("Bestseller: %d categories skipped per robots.txt", skipped_by_robots)
        with _state_lock:
            CAPTURE_STATE["categories_total"] = len(cats)
        logger.info("Bestseller capture: %d category pages to crawl", len(cats))

        best: Dict[str, int] = {}   # product_url -> best (min) position seen
        categories_used = 0
        for cat_url in cats:
            positions = self._crawl_category(cat_url, catalog_urls)
            with _state_lock:
                CAPTURE_STATE["categories_done"] += 1
            if positions:
                categories_used += 1
            for url, position in positions.items():
                if url not in best or position < best[url]:
                    best[url] = position

        previously_ranked = {
            p.product_id: p for p in self.db.query(Product).filter(
                Product.bestseller_rank.isnot(None)).all()
        }

        # Apply the freshly-captured ranks (in memory; committed below).
        ranked_ids: Set[str] = set()
        by_rank: Dict[int, List[str]] = defaultdict(list)  # rank -> [point_id]
        for url, rank in best.items():
            p = catalog.get(url)
            if not p:
                continue
            p.bestseller_rank = rank
            ranked_ids.add(p.product_id)
            by_rank[rank].append(product_id_to_point_id(p.product_id))

        # A transient fetch failure => partial run => clear nothing (H-1).
        partial = self._fetch_errors > 0
        to_clear = _stale_ranks_to_clear(previously_ranked.keys(), ranked_ids, partial)

        qs = QdrantService()
        push_ok = True
        # Patch fresh ranks onto Qdrant (grouped by value; no re-embed).
        for rank, point_ids in by_rank.items():
            if not qs.set_payload_for_points(point_ids, {"bestseller_rank": rank}):
                push_ok = False

        # Clear stale ranks in Qdrant FIRST; only null the DB rank for products
        # whose Qdrant clear succeeded, so a failed clear is retried next run
        # rather than lingering forever (H-2).
        cleared = 0
        if to_clear:
            clear_pids = [product_id_to_point_id(pid) for pid in to_clear]
            if qs.set_payload_for_points(clear_pids, {"bestseller_rank": None}):
                for pid in to_clear:
                    previously_ranked[pid].bestseller_rank = None
                cleared = len(to_clear)
            else:
                push_ok = False
                logger.warning("Bestseller: clearing %d stale ranks failed in Qdrant; "
                               "leaving DB ranks for retry next run", len(to_clear))

        self.db.commit()

        total = len(catalog)
        coverage_pct = round(100 * len(ranked_ids) / max(total, 1))
        if coverage_pct < LOW_COVERAGE_PCT:
            logger.warning("Bestseller: only %d%% of the catalog ranked (%d/%d) — "
                           "possible category-discovery gap", coverage_pct, len(ranked_ids), total)

        ok = not partial and push_ok
        result = {
            "success": True,
            "partial": not ok,
            "fetch_errors": self._fetch_errors,
            "qdrant_push_ok": push_ok,
            "robots_skipped": skipped_by_robots,
            "categories_crawled": len(cats),
            "categories_with_products": categories_used,
            "catalog_products": total,
            "products_ranked": len(ranked_ids),
            "coverage_pct": coverage_pct,
            "ranks_cleared": cleared,
            "top_rank": min(best.values()) if best else None,
        }
        with _state_lock:
            CAPTURE_STATE.update({
                "status": "completed" if ok else "partial",
                "products_ranked": len(ranked_ids),
                "fetch_errors": self._fetch_errors,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
        from app.services.ops import record_operation
        record_operation(self.db, "bestsellers", "completed" if ok else "partial", result)
        logger.info("Bestseller capture done: %s", result)
        return result


def get_capture_status() -> Dict[str, Any]:
    with _state_lock:
        return dict(CAPTURE_STATE)
