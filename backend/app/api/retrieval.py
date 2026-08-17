from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from app.services.retrieval import RetrievalService
from app.services.settings_service import SettingsService
from app.services.mistral import MistralService
from app.services.query_understanding import understand_query
from app.services.rag import _catalog_categories
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test", tags=["testing"])


@router.post("/retrieval", response_model=RetrievalResponse)
async def test_retrieval(
    request: RetrievalRequest,
    db: Session = Depends(get_db)
):
    """
    Test the retrieval pipeline (query understanding + filtered semantic search),
    without the answer-generation step. Mirrors what /chat retrieves, so it's a
    faithful debugging + QA surface.
    """
    try:
        retrieval_service = RetrievalService(db)
        api_key = SettingsService(db).get_category_settings("mistral").get("api_key")
        parsed = understand_query(
            MistralService(api_key=api_key), _catalog_categories(db), request.query
        )
        products = retrieval_service.retrieve(
            query=parsed["search_text"],
            limit=request.limit,
            score_threshold=request.score_threshold,
            filters=request.filters,
            categories=parsed["categories"] or None,
            price_min=parsed["price_min"],
            price_max=parsed["price_max"],
        )
        return RetrievalResponse(products=products, total=len(products))
    except Exception as e:
        logger.error(f"Retrieval test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
