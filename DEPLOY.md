# Deploying the ProductChat demo (public URL)

A single Docker container serves the whole demo: FastAPI backend + embedded
Qdrant + SQLite, with the catalog and prebuilt vectors **baked into the image**.
No Postgres/Qdrant/Redis, no persistent disk, no re-embedding on boot. Chat runs
on **Groq** (free); embeddings run on **Mistral**.

Files: [`deploy/Dockerfile`](deploy/Dockerfile), [`render.yaml`](render.yaml),
[`deploy/prepare_seed.py`](deploy/prepare_seed.py), [`.dockerignore`](.dockerignore).

---

## What you need

| Secret | What it is |
|---|---|
| `GROQ_API_KEY` | Groq key (`gsk_…`) — chat: answers, understanding, suggestions |
| `MISTRAL_API_KEY` | Mistral key — embeddings / retrieval (works on the free tier) |
| `ADMIN_TOKEN` | protects admin endpoints + the debug trace |
| `ENCRYPTION_KEY` | any Fernet key — the baked DB has **no** stored key, so it's re-seeded from `MISTRAL_API_KEY` |

Generate a Fernet key if you need one:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Step 1 — Build the seed (once, and after any catalog change)

Run with the backend **stopped** so the files are quiescent:

```bash
cd backend
../.venv/Scripts/python.exe ../deploy/prepare_seed.py
```

This writes `deploy/seed/productchat.db` (~1.6 MB) and `deploy/seed/qdrant_local/`
(~17 MB), clearing the stored Mistral key so the deploy re-seeds it from env.

## Step 2 — Get the seed into the repo the host builds from

`deploy/seed/` matches the repo's `*.db` / `qdrant_local/` ignore rules, so it is
**not** committed by accident. Force-add it for the deploy:

```bash
git add -f deploy/seed
git add deploy/Dockerfile render.yaml .dockerignore DEPLOY.md
git commit -m "Add demo deploy: single-container image + baked seed data"
git push
```

> Trade-off: this adds ~18 MB of binary data to the (public) Git history,
> permanently. The data is public shop-catalog content, so there's no privacy
> issue — only repo size. If you'd rather keep the repo lean, host the seed as a
> GitHub **Release asset** and have the Dockerfile `curl` it at build time
> instead (ask and I'll switch the Dockerfile to that).

## Step 3 — Deploy on Render (free)

1. Push must be on GitHub (repo already is).
2. Render → **New +** → **Blueprint** → connect this repo. Render reads
   `render.yaml` and creates the `productchat-demo` web service.
3. When prompted, paste the four secrets from the table above.
4. **Create** → first build + deploy takes a few minutes.
5. Your URL: `https://productchat-demo.onrender.com` (Render shows the exact one).

## Step 4 — Verify

- Open `https://<your-url>/widget-demo` and run a query
  (e.g. *"briefkasten mit zeitungsfach unter 250 euro"*).
- `GET /health` should return `{"status":"healthy"}`.
- Admin/debug: send the `X-Admin-Token` header.

---

## Notes

- **Free-tier cold start:** Render spins the service down after ~15 min idle; the
  next request wakes it in ~1 min. Fine for a shareable demo; hit it once before
  showing it to someone.
- **Rate limits (Groq free):** ~1000 req/day and 8000 tokens/min → ~2 paced
  queries/min. Bursts fall back to product cards (no errors).
- **Switching chat back to Mistral** (once its chat tier is active): set
  `LLM_PROVIDER=mistral` in the Render dashboard and redeploy.
- **Embedding on the real shop later:** add the shop origin to `CORS_ORIGINS`
  and include `<script src="https://<your-url>/productchat-widget.js" defer>` per
  `JTL-WIDGET-EMBED.md`.
- **Refreshing the catalog:** re-run Step 1 + Step 2 and redeploy. (The hosted
  instance has all background jobs off via `SCHEDULER_ENABLED=false`, so it never
  changes its own data.)
