"""Background scheduler that keeps the catalog in sync automatically.

Runs ScraperService.sync() on a fixed interval (and optionally once shortly
after startup). Change detection makes every run after the first cheap, since
only products whose sitemap <lastmod> changed are re-fetched and re-embedded.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from app.config import settings
from app.database import SessionLocal
from app.services.scraper import ScraperService, SYNC_STATE
from app.services.suggestions import SuggestionsService
import logging

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _sync_job():
    """One sync cycle: scrape -> index changed -> refresh LLM suggestions."""
    if SYNC_STATE.get("status") == "running":
        logger.info("Scheduler: previous sync still running, skipping this tick")
        return
    db = SessionLocal()
    try:
        logger.info("Scheduler: starting catalog sync")
        result = ScraperService(db).sync(max_products=settings.SCRAPE_MAX_PRODUCTS)
        if result.get("success") and result.get("changed"):
            SuggestionsService(db).generate_llm_suggestions()
    except Exception as e:
        logger.error(f"Scheduler sync job failed: {e}")
    finally:
        db.close()


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    interval = max(1, settings.SYNC_INTERVAL_HOURS)
    _scheduler.add_job(
        _sync_job,
        "interval",
        hours=interval,
        id="catalog_sync",
        max_instances=1,
        coalesce=True,
    )

    if settings.SCRAPE_ON_STARTUP:
        _scheduler.add_job(
            _sync_job,
            "date",
            run_date=datetime.now() + timedelta(seconds=30),
            id="catalog_sync_startup",
        )

    _scheduler.start()
    logger.info(
        f"Scheduler started: catalog sync every {interval}h "
        f"(startup run: {settings.SCRAPE_ON_STARTUP})"
    )


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
