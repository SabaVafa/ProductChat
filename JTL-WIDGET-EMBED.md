# Embedding ProductChat on a JTL-Shop

The assistant ships as a **single self-contained script**. It renders a floating
"Produktberater" button + chat panel inside a **Shadow DOM**, so it can't clash
with the shop's template styles (NOVA or custom templates like Snackys/ETK2022),
and it talks only to the **public** endpoints (`/api/chat`, `/api/suggestions`,
`/api/chat/feedback`). The UI is German.

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
        data-category="Briefkästen" defer></script>
```

or a global before the script:

```html
<script>window.ProductChatConfig = { api: "https://YOUR-BACKEND", category: "Briefkästen" };</script>
```

- **api** — backend origin. Defaults to the script's own origin, so if the shop
  loads it from the backend you don't need to set it.
- **category** — pins the context for suggestions and retrieval. **Must be the
  German catalog category exactly as in the ProductChat DB** (`Briefkästen`,
  `Türklingeln`, `Paketboxen`, …) — an English or misspelled name silently
  matches nothing. If omitted, the widget infers it from the page URL
  (e.g. `…/tuerklingel…` → `Türklingeln`), so per-page config is usually
  unnecessary.
- On product pages the widget reads the JSON-LD `sku` automatically and opens
  the chat grounded on that product; `data-product-id` /
  `ProductChatConfig.productId` can override it.

## Adding it to the shop — pick one

1. **Google Tag Manager (recommended for edelstahl-tuerklingel.de — GTM is
   already live).** Create a **Custom HTML tag**, trigger "All Pages"
   (consent-gated, see below), with:

   ```html
   <script>
     window.ProductChatConfig = { api: "https://YOUR-BACKEND" };
     (function () {
       var s = document.createElement("script");
       s.src = "https://YOUR-BACKEND/productchat-widget.js";
       s.defer = true;
       document.head.appendChild(s);
     })();
   </script>
   ```

   ⚠ **Inside a GTM Custom HTML tag, `document.currentScript` is `null`**, so
   the `data-*` attributes do **not** work there — configure via
   `window.ProductChatConfig` (as above) or inject a real `<script src>`
   element (as above, which also restores `data-*` if you set attributes on it).

2. **JTL plugin (upgrade-safe).** In a small custom plugin, hook the
   footer/head and output the `<script>` tag. Survives template updates.
3. **Child-template include.** Add the script tag to your child template's
   global footer include. The live shop runs a **custom template
   (Snackys/ETK2022)** — the include file may differ from NOVA's
   `templates/layout/footer.tpl`; use that template's footer equivalent.
4. **Admin → OnPage Composer / "Eigene Inhalte".** Paste the `<script>` tag into
   a site-wide custom-content/HTML block. Quickest, no code.

## Consent (JTL native consent manager)

The shop runs JTL's built-in consent manager. The widget is an **external
service**: when the shopper uses the chat, their messages and IP reach the
ProductChat backend. Register it there (Admin → Einstellungen → Consent-Manager →
new vendor, e.g. "Metzler Produktberater", purpose: functional/support) and — if
loading via GTM — fire the tag only on that consent category. The widget itself
sets **no cookies and no tracking**; it makes network requests only when the
shopper opens/uses the chat, which keeps its consent footprint minimal.

## CSP / HTTPS notes for this shop (verified 2026-08)

- The live shop's CSP is `frame-ancestors 'self'` **only** — it does not
  restrict `script-src`/`connect-src`, so the widget script and its `fetch()`
  calls are unaffected. (The widget is **not** an iframe, so `frame-ancestors`
  is irrelevant to it.)
- The shop sends **HSTS** → the backend **must** be public **HTTPS**, or the
  browser blocks the requests as mixed content.

## Backend prerequisites

- **Hosted & reachable.** The widget runs in customers' browsers, so the backend
  must be at a public **HTTPS** URL (not `localhost`). See the roadmap "deploy"
  step.
- **CORS.** The shop origins must be in `CORS_ORIGINS` (they are in the shipped
  default; override via `backend/.env` in deployment):
  ```
  CORS_ORIGINS=https://edelstahl-tuerklingel.de,https://www.edelstahl-tuerklingel.de
  ```
  Without this, every widget request fails CORS preflight and the chat is dead.
- **No admin token needed** — the widget uses only public endpoints. Indexing,
  settings, conversation logs, and the RAG debug trace remain behind the
  `X-Admin-Token`.

## What the shopper gets

Floating launcher → chat panel (German UI) with: natural-language
recommendations, product cards (image, German price format, "ab"-prices for
variant products, "Beliebt" pill for genuine bestsellers, link straight to the
product page), context-aware German starter questions, one-tap refine chips,
grounded product-page openings, multi-turn memory, and 👍/👎 feedback (captured
in the Conversations panel for quality review).
