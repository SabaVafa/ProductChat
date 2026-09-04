# Deploying the ProductChat demo (public URL)

A single Docker container serves the whole demo: FastAPI backend + embedded
Qdrant + SQLite, with the catalog and prebuilt vectors **baked into the image**.
No Postgres/Qdrant/Redis, no persistent disk, no re-embedding on boot. Chat runs
on **Groq** (free); embeddings run on **Mistral**.

The seed (catalog DB + vectors, ~5 MB gzipped) is **not** in the repo — it ships
as a GitHub **Release asset** and the Dockerfile fetches it at build time.

Files: [`deploy/Dockerfile`](deploy/Dockerfile), [`render.yaml`](render.yaml),
[`deploy/prepare_seed.py`](deploy/prepare_seed.py),
[`deploy/fetch_seed.py`](deploy/fetch_seed.py), [`.dockerignore`](.dockerignore).

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

Run with the backend **stopped** so the files are quiescent, then pack the tarball:

```bash
cd backend
../.venv/Scripts/python.exe ../deploy/prepare_seed.py
cd ..
tar --exclude='./qdrant_local/.lock' -czf deploy/seed.tar.gz -C deploy/seed .
```

`prepare_seed.py` writes `deploy/seed/` (DB with the stored Mistral key cleared →
re-seeded from env on deploy). The tarball `deploy/seed.tar.gz` is ~5 MB, with
`productchat.db` and `qdrant_local/` at its root. Both are gitignored.

## Step 2 — Publish the seed as a GitHub Release asset

The Dockerfile fetches the seed from a fixed URL. Create a release tagged
**`demo-seed`** and upload `deploy/seed.tar.gz` as an asset named **`seed.tar.gz`**:

```bash
# using the GitHub CLI (or do it in the web UI: Releases → Draft a new release)
gh release create demo-seed deploy/seed.tar.gz -t "Demo seed" -n "Baked catalog + vectors for the demo image"
```

That yields the exact URL the Dockerfile defaults to:
`https://github.com/SabaVafa/ProductChat/releases/download/demo-seed/seed.tar.gz`

To refresh the catalog later, rebuild the tarball (Step 1) and
`gh release upload demo-seed deploy/seed.tar.gz --clobber`, then redeploy.

## Step 3 — Push the code

```bash
git push
```

(The deploy config is already committed; the seed is NOT in the repo.)

## Step 4 — Deploy on Render (free)

1. Push must be on GitHub (repo already is).
2. Render → **New +** → **Blueprint** → connect this repo. Render reads
   `render.yaml` and creates the `productchat-demo` web service.
3. When prompted, paste the four secrets from the table above.
4. **Create** → first build + deploy takes a few minutes.
5. Your URL: `https://productchat-demo.onrender.com` (Render shows the exact one).

## Step 5 — Verify

- Open `https://<your-url>/widget-demo` and run a query
  (e.g. *"briefkasten mit zeitungsfach unter 250 euro"*).
- `GET /health` should return `{"status":"healthy"}`.
- Admin/debug: send the `X-Admin-Token` header.

---

## Alternative host: Hugging Face Spaces (Docker) — free, no card, 16 GB RAM

Files: [`deploy/hf/Dockerfile`](deploy/hf/Dockerfile),
[`deploy/hf/README.md`](deploy/hf/README.md). The Space builds itself from this
GitHub repo + the `demo-seed` release asset, so its own repo needs only those two
files. Prereq: the `demo-seed` release must exist (Step 2 above) — it does.

1. Create a free account at [huggingface.co](https://huggingface.co) (no card).
2. **New → Space**: name `productchat-demo`, **SDK = Docker** (blank), visibility
   **Public**, hardware **CPU basic (free)**.
3. Add two files to the Space repo (web UI: *Files → + Add file → Create*, or
   `git push` to the Space):
   - `Dockerfile` ← contents of `deploy/hf/Dockerfile`
   - `README.md` ← contents of `deploy/hf/README.md` (the YAML header sets
     `sdk: docker` and `app_port: 7860`)
4. **Settings → Variables and secrets → New secret** — add all four as *secrets*
   (runtime): `GROQ_API_KEY`, `MISTRAL_API_KEY`, `ADMIN_TOKEN`, `ENCRYPTION_KEY`.
5. The Space builds (a few min). Your demo:
   **`https://<owner>-productchat-demo.hf.space/widget-demo`**
   (e.g. `https://sabavafa-productchat-demo.hf.space/widget-demo`).

Notes for HF: free Spaces are **public** and **sleep after ~48 h idle** (wake on
visit). To update after a catalog change, refresh the release asset (Step 1–2)
and **Restart** the Space (a rebuild re-clones `main` and re-fetches the seed).

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
