from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from app.services.retrieval import RetrievalService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test", tags=["testing"])


@router.post("/retrieval", response_model=RetrievalResponse)
async def test_retrieval(
    request: RetrievalRequest,
    db: Session = Depends(get_db)
):
    """
    Test vector search without AI generation.
    
    Useful for debugging and testing retrieval performance.
    """
    try:
        retrieval_service = RetrievalService(db)
        products = retrieval_service.retrieve(
            query=request.query,
            limit=request.limit,
            score_threshold=request.score_threshold,
            filters=request.filters
        )
        
        return RetrievalResponse(
            products=products,
            total=len(products)
        )
    except Exception as e:
        logger.error(f"Retrieval test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
