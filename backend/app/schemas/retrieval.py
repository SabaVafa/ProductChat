from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class RetrievalRequest(BaseModel):
    query: str
    limit: int = 10
    score_threshold: float = 0.0
    filters: Optional[Dict[str, Any]] = None


class RetrievalResponse(BaseModel):
    products: List[Dict[str, Any]] = []
    total: int = 0
