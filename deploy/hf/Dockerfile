# Hugging Face Spaces (Docker SDK) image for the ProductChat demo.
#
# Put this file + README.md at the ROOT of your HF Space repo. It builds the
# whole demo self-contained: clones the app from GitHub, installs the lean deps,
# fetches the baked catalog+vectors from the GitHub Release asset, and serves the
# backend (which serves /widget-demo itself) on HF's port 7860.
#
# Chat runs on Groq, embeddings on Mistral. Set the four secrets in the Space
# (Settings -> Variables and secrets -> New secret): GROQ_API_KEY, MISTRAL_API_KEY,
# ADMIN_TOKEN, ENCRYPTION_KEY. They are injected as env vars at runtime.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# git is needed to clone the app; then removed to keep the image lean.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# App code from the public GitHub repo (a rebuild picks up the latest main).
ARG REPO_URL="https://github.com/SabaVafa/ProductChat"
ARG REPO_REF="main"
RUN git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" /app
WORKDIR /app/backend
RUN pip install --no-cache-dir -r requirements-local.txt

# Catalog + prebuilt vectors from the GitHub Release asset (stdlib fetch).
ARG SEED_URL="https://github.com/SabaVafa/ProductChat/releases/download/demo-seed/seed.tar.gz"
RUN mkdir -p /data && python /app/deploy/fetch_seed.py "$SEED_URL" /data

# HF may run the container non-root — make the paths the app writes to (SQLite
# DB + journal, Qdrant lock, logs) world-writable so it can't hit permission errors.
RUN mkdir -p /app/backend/logs && chmod -R 777 /data /app/backend/logs

ENV DATABASE_URL="sqlite:////data/productchat.db" \
    QDRANT_URL="" \
    QDRANT_PATH="/data/qdrant_local" \
    LLM_PROVIDER="groq" \
    SCHEDULER_ENABLED="false" \
    SCRAPE_ON_STARTUP="false" \
    BESTSELLER_CAPTURE_ENABLED="false" \
    ENVIRONMENT="production"

# HF Spaces default port.
EXPOSE 7860
CMD uvicorn app.main:app --host 0.0.0.0 --port 7860
