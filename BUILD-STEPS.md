# ProductChat — How It Was Built

*A step-by-step summary of the tool's creation, from concept to a running, documented product.*

---

## Phase 1 · The idea
- Framed the problem: keyword search is brittle, shoppers don't know SKUs, generic AI hallucinates
- Chose **RAG** (Retrieval-Augmented Generation): retrieve real products first, let the model only explain — never invent

## Phase 2 · Data foundation
- Scraped the live Metzler store (sitemap → JSON-LD product pages)
- Extracted structured facts: name, SKU, price, image, category
- Result: **842 products** across 6 categories

## Phase 3 · Storage design
- Defined data models: `Product`, `Settings`, `IndexingStatus`
- Split storage on purpose: **relational DB** for facts, **Qdrant** for meaning (vectors)

## Phase 4 · Indexing pipeline (build the index)
- Composed each product into a text blob
- Embedded it with `mistral-embed` → **1024-dim vector**
- Stored vectors in Qdrant (product IDs mapped to stable UUIDs)

## Phase 5 · RAG engine (answer a question)
- Embed the shopper's question into the same vector space
- Cosine search in Qdrant → ~10 nearest products
- Send candidates to `mistral-large` in JSON mode (pick, explain, ask)
- **Guardrail in code**: drop any product ID the model invented

## Phase 6 · Supporting services
- **Suggestions**: free template questions + cached LLM questions
- **Scheduler**: auto re-scrape with change detection (only re-embed what changed)
- **Settings**: DB-stored config; API key **Fernet-encrypted**
- **Storefront proxy**: strips framing headers so the live shop can be embedded

## Phase 7 · Interfaces
- **Backend**: FastAPI, all endpoints under `/api`
- **Frontend**: React + Vite — Store, Chat, Explorer, Admin
- **Packaging**: `docker-compose` (Postgres + Qdrant + Redis + backend + frontend)

---

## Phase 8 · Making it run locally *(this engagement)*
- Diagnosed environment: **no Docker**, Node 22 + Python 3.14, no `.env`
- Tried Docker → blocked (needs **WSL2 / Hyper-V** → **admin rights** unavailable)
- Re-architected for a local, no-admin run:
  - **SQLite** instead of Postgres
  - **Embedded Qdrant** instead of the server
  - **No Redis** (in-memory rate limiter)
  - **Mistral via REST** (`requests`) instead of the SDK (old `orjson` won't build on Python 3.14)
- Created `backend/.env`, a slim `requirements-local.txt`, and a one-click **`run.bat`**
- Built the venv, installed deps, **imported the 40 sample products**, launched both servers
- Verified end-to-end: UI renders, `/api` proxy works, graceful without an API key

## Phase 9 · Documentation & materials *(this engagement)*
- **System-review** document — engineer / UX / AI lenses + step diagram + roadmap
- Plain-language explanations of the **mechanism & background**
- **PowerPoint deck** (16 slides) presenting *and* defending the design
- **Cost analysis** on real data (~$0.02 to index, ~1¢ per chat) → added a cost slide
- Added a **"How it was built"** appendix slide

---

## Current state
A working, locally-runnable RAG assistant (`run.bat`), plus a system-review document, a 16-slide presentation with cost analysis, and a dependency-ordered roadmap (Phase 0 hardening → growth).

## How to run it
1. Set `MISTRAL_API_KEY` in `backend/.env` (or on the Settings page)
2. Double-click **`run.bat`**
3. Open **http://localhost:3000** · API docs at **http://localhost:8000/docs**
4. Run indexing from the Admin page to embed the products
