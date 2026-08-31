"""Background scheduler that keeps the catalog in sync automatically.

Runs ScraperService.sync() on a fixed interval (and optionally once shortly
after startup). Change detection makes every run after the first cheap, since
only products whose sitemap <lastmod> changed are re-fetched and re-embedded.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.config import settings
from app.database import SessionLocal
from app.services.scraper import ScraperService, SYNC_STATE
from app.services.suggestions import SuggestionsService
import logging

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _scheduler_tz():
    """Pinned scheduler timezone; fall back to UTC if the name is unknown (M-3)."""
    try:
        return ZoneInfo(settings.SCHEDULER_TIMEZONE)
    except Exception as e:
        logger.warning("Unknown SCHEDULER_TIMEZONE %r (%s); using UTC",
                       settings.SCHEDULER_TIMEZONE, e)
        return ZoneInfo("UTC")


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


def _bestseller_job():
    """Refresh per-category bestseller ranks (the shop recomputes them nightly)."""
    from app.services.bestsellers import BestsellerService
    # Don't run alongside a catalog sync — both write `products`, and on SQLite
    # that risks lock contention (M-2). The capture is idempotent and runs daily,
    # so skipping one tick is harmless; capture() also self-guards re-entry (M-1).
    if SYNC_STATE.get("status") == "running":
        logger.info("Scheduler: catalog sync running, skipping bestseller capture this tick")
        return
    db = SessionLocal()
    try:
        logger.info("Scheduler: starting bestseller capture")
        BestsellerService(db).capture()
    except Exception as e:
        logger.error(f"Scheduler bestseller job failed: {e}")
    finally:
        db.close()


def _gravur_job():
    """Refresh the 'ohne Gravur' category membership (curated on the shop)."""
    from app.services.gravur import GravurService
    if SYNC_STATE.get("status") == "running":
        logger.info("Scheduler: catalog sync running, skipping gravur capture this tick")
        return
    db = SessionLocal()
    try:
        logger.info("Scheduler: starting gravur capture")
        GravurService(db).capture()
    except Exception as e:
        logger.error(f"Scheduler gravur job failed: {e}")
    finally:
        db.close()


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(daemon=True, timezone=_scheduler_tz())
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
        # Catch-up gravur refresh after the startup sync (the backend rarely
        # stays up for the daily cron in this stop/start usage pattern).
        _scheduler.add_job(
            _gravur_job,
            "date",
            run_date=datetime.now() + timedelta(seconds=120),
            id="gravur_capture_startup",
        )

    # Daily bestseller-rank refresh, a bit after the shop's ~01:00 recompute.
    if settings.BESTSELLER_CAPTURE_ENABLED:
        hour = max(0, min(23, settings.BESTSELLER_CAPTURE_HOUR))
        _scheduler.add_job(
            _bestseller_job,
            "cron",
            hour=hour,
            id="bestseller_capture",
            max_instances=1,
            coalesce=True,
        )
        # Daily gravur membership refresh, alongside the bestseller capture.
        _scheduler.add_job(
            _gravur_job,
            "cron",
            hour=hour,
            minute=20,
            id="gravur_capture",
            max_instances=1,
            coalesce=True,
        )

    _scheduler.start()
    logger.info(
        f"Scheduler started: catalog sync every {interval}h "
        f"(startup run: {settings.SCRAPE_ON_STARTUP}); "
        f"bestseller capture: "
        + (f"daily @ {settings.BESTSELLER_CAPTURE_HOUR:02d}:00 {settings.SCHEDULER_TIMEZONE}"
           if settings.BESTSELLER_CAPTURE_ENABLED else "disabled")
    )


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
