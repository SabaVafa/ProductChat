from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse, FeedbackRequest
from app.services.rag import RAGService
from app.services.settings_service import SettingsService
from app.services import interactions
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Process a chat message using RAG architecture.

    Returns AI-generated answer with product recommendations.
    """
    try:
        # Initialize settings
        settings_service = SettingsService(db)
        settings_service.initialize_default_settings()

        # Initialize RAG service
        rag_service = RAGService(db)

        # Process chat (with prior turns for context)
        history = [{"role": t.role, "content": t.content} for t in request.history]
        response = rag_service.chat(
            request.message, history=history, is_refinement=request.is_refinement
        )

        # Best-effort logging of the exchange; attach its id for feedback.
        response["interaction_id"] = interactions.log_interaction(db, response, request.message)

        return ChatResponse(**response)

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback", response_model=Dict[str, Any])
async def submit_feedback(request: FeedbackRequest, db: Session = Depends(get_db)):
    """Attach a thumbs rating to a logged interaction."""
    ok = interactions.set_feedback(db, request.interaction_id, request.rating, request.comment)
    if not ok:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return {"success": True}


@router.get("/interactions", response_model=Dict[str, Any])
async def list_interactions(limit: int = 50, db: Session = Depends(get_db)):
    """Recent chat interactions plus a thumbs-up/down summary (for review)."""
    return interactions.recent_interactions(db, limit=limit)
