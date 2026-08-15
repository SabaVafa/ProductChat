from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.api.deps import require_admin
from app.schemas.indexing import IndexingStatusResponse, ImportRequest
from app.services.indexing import IndexingService
from app.services.settings_service import SettingsService
from typing import Dict, Any
import threading
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/index", tags=["indexing"])


def _run_indexing_job(incremental: bool):
    """Run indexing in a background thread with its own DB session.

    The request-scoped session is closed once /start returns, so the thread
    must open a fresh SessionLocal for the (potentially slow) embedding work.
    """
    db = SessionLocal()
    try:
        IndexingService(db).start_indexing(incremental=incremental)
    except Exception as e:
        logger.error(f"Background indexing job failed: {e}")
    finally:
        db.close()


@router.post("/start", response_model=Dict[str, Any])
async def start_indexing(
    incremental: bool = False,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    Start the product indexing process (runs in the background).

    - incremental: If True, only index new/updated products. If False, reindex all.

    Returns immediately after kicking off the job. Poll GET /index/status to
    watch progress (status + processed/total).
    """
    try:
        # Reject if a run is already in progress before spawning a thread.
        current = IndexingService(db).get_status()
        if current["status"] == "running":
            return {"success": False, "message": "Indexing already in progress"}

        thread = threading.Thread(
            target=_run_indexing_job,
            args=(incremental,),
            daemon=True,
        )
        thread.start()

        return {"success": True, "message": "Indexing started", "status": "running"}
    except Exception as e:
        logger.error(f"Indexing start error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=IndexingStatusResponse)
async def get_indexing_status(db: Session = Depends(get_db)):
    """
    Get the current indexing status.
    """
    try:
        indexing_service = IndexingService(db)
        status = indexing_service.get_status()
        return IndexingStatusResponse(**status)
    except Exception as e:
        logger.error(f"Status retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import", response_model=Dict[str, Any])
async def import_products(
    request: ImportRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    Import products from JSON data.
    """
    try:
        indexing_service = IndexingService(db)
        result = indexing_service.import_products_from_json(request.products)
        return result
    except Exception as e:
        logger.error(f"Import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/file", response_model=Dict[str, Any])
async def import_products_from_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    Import products from a file (JSON or CSV).
    """
    try:
        indexing_service = IndexingService(db)
        
        content = await file.read()
        
        if file.filename.endswith('.json'):
            data = json.loads(content.decode('utf-8'))
            result = indexing_service.import_products_from_json(data)
        elif file.filename.endswith('.csv'):
            # Save to temp file and import
            import tempfile
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as temp:
                temp.write(content)
                temp_path = temp.name
            result = indexing_service.import_products_from_csv(temp_path)
            import os
            os.unlink(temp_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use JSON or CSV.")
        
        return result
    except Exception as e:
        logger.error(f"File import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
