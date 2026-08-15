from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.services.scraper import ScraperService, get_sync_status, SYNC_STATE
from app.services.suggestions import SuggestionsService
from app.services.settings_service import SettingsService
from app.api.deps import require_admin
from typing import Dict, Any, List
import threading
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scraper"])


def _run_sync_job(max_products: int = 0):
    """Run a scrape+index sync in a background thread with its own session."""
    db = SessionLocal()
    try:
        result = ScraperService(db).sync(max_products=max_products)
        # Refresh cached LLM starter questions only if something changed.
        if result.get("success") and result.get("changed"):
            SuggestionsService(db).generate_llm_suggestions()
    except Exception as e:
        logger.error(f"Background sync job failed: {e}")
    finally:
        db.close()


@router.get("/sync/status", response_model=Dict[str, Any])
async def sync_status(db: Session = Depends(get_db)):
    """Current sync status, falling back to the last run persisted in the DB.

    SYNC_STATE lives in memory, so after a backend restart it reads as "idle /
    never" even though a sync succeeded earlier. Merge in the persisted result
    so the panel keeps showing the real last run.
    """
    state = get_sync_status()

    if not state.get("last_success_at"):
        try:
            saved = SettingsService(db).get_category_settings("sync")
            last = saved.get("sync_last_success_at")
            if last:
                state["last_success_at"] = last
                summary = saved.get("sync_last_summary")
                if isinstance(summary, str):
                    summary = json.loads(summary)
                if isinstance(summary, dict) and state["status"] == "idle":
                    # Show the last run's numbers rather than all zeros.
                    state.update({k: v for k, v in summary.items() if k in state})
        except Exception as e:
            logger.warning(f"Could not read persisted sync status: {e}")

    return state


@router.post("/sync/run", response_model=Dict[str, Any])
async def sync_run(max_products: int = 0, _: None = Depends(require_admin)):
    """Kick off a sync now (operational/testing). Returns immediately.

    max_products: cap products upserted this run (0 = unlimited). Useful for a
    cheap bounded run without embedding the whole catalog.
    """
    if SYNC_STATE.get("status") == "running":
        return {"success": False, "message": "Sync already in progress"}
    threading.Thread(target=_run_sync_job, args=(max_products,), daemon=True).start()
    return {"success": True, "message": "Sync started", "max_products": max_products}


@router.get("/suggestions", response_model=Dict[str, List[str]])
async def suggestions(category: str = None, db: Session = Depends(get_db)):
    """Cached LLM starter questions merged with templates.

    Pass ?category=<name> for questions specific to a storefront category page.
    """
    return {"suggestions": SuggestionsService(db).get_suggestions(category=category)}
