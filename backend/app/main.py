from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.config import settings
from app.api import (
    chat_router, indexing_router, settings_router, retrieval_router,
    scraper_router, products_router, proxy_router
)
from app.database import engine, Base
from sqlalchemy import text
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

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

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
