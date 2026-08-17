from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
from app.database import get_db
from app.api.deps import require_admin
from app.services.ops import record_operation, list_operations

router = APIRouter(prefix="/ops", tags=["operations"])


class OperationIn(BaseModel):
    kind: str = Field(..., max_length=40)
    status: str = Field(..., max_length=20)
    detail: Optional[Dict[str, Any]] = None


@router.get("", response_model=List[Dict[str, Any]])
async def get_operations(
    limit: int = 30,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Recent pipeline operations (sync/index/import/enrich/dedupe/qa), newest first."""
    return list_operations(db, limit=min(limit, 200))


@router.post("", response_model=Dict[str, Any])
async def post_operation(
    op: OperationIn,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Record an operation performed outside the backend (e.g. a QA suite run)."""
    record_operation(db, op.kind, op.status, op.detail)
    return {"success": True}
