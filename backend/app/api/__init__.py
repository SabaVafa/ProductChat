from app.api.chat import router as chat_router
from app.api.indexing import router as indexing_router
from app.api.settings import router as settings_router
from app.api.retrieval import router as retrieval_router
from app.api.scraper import router as scraper_router
from app.api.products import router as products_router
from app.api.proxy import router as proxy_router
from app.api.ops import router as ops_router

__all__ = [
    "chat_router", "indexing_router", "settings_router",
    "retrieval_router", "scraper_router", "products_router", "proxy_router",
    "ops_router",
]
