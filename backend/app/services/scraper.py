"""Scraper for the edelstahl-tuerklingel.de catalog.

Strategy (all allowed by the site's robots.txt):
  1. Read the sitemap index -> sub-sitemaps -> every URL with its <lastmod>.
  2. For each URL, skip it entirely if its <lastmod> matches what we already
     stored (change detection happens *before* any HTTP fetch, so incremental
     syncs are cheap).
  3. Fetch changed/new pages and extract the JSON-LD `Product` block
     (name, sku, price, description, image) plus the breadcrumb category.
     Pages without a Product block (categories, CMS pages) are skipped.
  4. Upsert into Postgres with indexed=0 so the indexer re-embeds only them.
  5. Products that vanished from the sitemap are removed from DB + Qdrant.

The actual re-embedding/indexing is delegated to IndexingService so there is a
single code path for writing vectors to Qdrant.
"""

from sqlalchemy.orm import Session
from app.models.product import Product
from app.services.indexing import IndexingService, product_id_to_point_id
from app.services.qdrant_service import QdrantService
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import threading
import logging
import hashlib
import gzip
import html
import json
import re
import time

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://edelstahl-tuerklingel.de"
SITEMAP_INDEX_URL = f"{BASE_URL}/export/sitemap_index.xml"
USER_AGENT = (
    "Mozilla/5.0 (compatible; ProductChatBot/1.0; +https://edelstahl-tuerklingel.de) "
    "RAG-demo scraper"
)
REQUEST_TIMEOUT = 20
REQUEST_DELAY = 0.25  # polite delay between page fetches (seconds)

# Shared, in-process sync status (the scheduler and the API run in the same
# process, so a module-level dict is enough to surface progress to the UI).
SYNC_STATE: Dict[str, Any] = {
    "status": "idle",           # idle | running | completed | error
    "phase": None,              # scanning | indexing | None
    "total_urls": 0,
    "scanned": 0,
    "products_found": 0,
    "changed": 0,
    "removed": 0,
    "indexed": 0,
    "started_at": None,
    "finished_at": None,
    "last_success_at": None,
    "error": None,
}
_sync_lock = threading.Lock()


class ScraperService:
    def __init__(self, db: Session):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    # ---- HTTP -----------------------------------------------------------
    def _get(self, url: str, binary: bool = False) -> Optional[Any]:
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.content if binary else resp.text
        except Exception as e:
            logger.warning(f"Scraper GET failed for {url}: {e}")
            return None

    # ---- Sitemap --------------------------------------------------------
    def fetch_sitemap_entries(self) -> List[Dict[str, str]]:
        """Return [{'url', 'lastmod'}] for every URL across all sub-sitemaps."""
        index_xml = self._get(SITEMAP_INDEX_URL)
        if not index_xml:
            return []

        sub_sitemaps = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", index_xml)
        entries: List[Dict[str, str]] = []

        for sm_url in sub_sitemaps:
            raw = self._get(sm_url, binary=True)
            if not raw:
                continue
            # Sub-sitemaps may be gzipped files (magic bytes 1f 8b).
            if raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.decompress(raw)
                except Exception as e:
                    logger.warning(f"Failed to gunzip {sm_url}: {e}")
                    continue
            xml = raw.decode("utf-8", errors="replace")

            for block in re.findall(r"<url>(.*?)</url>", xml, re.DOTALL):
                loc_m = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block)
                if not loc_m:
                    continue
                mod_m = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", block)
                entries.append({
                    "url": loc_m.group(1).strip(),
                    "lastmod": mod_m.group(1).strip() if mod_m else "",
                })

        return entries

    # ---- Product page parsing ------------------------------------------
    @staticmethod
    def _clean(text: Optional[str]) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)      # strip HTML tags
        text = html.unescape(text)                 # decode entities
        return re.sub(r"\s+", " ", text).strip()

    def _extract_ld_json(self, page_html: str) -> List[dict]:
        blocks = re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            page_html,
            re.DOTALL,
        )
        parsed = []
        for b in blocks:
            try:
                parsed.append(json.loads(b.strip()))
            except Exception:
                continue
        return parsed

    def parse_product(self, url: str, page_html: str) -> Optional[Dict[str, Any]]:
        """Extract a product dict from a page, or None if it isn't a product."""
        ld = self._extract_ld_json(page_html)
        product = next((d for d in ld if d.get("@type") == "Product"), None)
        if not product:
            return None

        sku = product.get("sku") or product.get("productID")
        if not sku:
            return None

        # JTL variation options (e.g. "Schriftart 12", "Unterputz", "Schloss
        # links") emit their own Product JSON-LD blocks with no description and
        # price 0. They aren't real products and pollute retrieval — skip them.
        _desc = self._clean(product.get("description"))
        _offers = product.get("offers") or {}
        if isinstance(_offers, list):
            _offers = _offers[0] if _offers else {}
        try:
            _price_probe = float(_offers.get("price")) if isinstance(_offers, dict) and _offers.get("price") is not None else None
        except (TypeError, ValueError):
            _price_probe = None
        if not _price_probe or _price_probe <= 0:
            # Everything sellable has a positive price; price-0 "products" are
            # variation options (e.g. "LAN / PoE", "Schriftart 12") — even when
            # they carry a description. Skip them.
            return None

        # Price + currency from offers.
        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = None
        currency = "EUR"
        if isinstance(offers, dict):
            try:
                price = float(offers.get("price")) if offers.get("price") is not None else None
            except (TypeError, ValueError):
                price = None
            currency = offers.get("priceCurrency") or "EUR"

        # First image -> absolute URL; prefer the lighter /sm/ thumbnail.
        image = product.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        image_url = None
        if isinstance(image, str) and image:
            image = image.replace("/lg/", "/sm/")
            image_url = image if image.startswith("http") else f"{BASE_URL}/{image.lstrip('/')}"

        # Category from the breadcrumb (penultimate crumb; last is the product).
        category = None
        crumb = next((d for d in ld if d.get("@type") == "BreadcrumbList"), None)
        if crumb and isinstance(crumb.get("itemListElement"), list):
            items = crumb["itemListElement"]
            if len(items) >= 2:
                cat_item = items[-2]
                category = self._clean(cat_item.get("name")) or None

        # Brand.
        brand = product.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        if not brand:
            name_l = self._clean(product.get("name"))
            brand = "Metzler" if name_l.lower().startswith("metzler") else None

        return {
            "product_id": str(sku),
            "name": self._clean(product.get("name")),
            "description": self._clean(product.get("description")),
            "category": category,
            "brand": brand,
            "price": price,
            "currency": currency,
            "image_url": image_url,
            "product_url": url,
        }

    @staticmethod
    def _content_hash(p: Dict[str, Any]) -> str:
        basis = "|".join(str(p.get(k)) for k in
                         ("name", "description", "category", "brand", "price", "image_url"))
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()

    # ---- Sync -----------------------------------------------------------
    def sync(self, max_products: int = 0, remove_missing: bool = True) -> Dict[str, Any]:
        """Scrape the catalog and index only changed/new products.

        max_products: 0 = unlimited. Otherwise cap the number of products
        upserted this run (useful for a bounded first run / testing).
        """
        with _sync_lock:
            SYNC_STATE.update({
                "status": "running", "phase": "scanning", "error": None,
                "total_urls": 0, "scanned": 0, "products_found": 0,
                "changed": 0, "removed": 0, "indexed": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
            })

        try:
            entries = self.fetch_sitemap_entries()
            SYNC_STATE["total_urls"] = len(entries)
            logger.info(f"Scraper: {len(entries)} sitemap URLs")

            # Existing products keyed by their source URL for change detection.
            existing = {
                p.product_url: p
                for p in self.db.query(Product).filter(Product.product_url.isnot(None)).all()
            }
            seen_urls = set()
            changed_ids: List[str] = []

            for entry in entries:
                SYNC_STATE["scanned"] += 1
                url, lastmod = entry["url"], entry["lastmod"]
                prior = existing.get(url)

                # Change detection before any fetch: unchanged lastmod -> skip.
                if prior is not None and lastmod and prior.lastmod == lastmod:
                    seen_urls.add(url)
                    continue

                page = self._get(url)
                time.sleep(REQUEST_DELAY)
                if not page:
                    continue

                product = self.parse_product(url, page)
                if not product:
                    continue  # category / CMS page

                SYNC_STATE["products_found"] += 1
                seen_urls.add(url)
                new_hash = self._content_hash(product)

                # If content is unchanged, just refresh lastmod (no re-index).
                existing_by_pid = self.db.query(Product).filter(
                    Product.product_id == product["product_id"]
                ).first()

                if existing_by_pid and existing_by_pid.content_hash == new_hash:
                    existing_by_pid.lastmod = lastmod
                    existing_by_pid.product_url = url
                    self.db.commit()
                    continue

                self._upsert_product(product, lastmod, new_hash, existing_by_pid)
                changed_ids.append(product["product_id"])
                SYNC_STATE["changed"] += 1

                if max_products and len(changed_ids) >= max_products:
                    logger.info(f"Scraper: hit max_products cap ({max_products})")
                    break

            # Remove products that disappeared from the sitemap.
            if remove_missing and not max_products:
                self._remove_missing(existing, seen_urls)

            # Index only the changed/new products (embeds + Qdrant upsert).
            SYNC_STATE["phase"] = "indexing"
            if changed_ids:
                result = IndexingService(self.db).start_indexing(incremental=True)
                SYNC_STATE["indexed"] = result.get("total", 0)

            finished = datetime.now(timezone.utc).isoformat()
            with _sync_lock:
                SYNC_STATE.update({
                    "status": "completed", "phase": None,
                    "finished_at": finished,
                    "last_success_at": finished,
                })
            # Persist the outcome so the Admin panel still shows it after a
            # backend restart (SYNC_STATE is in-memory only).
            self._persist_last_run(finished)
            logger.info(f"Scraper sync done: {len(changed_ids)} changed/new indexed")
            return {"success": True, "changed": len(changed_ids)}

        except Exception as e:
            logger.error(f"Scraper sync error: {e}")
            with _sync_lock:
                SYNC_STATE.update({
                    "status": "error", "phase": None, "error": str(e),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                })
            return {"success": False, "error": str(e)}

    def _persist_last_run(self, finished_at: str):
        """Save the last successful run to the DB so it survives restarts."""
        try:
            from app.services.settings_service import SettingsService
            svc = SettingsService(self.db)
            summary = {
                "scanned": SYNC_STATE["scanned"],
                "total_urls": SYNC_STATE["total_urls"],
                "products_found": SYNC_STATE["products_found"],
                "changed": SYNC_STATE["changed"],
                "indexed": SYNC_STATE["indexed"],
                "removed": SYNC_STATE["removed"],
            }
            svc.set_setting("sync_last_success_at", finished_at, "sync")
            svc.set_setting("sync_last_summary", json.dumps(summary), "sync")
        except Exception as e:
            logger.warning(f"Could not persist sync result: {e}")

    def _upsert_product(self, product: Dict[str, Any], lastmod: str,
                        content_hash: str, existing: Optional[Product]):
        if existing:
            existing.name = product["name"]
            existing.description = product["description"]
            existing.category = product["category"]
            existing.brand = product["brand"]
            existing.price = product["price"]
            existing.image_url = product["image_url"]
            existing.product_url = product["product_url"]
            existing.source = "scraper"
            existing.lastmod = lastmod
            existing.content_hash = content_hash
            existing.indexed = 0
        else:
            self.db.add(Product(
                product_id=product["product_id"],
                name=product["name"],
                description=product["description"],
                category=product["category"],
                brand=product["brand"],
                price=product["price"],
                image_url=product["image_url"],
                product_url=product["product_url"],
                source="scraper",
                lastmod=lastmod,
                content_hash=content_hash,
                indexed=0,
            ))
        self.db.commit()

    def _remove_missing(self, existing: Dict[str, Product], seen_urls: set):
        """Delete products whose URL is no longer in the sitemap."""
        missing = [p for url, p in existing.items()
                   if url not in seen_urls and p.source == "scraper"]
        if not missing:
            return
        qdrant = QdrantService()
        point_ids = [product_id_to_point_id(p.product_id) for p in missing]
        try:
            qdrant.delete_points(point_ids)
        except Exception as e:
            logger.warning(f"Failed to delete {len(point_ids)} Qdrant points: {e}")
        for p in missing:
            self.db.delete(p)
        self.db.commit()
        SYNC_STATE["removed"] = len(missing)
        logger.info(f"Scraper: removed {len(missing)} products no longer on site")


def get_sync_status() -> Dict[str, Any]:
    return dict(SYNC_STATE)
