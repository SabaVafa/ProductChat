from pydantic import BaseModel
from typing import Dict, Any, Optional


class SettingsResponse(BaseModel):
    mistral: Dict[str, Any] = {}
    qdrant: Dict[str, Any] = {}
    retrieval: Dict[str, Any] = {}
    output: Dict[str, Any] = {}
    product_data: Dict[str, Any] = {}


class CategorySettings(BaseModel):
    category: str
    settings: Dict[str, Any]


class SettingsUpdate(BaseModel):
    mistral: Optional[Dict[str, Any]] = None
    qdrant: Optional[Dict[str, Any]] = None
    retrieval: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    product_data: Optional[Dict[str, Any]] = None
