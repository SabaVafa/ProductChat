"""Operations journal: best-effort recording of pipeline runs.

Recording must never break the operation it documents — failures here are
logged and swallowed.
"""

from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def record_operation(db, kind: str, status: str, detail: Optional[Dict[str, Any]] = None) -> None:
    """Append one journal row (kind: sync|index|import|enrich|dedupe|qa...)."""
    try:
        from app.models.operation import Operation
        db.add(Operation(kind=kind, status=status, detail=detail or {}))
        db.commit()
        logger.info("operation recorded: %s %s %s", kind, status, detail)
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(f"Failed to record operation {kind}: {e}")


def list_operations(db, limit: int = 30) -> List[Dict[str, Any]]:
    from app.models.operation import Operation
    rows = db.query(Operation).order_by(Operation.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "status": r.status,
            "detail": r.detail,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
