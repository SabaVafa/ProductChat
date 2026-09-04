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
    # medium, not large: mistral-large is tier-gated (403 tier_not_allowed on
    # standard tiers as of 2026-08) — a large default breaks fresh installs.
    MISTRAL_MODEL: str = "mistral-medium-latest"
    MISTRAL_TEMPERATURE: float = 0.7
    MISTRAL_MAX_TOKENS: int = 1000

    # Chat/LLM provider for answer generation, query understanding and
    # suggestions: "mistral" (default) or "groq". EMBEDDINGS ALWAYS use Mistral
    # (Groq has no embeddings API), so retrieval keeps working via
    # MISTRAL_API_KEY regardless of this setting. Set LLM_PROVIDER=groq to move
    # only the chat calls onto Groq's free, OpenAI-compatible endpoint — used
    # when the Mistral account's chat tier is capped (429 limit-req-minute: 0)
    # but embeddings (60/min) still work.
    LLM_PROVIDER: str = "mistral"

    # Groq (OpenAI-compatible chat). Only used when LLM_PROVIDER=groq.
    # Model ids must be ones this Groq account can access (GET /openai/v1/models);
    # Groq rotates its catalog, so these are overridable via env. The gpt-oss
    # open-weight models handle German + JSON mode well; the 20B returns its
    # chain-of-thought in a separate `reasoning` field, leaving `content` as
    # clean JSON, so our json.loads(content) is unaffected.
    GROQ_API_KEY: str = ""
    GROQ_API_BASE: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "openai/gpt-oss-120b"      # answer generation (strong)
    GROQ_SMALL_MODEL: str = "openai/gpt-oss-20b"  # query understanding / suggestions (fast)
    # gpt-oss are REASONING models: they spend completion tokens on internal
    # reasoning BEFORE the JSON answer. At the tight max_tokens the parsing step
    # uses, "medium"/"high" reasoning eats the whole budget and truncates the
    # JSON → Groq's json_object validator returns 400 (json_validate_failed).
    # "low" keeps reasoning to ~30 tokens (JSON fits, faster, fewer tokens vs the
    # free-tier TPM cap). Empty string omits the param (for non-reasoning models).
    GROQ_REASONING_EFFORT: str = "low"
    
    # Security
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ENCRYPTION_KEY: str = "your-32-byte-encryption-key-here"
    # Token required (via the X-Admin-Token header) for admin/write endpoints.
    # If empty: allowed in development (with a warning), denied otherwise.
    ADMIN_TOKEN: str = ""
    
    # Application
    API_PREFIX: str = "/api"
    # Must include every origin the widget is embedded on — without the shop
    # origin here, every /api/chat preflight from the live shop fails and the
    # widget is dead (frontend-audit H1). Override via env in deployment.
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,"
        "https://edelstahl-tuerklingel.de,https://www.edelstahl-tuerklingel.de"
    )
    ENVIRONMENT: str = "development"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Scraper / auto-sync scheduler
    SCHEDULER_ENABLED: bool = True      # master switch for ALL background jobs
    SYNC_INTERVAL_HOURS: int = 6        # how often the catalog is re-synced
    SCRAPE_ON_STARTUP: bool = False     # run one sync ~30s after boot
    SCRAPE_MAX_PRODUCTS: int = 0        # 0 = unlimited (cap products per sync)

    # Bestseller-rank auto-capture (the shop recomputes bestsellers nightly ~01:00)
    BESTSELLER_CAPTURE_ENABLED: bool = True  # run the daily capture on schedule
    BESTSELLER_CAPTURE_HOUR: int = 2         # hour (in SCHEDULER_TIMEZONE) to run it
    # Pinned so "run after the shop's ~01:00 recompute" holds regardless of the
    # host's local timezone (M-3). The shop is a German store.
    SCHEDULER_TIMEZONE: str = "Europe/Berlin"
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
