from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.config import settings
import os
from app.api import (
    chat_router, indexing_router, settings_router, retrieval_router,
    scraper_router, products_router, proxy_router, ops_router
)
from app.database import engine, Base
from sqlalchemy import text, inspect
import logging

# Configure logging: console + a rotating file. The file is the flight
# recorder — silent failures (embedding 429s, scraper skips, Qdrant errors)
# stay on disk instead of vanishing with the console window.
from logging.handlers import RotatingFileHandler

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
_file_handler = RotatingFileHandler(
    os.path.join(_LOG_DIR, "app.log"),
    maxBytes=5 * 1024 * 1024,  # 5 MB per file
    backupCount=5,             # keep app.log.1 … app.log.5
    encoding="utf-8",
)
_file_handler.setFormatter(_fmt)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger().addHandler(_file_handler)
logger = logging.getLogger(__name__)
logger.info("=== backend starting; file log at %s ===", os.path.join(_LOG_DIR, "app.log"))

# Create tables
Base.metadata.create_all(bind=engine)


def _migrate_product_columns():
    """Add scraper columns to an existing products table.

    create_all() never ALTERs existing tables, so new columns on the Product
    model won't appear on a DB created by an earlier version. Postgres supports
    ADD COLUMN IF NOT EXISTS, so this is a safe, idempotent lightweight migration.
    """
    stmts = [
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS product_url VARCHAR(1000)",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS source VARCHAR(50)",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS lastmod VARCHAR(64)",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)",
    ]
    try:
        with engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
        logger.info("Product columns migration applied")
    except Exception as e:
        logger.error(f"Product columns migration failed: {e}")


# The ALTER ... ADD COLUMN IF NOT EXISTS syntax is Postgres-specific. On a
# fresh SQLite DB, create_all() above already creates every column, so this
# lightweight migration is only needed for existing Postgres databases.
if engine.dialect.name == "postgresql":
    _migrate_product_columns()


def _ensure_columns():
    """Add columns introduced after a DB was first created (both dialects).

    create_all() never ALTERs an existing table, and SQLite lacks
    'ADD COLUMN IF NOT EXISTS', so we introspect the live columns and ALTER
    only the missing ones. Idempotent and safe to run on every startup.
    """
    wanted = {"bestseller_rank": "INTEGER", "gravur_tags": "VARCHAR(32)",
              "index_attempts": "INTEGER"}
    try:
        with engine.begin() as conn:
            existing = {c["name"] for c in inspect(conn).get_columns("products")}
            for col, ddl in wanted.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE products ADD COLUMN {col} {ddl}"))
                    logger.info("Added products.%s column", col)
    except Exception as e:
        logger.error(f"_ensure_columns failed: {e}")


_ensure_columns()

# Shared rate limiter (defined in app.limiter so routers can apply per-route limits)
from app.limiter import limiter

# Create FastAPI app
app = FastAPI(
    title="ProductChat API",
    description="AI Product Recommendation Assistant with RAG Architecture",
    version="1.0.0"
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat_router, prefix=settings.API_PREFIX)
app.include_router(indexing_router, prefix=settings.API_PREFIX)
app.include_router(settings_router, prefix=settings.API_PREFIX)
app.include_router(retrieval_router, prefix=settings.API_PREFIX)
app.include_router(scraper_router, prefix=settings.API_PREFIX)
app.include_router(products_router, prefix=settings.API_PREFIX)
app.include_router(proxy_router, prefix=settings.API_PREFIX)
app.include_router(ops_router, prefix=settings.API_PREFIX)


@app.on_event("startup")
def _startup():
    """Start the background catalog-sync scheduler."""
    from app.services.scheduler import start_scheduler
    start_scheduler()


@app.on_event("shutdown")
def _shutdown():
    from app.services.scheduler import shutdown_scheduler
    shutdown_scheduler()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "ProductChat API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.get("/productchat-widget.js")
def widget_js():
    """Serve the embeddable widget. Include it on any page (e.g. a JTL NOVA
    template) with: <script src="<backend>/productchat-widget.js" defer></script>."""
    resp = FileResponse(
        os.path.join(_STATIC_DIR, "productchat-widget.js"),
        media_type="application/javascript",
    )
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@app.get("/widget-demo", response_class=HTMLResponse)
def widget_demo():
    """A minimal page that embeds the widget exactly as a shop page would —
    for local testing without touching the real storefront."""
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ProductChat widget demo</title></head>
<body style="font-family:system-ui,sans-serif;max-width:720px;margin:60px auto;padding:0 20px;color:#334155">
<h1 style="color:#0f172a">Storefront (demo)</h1>
<p>This blank page embeds the ProductChat assistant with a single script tag —
the same way it would sit on a live JTL-Shop (NOVA) page. Look for the
<b>"Ask the assistant"</b> button in the bottom-right corner.</p>
<pre style="background:#f1f5f9;padding:14px;border-radius:10px;overflow:auto">&lt;script src="/productchat-widget.js" defer&gt;&lt;/script&gt;</pre>
<script src="/productchat-widget.js" defer></script>
</body></html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
