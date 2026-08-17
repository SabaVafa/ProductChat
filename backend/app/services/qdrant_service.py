from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from typing import List, Dict, Any, Optional
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# A single shared client for the whole process.
#
# When QDRANT_URL is an http(s) URL we connect to a Qdrant server (Docker).
# When it's empty we run Qdrant in embedded/local mode, persisting vectors to a
# local folder (QDRANT_PATH) with no server required. Embedded mode locks that
# folder to one client instance, and the app creates many QdrantService objects
# (retrieval, indexing, scraper), so the client MUST be a module-level singleton
# or the second instance raises "Storage folder already accessed".
_shared_client: Optional[QdrantClient] = None


def _get_client() -> QdrantClient:
    global _shared_client
    if _shared_client is None:
        url = (settings.QDRANT_URL or "").strip()
        if url.startswith("http"):
            _shared_client = QdrantClient(url=url)
            logger.info(f"Qdrant: connected to server at {url}")
        else:
            path = getattr(settings, "QDRANT_PATH", None) or "./qdrant_local"
            _shared_client = QdrantClient(path=path)
            logger.info(f"Qdrant: embedded/local mode at {path}")
    return _shared_client


class QdrantService:
    def __init__(self):
        self.client = _get_client()
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.vector_size = 1024  # Mistral embeddings size
    
    def create_collection(self) -> bool:
        """Create the collection if it doesn't exist."""
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            return False
    
    def delete_collection(self) -> bool:
        """Delete the collection."""
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"Deleted collection: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting collection: {e}")
            return False
    
    def upsert_points(self, points: List[PointStruct]) -> bool:
        """Upsert points to the collection."""
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            return True
        except Exception as e:
            logger.error(f"Error upserting points: {e}")
            return False
    
    def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.0,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        try:
            search_filter = None
            if filter_conditions:
                conditions = []
                for key, value in filter_conditions.items():
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
                search_filter = Filter(must=conditions)
            
            # Use query_points (the current API). The old .search() method was
            # removed in qdrant-client 1.19, so calling it silently returned no
            # results. query_points works on both embedded and server mode.
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=search_filter,
                with_payload=True,
            )

            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload
                }
                for hit in response.points
            ]
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []
    
    def delete_points(self, point_ids: List[str]) -> bool:
        """Delete points by IDs."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=point_ids
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting points: {e}")
            return False
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection information."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": info.config.params.vectors.size,
                "points_count": info.points_count,
                "vector_size": info.config.params.vectors.size
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {}
    
    def count_points(self) -> int:
        """Count total points in collection."""
        try:
            info = self.client.get_collection(self.collection_name)
            return info.points_count
        except Exception as e:
            logger.error(f"Error counting points: {e}")
            return 0
