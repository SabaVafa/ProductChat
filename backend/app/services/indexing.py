from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.indexing_status import IndexingStatus
from app.services.qdrant_service import QdrantService
from app.services.embeddings import EmbeddingsService
from app.services.settings_service import SettingsService
from qdrant_client.models import PointStruct
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import json
import uuid

# Qdrant point IDs must be an unsigned integer or a UUID, so string product
# IDs (e.g. "laptop-001") are mapped to a stable UUID derived from them.
QDRANT_ID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def product_id_to_point_id(product_id: str) -> str:
    return str(uuid.uuid5(QDRANT_ID_NAMESPACE, product_id))

logger = logging.getLogger(__name__)

# After this many consecutive failed embed attempts a product is parked
# (indexed = -1) so it stops consuming the rate-limited free-tier quota every
# run. Reconciliation reports parked products so a genuine problem is visible.
MAX_INDEX_ATTEMPTS = 5


class IndexingService:
    def __init__(self, db: Session):
        self.db = db
        self.qdrant = QdrantService()
        self.embeddings = EmbeddingsService()

        # Use the Mistral API key configured via the Admin UI (stored
        # encrypted in the DB) to generate embeddings, not just the process
        # env var, since that's how users actually set their key.
        api_key = SettingsService(db).get_category_settings("mistral").get("api_key")
        if api_key:
            self.embeddings.set_api_key(api_key)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current indexing status."""
        status = self.db.query(IndexingStatus).order_by(IndexingStatus.id.desc()).first()
        if not status:
            return {
                "status": "idle",
                "processed": 0,
                "total": 0,
                "error_message": None,
                "started_at": None,
                "completed_at": None
            }
        return {
            "status": status.status,
            "processed": status.processed,
            "total": status.total,
            "error_message": status.error_message,
            "started_at": status.started_at.isoformat() if status.started_at else None,
            "completed_at": status.completed_at.isoformat() if status.completed_at else None
        }
    
    def health(self) -> Dict[str, Any]:
        """Compare the DB against Qdrant to surface silent index gaps.

        `missing` = products in the DB but absent from Qdrant (the silent-loss
        that makes a whole category return nothing). `orphans` = points in
        Qdrant with no matching product (e.g. a deleted product). Read-only and
        free — no Mistral calls — so it's safe to poll.
        """
        products = self.db.query(Product).all()
        db_ids = {p.product_id for p in products}
        parked = {p.product_id for p in products if p.indexed == -1}
        qdrant_ids = self.qdrant.all_indexed_product_ids()
        if qdrant_ids is None:
            return {"ok": False, "error": "could not read Qdrant", "db_count": len(db_ids)}
        missing = db_ids - qdrant_ids
        return {
            "ok": len(missing) == 0,
            "db_count": len(db_ids),
            "qdrant_count": len(qdrant_ids),
            "missing_count": len(missing),
            "missing_sample": sorted(missing)[:20],
            "parked_count": len(parked),          # given up after repeated failures
            "orphan_count": len(qdrant_ids - db_ids),
        }

    def reconcile(self, trigger_repair: bool = True) -> Dict[str, Any]:
        """Detect DB↔Qdrant gaps and queue the missing products for re-indexing.

        A product flagged indexed but absent from Qdrant is re-flagged indexed=0
        so the next incremental run re-embeds it — turning a silent, permanent
        hole into a visible, self-closing one. Products already parked at -1
        (persistently failing) are reported but NOT resurrected, so reconcile
        can't loop on a broken product. On free-tier Mistral the repair is
        eventually-consistent: each run re-embeds what the rate limit allows.
        """
        h = self.health()
        if not h.get("ok") and "error" in h:
            logger.warning("Reconcile skipped: %s", h["error"])
            return {"success": False, **h}

        products = self.db.query(Product).all()
        qdrant_ids = self.qdrant.all_indexed_product_ids()
        if qdrant_ids is None:
            return {"success": False, "error": "could not read Qdrant"}

        reflagged, parked = 0, 0
        for p in products:
            if p.product_id in qdrant_ids:
                continue
            if p.indexed == -1:          # given up — don't resurrect, just report
                parked += 1
                continue
            p.indexed = 0                # missing from Qdrant -> make it retryable
            reflagged += 1
        self.db.commit()

        result = {
            "success": True,
            "db_count": h["db_count"],
            "qdrant_count": h["qdrant_count"],
            "missing_count": h["missing_count"],
            "reflagged_for_reindex": reflagged,
            "parked_persistent_failures": parked,
            "orphan_count": h["orphan_count"],
        }
        if reflagged:
            logger.warning("Reconcile: %d products missing from Qdrant re-flagged "
                           "for re-index (%d parked)", reflagged, parked)
        else:
            logger.info("Reconcile: DB and Qdrant consistent (%d products, %d parked)",
                        h["db_count"], parked)
        from app.services.ops import record_operation
        record_operation(self.db, "reconcile", "completed", result)

        if trigger_repair and reflagged:
            self.start_indexing(incremental=True)
        return result

    def start_indexing(self, incremental: bool = False) -> Dict[str, Any]:
        """Start the indexing process."""
        # Check if already running
        current_status = self.get_status()
        if current_status["status"] == "running":
            return {"success": False, "message": "Indexing already in progress"}
        
        # Create collection if needed
        self.qdrant.create_collection()
        
        # Get products to index
        if incremental:
            # Skip products parked after too many failures (indexed == -1), so a
            # persistently-broken product doesn't drain the quota every run.
            products = self.db.query(Product).filter(Product.indexed == 0).all()
        else:
            # For full reindex, delete collection first
            self.qdrant.delete_collection()
            self.qdrant.create_collection()
            products = self.db.query(Product).all()
        
        total = len(products)
        
        # Create status record
        status = IndexingStatus(
            status="running",
            processed=0,
            total=total,
            started_at=datetime.utcnow()
        )
        self.db.add(status)
        self.db.commit()
        
        try:
            # Small batches so the processed count (and the progress bar in
            # the Admin UI polling /index/status) advances visibly.
            batch_size = 5
            succeeded_ids = set()
            for i in range(0, total, batch_size):
                batch = products[i:i + batch_size]
                succeeded_ids.update(self._process_batch(batch))

                # Update status
                status.processed = min(i + batch_size, total)
                self.db.commit()

            # Mark ONLY the products whose vectors actually landed in Qdrant as
            # indexed. A product whose embed failed is set back to 0 (retryable)
            # — NOT left at its old flag, which is how "indexed but missing from
            # Qdrant" gaps were created. After MAX_INDEX_ATTEMPTS it is parked at
            # -1 so it stops consuming quota; reconciliation still surfaces it.
            for product in products:
                if product.product_id in succeeded_ids:
                    product.indexed = 1
                    product.index_attempts = 0
                else:
                    attempts = (product.index_attempts or 0) + 1
                    product.index_attempts = attempts
                    product.indexed = -1 if attempts >= MAX_INDEX_ATTEMPTS else 0

            failed = total - len(succeeded_ids)
            status.status = "completed"
            status.completed_at = datetime.utcnow()
            if failed:
                status.error_message = f"{failed} products failed embedding and remain unindexed"
            self.db.commit()

            from app.services.ops import record_operation
            record_operation(self.db, "index", "completed", {
                "incremental": incremental, "succeeded": len(succeeded_ids), "failed": failed,
            })

            return {
                "success": True,
                "message": f"Indexed {len(succeeded_ids)} of {total} products"
                           + (f" ({failed} failed — rerun incremental indexing)" if failed else ""),
                "total": len(succeeded_ids)
            }
            
        except Exception as e:
            logger.error(f"Indexing error: {e}")
            status.status = "error"
            status.error_message = str(e)
            status.completed_at = datetime.utcnow()
            self.db.commit()
            from app.services.ops import record_operation
            record_operation(self.db, "index", "error", {"error": str(e)})
            return {
                "success": False,
                "message": f"Indexing failed: {str(e)}"
            }
    
    def _process_batch(self, products: List[Product]) -> set:
        """Process a batch of products. Returns the product_ids whose vectors
        were successfully upserted (callers must only flag those as indexed)."""
        # One embeddings API call for the whole batch (fewer calls → far fewer
        # rate-limit failures than embedding each product individually).
        texts = [
            self.embeddings.compose_product_text({
                "name": p.name,
                "description": p.description,
                "category": p.category,
                "brand": p.brand,
                "price": p.price,
                "attributes": p.attributes,
            })
            for p in products
        ]
        try:
            vectors = self.embeddings.embed_texts(texts)
        except Exception as e:
            logger.error(f"Batch embedding failed for {len(products)} products: {e}")
            return set()

        points = []
        for product, embedding in zip(products, vectors):
            points.append(PointStruct(
                id=product_id_to_point_id(product.product_id),
                vector=embedding,
                payload={
                    "product_id": product.product_id,
                    "name": product.name,
                    "description": product.description,
                    "category": product.category,
                    "brand": product.brand,
                    "price": product.price,
                    "image_url": product.image_url,
                    "product_url": product.product_url,
                    "attributes": product.attributes,
                    "bestseller_rank": product.bestseller_rank,
                    # List payload so a MatchValue("ohne") filter hits; None when untagged.
                    "gravur": (product.gravur_tags.split(",") if product.gravur_tags else None),
                }
            ))

        if points:
            if not self.qdrant.upsert_points(points):
                raise RuntimeError(f"Failed to upsert {len(points)} points to Qdrant")
        return {p.product_id for p in products}
    
    def import_products_from_json(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Import products from JSON data.

        On update, name/description/category/brand/price/attributes are refreshed
        from the incoming item, but image_url and product_url are only overwritten
        when a non-empty value is supplied — so importing from a source that omits
        images (e.g. a JTL finder export) never wipes media a previous source
        (like the scraper) already provided.
        """
        imported = 0
        errors = []

        for item in data:
            try:
                product = Product(
                    product_id=str(item.get("product_id") or item.get("id")),
                    name=item.get("name"),
                    description=item.get("description"),
                    category=item.get("category"),
                    brand=item.get("brand"),
                    price=item.get("price"),
                    image_url=item.get("image_url"),
                    product_url=item.get("product_url"),
                    attributes=item.get("attributes"),
                    indexed=0
                )

                # Check if exists
                existing = self.db.query(Product).filter(
                    Product.product_id == product.product_id
                ).first()

                if existing:
                    # Update existing
                    existing.name = product.name
                    existing.description = product.description
                    existing.category = product.category
                    existing.brand = product.brand
                    existing.price = product.price
                    existing.attributes = product.attributes
                    # Preserve existing media/links if the new source omits them.
                    if product.image_url:
                        existing.image_url = product.image_url
                    if product.product_url:
                        existing.product_url = product.product_url
                    existing.indexed = 0
                else:
                    self.db.add(product)

                imported += 1

            except Exception as e:
                errors.append(f"Error importing item: {str(e)}")
                logger.error(f"Import error: {e}")
        
        self.db.commit()
        
        return {
            "success": True,
            "imported": imported,
            "errors": errors
        }
    
    def import_products_from_csv(self, csv_path: str) -> Dict[str, Any]:
        """Import products from CSV file."""
        import pandas as pd
        
        try:
            df = pd.read_csv(csv_path)
            data = df.to_dict("records")
            return self.import_products_from_json(data)
        except Exception as e:
            logger.error(f"CSV import error: {e}")
            return {
                "success": False,
                "message": f"CSV import failed: {str(e)}"
            }
