"""Persist chat interactions and capture thumbs feedback.

Logging is best-effort: a failure here must never break the chat response.
"""

from sqlalchemy.orm import Session
from app.models.interaction import Interaction
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def log_interaction(db: Session, response: Dict[str, Any], message: str) -> Optional[int]:
    """Record one chat exchange from the RAG response. Returns the row id."""
    try:
        debug = response.get("debug") or {}
        steps = {s.get("step"): s for s in debug.get("steps", [])}
        vs = steps.get("2_vector_search", {})

        retrieved = [
            {"product_id": r.get("product_id"), "name": r.get("name"), "score": r.get("score")}
            for r in (vs.get("results") or [])
        ]
        recommended_ids = [p.get("id") for p in response.get("products", [])]

        row = Interaction(
            message=message,
            retrieval_query=vs.get("retrieval_query"),
            retrieved=retrieved,
            answer=response.get("answer"),
            recommended_ids=recommended_ids,
            follow_up=response.get("follow_up_question"),
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        logger.info(
            "chat logged id=%s q=%r retrieved=%d recommended=%d",
            row.id, message, len(retrieved), len(recommended_ids),
        )
        return row.id
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to log interaction: {e}")
        return None


def set_feedback(db: Session, interaction_id: int, rating: str, comment: Optional[str] = None) -> bool:
    """Attach a thumbs rating ('up'/'down'/'none') to a logged interaction."""
    row = db.query(Interaction).filter(Interaction.id == interaction_id).first()
    if not row:
        return False
    row.feedback = {"up": 1, "down": -1}.get(rating)  # None clears it
    row.feedback_comment = comment
    db.commit()
    logger.info("feedback id=%s rating=%s", interaction_id, rating)
    return True


def recent_interactions(db: Session, limit: int = 50) -> Dict[str, Any]:
    """Return recent interactions plus a small feedback summary."""
    rows = db.query(Interaction).order_by(Interaction.id.desc()).limit(limit).all()
    up = db.query(Interaction).filter(Interaction.feedback == 1).count()
    down = db.query(Interaction).filter(Interaction.feedback == -1).count()
    total = db.query(Interaction).count()
    items: List[Dict[str, Any]] = [
        {
            "id": r.id,
            "message": r.message,
            "retrieval_query": r.retrieval_query,
            "answer": r.answer,
            "recommended_ids": r.recommended_ids,
            "retrieved": r.retrieved,
            "feedback": r.feedback,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {"total": total, "thumbs_up": up, "thumbs_down": down, "items": items}
