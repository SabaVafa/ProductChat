from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class IndexingStatusResponse(BaseModel):
    status: str
    processed: int
    total: int
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class ImportRequest(BaseModel):
    products: List[Dict[str, Any]]
