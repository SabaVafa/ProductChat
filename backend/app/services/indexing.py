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
            for i in range(0, total, batch_size):
                batch = products[i:i + batch_size]
                self._process_batch(batch)
                
                # Update status
                status.processed = min(i + batch_size, total)
                self.db.commit()
            
            # Mark all as indexed
            for product in products:
                product.indexed = 1
            
            # Update final status
            status.status = "completed"
            status.completed_at = datetime.utcnow()
            self.db.commit()
            
            return {
                "success": True,
                "message": f"Successfully indexed {total} products",
                "total": total
            }
            
        except Exception as e:
            logger.error(f"Indexing error: {e}")
            status.status = "error"
            status.error_message = str(e)
            status.completed_at = datetime.utcnow()
            self.db.commit()
            return {
                "success": False,
                "message": f"Indexing failed: {str(e)}"
            }
    
    def _process_batch(self, products: List[Product]):
        """Process a batch of products."""
        points = []
        
        for product in products:
            try:
                # Generate embedding
                product_dict = {
                    "name": product.name,
                    "description": product.description,
                    "category": product.category,
                    "brand": product.brand,
                    "price": product.price,
                    "attributes": product.attributes
                }
                embedding = self.embeddings.embed_product(product_dict)
                
                # Create point
                point = PointStruct(
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
                        "attributes": product.attributes
                    }
                )
                points.append(point)
                
            except Exception as e:
                logger.error(f"Error processing product {product.product_id}: {e}")
                continue
        
        # Upsert batch
        if points:
            if not self.qdrant.upsert_points(points):
                raise RuntimeError(f"Failed to upsert {len(points)} points to Qdrant")
    
    def import_products_from_json(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Import products from JSON data."""
        imported = 0
        errors = []
        
        for item in data:
            try:
                product = Product(
                    product_id=str(item.get("id") or item.get("product_id")),
                    name=item.get("name"),
                    description=item.get("description"),
                    category=item.get("category"),
                    brand=item.get("brand"),
                    price=item.get("price"),
                    image_url=item.get("image_url"),
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
                    existing.image_url = product.image_url
                    existing.attributes = product.attributes
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
