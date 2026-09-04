# ProductChat — single-container demo image.
#
# Self-contained: FastAPI backend + embedded Qdrant + SQLite, with the catalog
# and prebuilt vectors BAKED IN (deploy/seed/), so a cold start serves the demo
# instantly — no Postgres/Qdrant/Redis servers, no re-embedding on boot, no
# persistent disk required. The old root Dockerfile/docker-compose.yml are the
# multi-service design and are NOT used here.
#
# Chat runs on Groq (LLM_PROVIDER=groq); embeddings run on Mistral. Set the
# secret env vars (GROQ_API_KEY, MISTRAL_API_KEY, ADMIN_TOKEN, ENCRYPTION_KEY)
# in the host dashboard — never bake them into the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Lean dependency set (SQLite + embedded Qdrant + REST Mistral/Groq via requests).
COPY backend/requirements-local.txt .
RUN pip install --no-cache-dir -r requirements-local.txt

# Backend code (the live productchat.db / qdrant_local are excluded via
# .dockerignore — the demo uses the baked seed below instead).
COPY backend/ /app/

# Baked catalog + prebuilt vectors -> /data (writable at runtime; Qdrant local
# mode and SQLite both open their paths read-write).
COPY deploy/seed/ /data/

# Point the app at the baked data and turn off every background job. These are
# defaults; the host can still override any of them.
ENV DATABASE_URL="sqlite:////data/productchat.db" \
    QDRANT_URL="" \
    QDRANT_PATH="/data/qdrant_local" \
    LLM_PROVIDER="groq" \
    SCHEDULER_ENABLED="false" \
    SCRAPE_ON_STARTUP="false" \
    BESTSELLER_CAPTURE_ENABLED="false" \
    ENVIRONMENT="production"

# Render/most PaaS inject $PORT; default to 8000 locally. Shell form so $PORT expands.
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
