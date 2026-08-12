from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/productchat"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "productchat"
    
    # Qdrant
    # Leave QDRANT_URL empty to run Qdrant embedded (no server); vectors are
    # then persisted to the QDRANT_PATH folder. Set it to an http(s) URL to use
    # a Qdrant server instead (e.g. the Docker setup).
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_PATH: str = "./qdrant_local"
    QDRANT_COLLECTION_NAME: str = "products"
    
    # Mistral AI defaults (can be overridden via UI)
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-large-latest"
    MISTRAL_TEMPERATURE: float = 0.7
    MISTRAL_MAX_TOKENS: int = 1000
    
    # Security
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ENCRYPTION_KEY: str = "your-32-byte-encryption-key-here"
    
    # Application
    API_PREFIX: str = "/api"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    ENVIRONMENT: str = "development"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Scraper / auto-sync scheduler
    SYNC_INTERVAL_HOURS: int = 6        # how often the catalog is re-synced
    SCRAPE_ON_STARTUP: bool = False     # run one sync ~30s after boot
    SCRAPE_MAX_PRODUCTS: int = 0        # 0 = unlimited (cap products per sync)
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
