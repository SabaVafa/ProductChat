"""Capture the shop's "ohne Gravur" product membership as a retrieval filter.

Vector search cannot answer "Briefkasten ohne Gravur": the phrase embeds almost
identically to "mit Gravur", and — worse — the products that are genuinely
offered without engraving carry NO "gravur" token in their name at all (they are
sold with a slide-in *austauschbares Namensschild*). Guessing from names is
therefore hopeless. The shop already curates the answer as a real category page,
``/briefkasten-ohne-gravur``, so we take that as ground truth.

We crawl that category, resolve each listed product to a catalog ``product_id``
(URL → slug → the ``data-product-id`` printed on the product page, which bridges
the URL-alias gap where a listing links a variant URL our catalog stored under a
different canonical URL), and tag those products ``gravur_tags="ohne"``. The tag
is pushed to the Qdrant payload as ``gravur`` and applied as a HARD filter in
retrieval, so "ohne Gravur" returns exactly the shop's curated set — ranked by
the usual relevance/price/bestseller signals.

Mirrors the bestseller capture's robustness: a transient fetch failure marks the
run *partial* and then clears NOTHING (a flaky page can't erase real tags), and
the tag lives in its own non-embedded column so refreshing it never re-embeds.

Only ``/briefkasten-ohne-gravur`` exists today (``/tuerklingel-ohne-gravur``
redirects to the general doorbell category; no other ``*-ohne-gravur`` page is
live), but ``OHNE_GRAVUR_CATEGORIES`` is a list so new ones drop straight in.
"""

from sqlalchemy.orm import Session
from app.models.product import Product
from app.services.indexing import product_id_to_point_id
from app.services.qdrant_service import QdrantService
from app.services.scraper import BASE_URL, USER_AGENT, REQUEST_TIMEOUT, REQUEST_DELAY
from typing import Dict, Any, List, Set, Optional, Tuple
from datetime import datetime, timezone
import logging
import threading
import re
import time

import requests

logger = logging.getLogger(__name__)

# (tag, category listing URL). One entry today; extend as the shop adds pages.
OHNE_GRAVUR_CATEGORIES: List[Tuple[str, str]] = [
    ("ohne", f"{BASE_URL}/briefkasten-ohne-gravur"),
]

PAGE_PARAM = "seite"
MAX_PAGES = 10                       # the category is ~2 pages; generous cap
FETCH_RETRIES = 3
# Only these product-looking slugs are followed to read a product-id when the
# URL/slug match fails — keeps us from fetching every nav/CMS link on the page.
_PRODUCT_SLUG_HINT = re.compile(r"^metzler-(?:briefkasten|standbriefkasten|unterputz)", re.I)
_HREF_RE = re.compile(r'href="(' + re.escape(BASE_URL) + r'/[^"#?]+)"')
_ID_RE = re.compile(r'data-product-id="(\d+)"')
_SKU_RE = re.compile(r'"sku"\s*:\s*"?(\d+)')

CAPTURE_STATE: Dict[str, Any] = {
    "status": "idle", "products_tagged": 0, "fetch_errors": 0,
    "started_at": None, "finished_at": None, "error": None,
}
_run_lock = threading.Lock()
_state_lock = threading.Lock()


class GravurService:
    def __init__(self, db: Session):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._fetch_errors = 0

    def _get(self, url: str) -> Optional[str]:
        last = None
        for attempt in range(FETCH_RETRIES):
            try:
                r = self.session.get(url, timeout=REQUEST_TIMEOUT)
                if r.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                if r.status_code >= 400:
                    return None                       # definitive, not a transient failure
                return r.text
            except Exception as e:
                last = e
                time.sleep(0.5 * (2 ** attempt))
        logger.warning("Gravur GET failed after %d tries for %s: %s", FETCH_RETRIES, url, last)
        self._fetch_errors += 1
        return None

    def _resolve_to_product_id(
        self, url: str, by_url: Dict[str, str], by_slug: Dict[str, str], valid_ids: Set[str]
    ) -> Optional[str]:
        """Map a category-listing product URL to a catalog product_id, or None."""
        pid = by_url.get(url) or by_url.get(url.rstrip("/")) or by_url.get(url + "/")
        if pid:
            return pid
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        pid = by_slug.get(slug)
        if pid:
            return pid
        # URL-alias bridge: the listing links a variant URL our catalog stored
        # under a different canonical URL. The product page prints the JTL id.
        if not _PRODUCT_SLUG_HINT.match(slug):
            return None
        html = self._get(url) or ""
        m = _ID_RE.search(html) or _SKU_RE.search(html)
        if m and m.group(1) in valid_ids:
            return m.group(1)
        return None

    def _members(self, cat_url: str, by_url, by_slug, valid_ids) -> Set[str]:
        """product_ids listed in one 'ohne Gravur' category (across its pages)."""
        ids: Set[str] = set()
        seen_urls: Set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            url = cat_url if page == 1 else f"{cat_url}?{PAGE_PARAM}={page}"
            html = self._get(url)
            time.sleep(REQUEST_DELAY)
            if html is None:
                break
            page_urls = [u for u in _HREF_RE.findall(html) if u not in seen_urls]
            fresh_products = [u for u in page_urls
                              if _PRODUCT_SLUG_HINT.match(u.rstrip("/").rsplit("/", 1)[-1])]
            if page > 1 and not fresh_products:
                break                                 # ran past the last page
            seen_urls.update(page_urls)
            for u in page_urls:
                pid = self._resolve_to_product_id(u, by_url, by_slug, valid_ids)
                if pid:
                    ids.add(pid)
        return ids

    def capture(self) -> Dict[str, Any]:
        if not _run_lock.acquire(blocking=False):
            from app.services.ops import record_operation
            record_operation(self.db, "gravur", "skipped", {"reason": "already running"})
            return {"success": False, "message": "Gravur capture already in progress"}
        try:
            with _state_lock:
                CAPTURE_STATE.update({"status": "running", "error": None, "products_tagged": 0,
                                      "fetch_errors": 0,
                                      "started_at": datetime.now(timezone.utc).isoformat(),
                                      "finished_at": None})
            try:
                return self._capture()
            except Exception as e:
                logger.error("Gravur capture error: %s", e)
                with _state_lock:
                    CAPTURE_STATE.update({"status": "error", "error": str(e),
                                          "finished_at": datetime.now(timezone.utc).isoformat()})
                from app.services.ops import record_operation
                record_operation(self.db, "gravur", "error", {"error": str(e)})
                return {"success": False, "error": str(e)}
        finally:
            _run_lock.release()

    def _capture(self) -> Dict[str, Any]:
        self._fetch_errors = 0
        products = self.db.query(Product).all()
        by_url: Dict[str, str] = {}
        by_slug: Dict[str, str] = {}
        for p in products:
            if p.product_url:
                by_url[p.product_url] = p.product_id
                by_slug[p.product_url.rstrip("/").rsplit("/", 1)[-1]] = p.product_id
        valid_ids = {p.product_id for p in products}

        # tag -> set(product_id)
        tagged: Dict[str, Set[str]] = {}
        for tag, cat_url in OHNE_GRAVUR_CATEGORIES:
            ids = self._members(cat_url, by_url, by_slug, valid_ids)
            logger.info("Gravur: %s -> %d products", cat_url, len(ids))
            tagged.setdefault(tag, set()).update(ids)

        # product_id -> comma-joined sorted tags (e.g. "ohne")
        new_tags: Dict[str, str] = {}
        for tag, ids in tagged.items():
            for pid in ids:
                cur = set(filter(None, new_tags.get(pid, "").split(",")))
                cur.add(tag)
                new_tags[pid] = ",".join(sorted(cur))

        partial = self._fetch_errors > 0
        prev_tagged = {p.product_id: p for p in products if p.gravur_tags}

        # Apply in the DB.
        changed = 0
        for pid, val in new_tags.items():
            p = self.db.query(Product).filter(Product.product_id == pid).first()
            if p and p.gravur_tags != val:
                p.gravur_tags = val
                changed += 1
        # Clear products that were tagged but are no longer listed — unless this
        # run was partial (a fetch failed), in which case clear nothing (H-1).
        cleared = 0
        stale = set() if partial else (set(prev_tagged) - set(new_tags))
        for pid in stale:
            prev_tagged[pid].gravur_tags = None
            changed += 1
            cleared += 1

        # Push to Qdrant (no re-embed). Group by payload value.
        qs = QdrantService()
        push_ok = True
        by_value: Dict[str, List[str]] = {}
        for pid, val in new_tags.items():
            by_value.setdefault(val, []).append(product_id_to_point_id(pid))
        for val, point_ids in by_value.items():
            if not qs.set_payload_for_points(point_ids, {"gravur": val.split(",")}):
                push_ok = False
        if stale:
            clear_ids = [product_id_to_point_id(pid) for pid in stale]
            if not qs.set_payload_for_points(clear_ids, {"gravur": None}):
                push_ok = False

        self.db.commit()

        ok = not partial and push_ok
        result = {
            "success": True, "partial": not ok, "fetch_errors": self._fetch_errors,
            "qdrant_push_ok": push_ok, "products_tagged": len(new_tags),
            "tags_changed": changed, "tags_cleared": cleared,
            "by_tag": {t: len(ids) for t, ids in tagged.items()},
        }
        with _state_lock:
            CAPTURE_STATE.update({"status": "completed" if ok else "partial",
                                  "products_tagged": len(new_tags),
                                  "fetch_errors": self._fetch_errors,
                                  "finished_at": datetime.now(timezone.utc).isoformat()})
        from app.services.ops import record_operation
        record_operation(self.db, "gravur", "completed" if ok else "partial", result)
        logger.info("Gravur capture done: %s", result)
        return result


def get_capture_status() -> Dict[str, Any]:
    with _state_lock:
        return dict(CAPTURE_STATE)
