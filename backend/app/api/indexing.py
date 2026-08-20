from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body, Request
from typing import Any
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.api.deps import require_admin
from app.limiter import limiter
from app.services.jtl_adapter import map_jtl_finder, extract_items, enrich_from_jtl
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


@router.post("/import/jtl", response_model=Dict[str, Any])
async def import_jtl_export(
    payload: Any = Body(...),
    enrich: bool = False,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    Import a raw JTL-Shop 'finder' export — either the wrapper object
    (`{"products": [...]}`) or a bare list of finder items.

    - enrich=false (default): create/update products from the export.
    - enrich=true: only MERGE variant data (characteristics + finder facets —
      colours, Montageart, material...) into EXISTING products, filling missing
      links; scraped name/description/price/image are never overwritten.

    Changed products are flagged for re-embedding; run
    POST /index/start?incremental=true afterwards to make them searchable.
    """
    try:
        items = extract_items(payload)
        if not items:
            raise HTTPException(status_code=400, detail="No products found in the payload")
        if enrich:
            result: Dict[str, Any] = enrich_from_jtl(db, items)
        else:
            mapped = map_jtl_finder(items)
            result = IndexingService(db).import_products_from_json(mapped)
            result["mapped"] = len(mapped)
        result["received"] = len(items)
        from app.services.ops import record_operation
        record_operation(db, "enrich" if enrich else "import-jtl", "completed", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"JTL import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _run_bestseller_capture():
    """Crawl the shop's per-category Bestseller listings in a background thread."""
    from app.services.bestsellers import BestsellerService
    db = SessionLocal()
    try:
        BestsellerService(db).capture()
    except Exception as e:
        logger.error(f"Background bestseller capture failed: {e}")
    finally:
        db.close()


@router.post("/import/bestsellers", response_model=Dict[str, Any])
@limiter.limit("6/hour")
async def capture_bestsellers(
    request: Request,               # required by the rate limiter (per-IP key)
    _: None = Depends(require_admin),
):
    """Capture per-category "Bestseller" rank from the live shop (background).

    Crawls each category's ?Sortierung=11 listing, records each product's best
    position, and patches `bestseller_rank` onto the Qdrant payload WITHOUT
    re-embedding. Retrieval then uses it as a relevance-gated tie-break.

    Rate-limited (this launches a multi-minute outbound crawl). Returns
    immediately; poll GET /index/bestsellers/status for progress, or see the
    "bestsellers" entry in GET /ops once done.
    """
    from app.services.bestsellers import get_capture_status
    if get_capture_status()["status"] == "running":
        return {"success": False, "message": "Bestseller capture already in progress"}
    thread = threading.Thread(target=_run_bestseller_capture, daemon=True)
    thread.start()
    return {"success": True, "message": "Bestseller capture started", "status": "running"}


@router.get("/bestsellers/status", response_model=Dict[str, Any])
async def bestseller_status(_: None = Depends(require_admin)):
    from app.services.bestsellers import get_capture_status
    return get_capture_status()


@router.post("/dedupe", response_model=Dict[str, Any])
async def dedupe_products(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Merge duplicate products sharing the same product_url (e.g. a JTL import
    keyed by sku next to the scraper's record keyed by article id). Keeps the
    richer record (image > numeric id), merges attributes, deletes the other
    row AND its vector so it can't linger in search results."""
    try:
        from app.models.product import Product
        from app.services.indexing import product_id_to_point_id
        from app.services.qdrant_service import QdrantService

        groups: Dict[str, list] = {}
        for p in db.query(Product).filter(Product.product_url.isnot(None)).all():
            groups.setdefault(p.product_url, []).append(p)

        removed, merged = [], 0
        qs = QdrantService()
        for url, plist in groups.items():
            if len(plist) < 2:
                continue
            # Prefer the record with an image; tiebreak: numeric (scraper) id.
            plist.sort(key=lambda p: (bool(p.image_url), str(p.product_id).isdigit()), reverse=True)
            keeper, rest = plist[0], plist[1:]
            for dup in rest:
                extra = dup.attributes if isinstance(dup.attributes, dict) else {}
                if extra:
                    base = keeper.attributes if isinstance(keeper.attributes, dict) else {}
                    combined = {**extra, **base}
                    if combined != base:
                        keeper.attributes = combined
                        keeper.indexed = 0
                        merged += 1
                removed.append(dup.product_id)
                db.delete(dup)
        if removed:
            qs.delete_points([product_id_to_point_id(pid) for pid in removed])
        db.commit()
        result = {"duplicate_urls": len([g for g in groups.values() if len(g) > 1]),
                  "removed": len(removed), "attr_merged_into_keeper": merged,
                  "removed_ids": removed[:20]}
        from app.services.ops import record_operation
        record_operation(db, "dedupe", "completed",
                         {k: v for k, v in result.items() if k != "removed_ids"})
        return result
    except Exception as e:
        logger.error(f"Dedupe error: {e}")
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
