# Embedding ProductChat on a JTL-Shop (NOVA)

The assistant ships as a **single self-contained script**. It renders a floating
"Ask the assistant" button + chat panel inside a **Shadow DOM**, so it can't
clash with the shop's Bootstrap/NOVA styles, and it talks only to the **public**
endpoints (`/api/chat`, `/api/suggestions`, `/api/chat/feedback`).

## The one line

```html
<script src="https://YOUR-BACKEND/productchat-widget.js" defer></script>
```

Served by the backend at `GET /productchat-widget.js`. Try it locally at
**http://localhost:8000/widget-demo** (a blank page that embeds the widget the
same way a shop page would).

## Configuration (optional)

Via `data-` attributes on the script tag:

```html
<script src="https://YOUR-BACKEND/productchat-widget.js"
        data-api="https://YOUR-BACKEND"
        data-category="Doorbells" defer></script>
```

or a global before the script:

```html
<script>window.ProductChatConfig = { api: "https://YOUR-BACKEND", category: "Doorbells" };</script>
```

- **api** — backend origin. Defaults to the script's own origin, so if the shop
  loads it from the backend you don't need to set it.
- **category** — pins the context for suggestions. If omitted, the widget infers
  it from the page URL (e.g. `…/tuerklingel…` → Doorbells), so per-page config is
  usually unnecessary.

## Adding it to NOVA — pick one

1. **JTL plugin (recommended, upgrade-safe).** In a small custom plugin, hook
   the footer/head and output the `<script>` tag. Survives template updates.
2. **Child-template include.** In your NOVA **child template**, add the script to
   `templates/layout/footer.tpl` (or an equivalent global include). Use a child
   template so a shop update won't overwrite it.
3. **Admin → OnPage Composer / "Eigene Inhalte".** Paste the `<script>` tag into a
   site-wide custom-content/HTML block. Quickest, no code.

## Backend prerequisites

- **Hosted & reachable.** The widget runs in customers' browsers, so the backend
  must be at a public **HTTPS** URL (not `localhost`). See the roadmap "deploy"
  step.
- **CORS.** Add the shop origin to `CORS_ORIGINS` in `backend/.env`, e.g.:
  ```
  CORS_ORIGINS=https://edelstahl-tuerklingel.de,https://www.edelstahl-tuerklingel.de
  ```
- **No admin token needed** — the widget uses only public endpoints. Indexing,
  settings, and conversation logs remain behind the `X-Admin-Token`.

## What the shopper gets

Floating launcher → chat panel with: natural-language recommendations, product
cards (image, price, link straight to the product page), context-aware starter
questions, one-tap refine chips, multi-turn memory, and 👍/👎 feedback (captured
in the Conversations panel for quality review).
