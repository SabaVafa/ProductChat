/*!
 * ProductChat embeddable widget — drop-in for JTL-Shop 5 (NOVA/custom templates) or any site.
 * Usage:  <script src="https://<backend>/productchat-widget.js" defer></script>
 * Config (optional): data-api="https://<backend>"  data-category="Briefkästen"
 *                    or window.ProductChatConfig = { api, category, productId }.
 * GTM note: inside a GTM Custom-HTML tag, document.currentScript is NULL, so the
 *           data-* attributes do NOT work there — set window.ProductChatConfig
 *           BEFORE the loader, or inject a real <script src> element.
 * Self-contained: renders in a Shadow DOM so it never clashes with the shop CSS.
 * Talks only to the PUBLIC endpoints (/api/chat, /api/suggestions, /api/chat/feedback).
 * UI language: German (the shop's customers); all strings live in the T table below.
 */
(function () {
  "use strict";
  if (window.__productChatLoaded) return;
  window.__productChatLoaded = true;

  var script = document.currentScript;
  var cfg = window.ProductChatConfig || {};
  var API = (cfg.api || (script && script.getAttribute("data-api")) ||
             (script && script.src ? new URL(script.src).origin : "")).replace(/\/+$/, "");

  // ---- UI strings (German-first; single place to translate) -----------------
  var T = {
    launcher: "Produktberater",
    title: "Produktberater",
    subtitle: "Wie kann ich dir bei der Produktsuche helfen?",
    browsing: "Du stöberst in: ",
    emptyCat: "Fragen zu ",
    emptyCatTail: "? Wähle unten einen Vorschlag oder stell deine eigene Frage.",
    empty: "Nicht sicher, wo du anfangen sollst?<br>Wähle unten einen Vorschlag oder stell deine eigene Frage.",
    thinking: "Einen Moment …",
    placeholder: "Deine Frage …",
    view: "Zum Produkt ↗",
    errGeneric: "Entschuldigung, da ist etwas schiefgelaufen. Bitte versuche es erneut.",
    errRate: "Einen Moment bitte – gerade zu viele Anfragen. Versuche es gleich noch einmal.",
    introFallback: "Hallo! Ich beantworte dir gern Fragen zu diesem Produkt – zum Beispiel zu Farben, Montage oder Alternativen.",
    close: "Chat schließen",
    send: "Frage senden",
    thumbUp: "Hilfreiche Antwort",
    thumbDown: "Nicht hilfreiche Antwort",
    open: "Produktberater öffnen"
  };

  // ---- category detection (context-aware suggestions) ----------------------
  // Values MUST be the German JTL breadcrumb categories exactly as stored in the
  // ProductChat DB — English names silently match nothing (suggestions fall back
  // to generic templates and the chat category filter is discarded).
  var CATEGORY_BY_SLUG = [
    { m: "tuerklingel", c: "Türklingeln" }, { m: "klingel", c: "Türklingeln" },
    { m: "briefkasten", c: "Briefkästen" }, { m: "tuersprech", c: "Video Sprechanlagen" },
    { m: "sprechanlage", c: "Video Sprechanlagen" }, { m: "paketbox", c: "Paketboxen" },
    { m: "paketkasten", c: "Paketboxen" }, { m: "hausnummer", c: "Hausnummern" },
    { m: "muelltonnenbox", c: "Mülltonnenboxen" }, { m: "sicherheit", c: "Sicherheitstechnik" },
  ];
  function detectCategory() {
    if (cfg.category || (script && script.getAttribute("data-category")))
      return cfg.category || script.getAttribute("data-category");
    var p = (location.pathname || "").toLowerCase();
    for (var i = 0; i < CATEGORY_BY_SLUG.length; i++)
      if (p.indexOf(CATEGORY_BY_SLUG[i].m) !== -1) return CATEGORY_BY_SLUG[i].c;
    return null;
  }

  // ---- product detection: read the PDP's JSON-LD `sku` (launch context) -----
  // When embedded on a product page, this anchors the assistant to that product
  // so questions like "welche Farben?" resolve without the user restating it.
  function detectProductId() {
    if (cfg.productId || (script && script.getAttribute("data-product-id")))
      return String(cfg.productId || script.getAttribute("data-product-id"));
    try {
      var blocks = document.querySelectorAll('script[type="application/ld+json"]');
      for (var i = 0; i < blocks.length; i++) {
        var data; try { data = JSON.parse(blocks[i].textContent); } catch (e) { continue; }
        var items = Array.isArray(data) ? data : (data["@graph"] || [data]);
        for (var j = 0; j < items.length; j++) {
          var it = items[j]; if (!it) continue;
          var t = it["@type"];
          var isProduct = t === "Product" || (Array.isArray(t) && t.indexOf("Product") !== -1);
          // sku/productID match the catalog's product_id; mpn deliberately NOT
          // used (JTL mpn formats never match and would silently miss).
          if (isProduct) { var id = it.sku || it.productID; if (id) return String(id); }
        }
      }
    } catch (e) {}
    return null;
  }

  // ---- state ---------------------------------------------------------------
  var state = { open: false, loading: false, messages: [], suggestions: [],
                category: detectCategory(), productId: detectProductId() };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // Only http(s) URLs may land in href/src — a catalog record carrying a
  // javascript: URL must never become a clickable card (XSS guard).
  function safeUrl(u) { return /^https?:\/\//i.test(u || "") ? u : ""; }
  // German price formatting: 1.234,56 € (falls back to a simple form).
  function fmtPrice(v) {
    try { return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(v); }
    catch (e) { return Number(v).toFixed(2).replace(".", ",") + " €"; }
  }
  function api(path, opts) {
    return fetch(API + path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts))
      .then(function (r) {
        if (!r.ok) { var e = new Error("HTTP " + r.status); e.status = r.status; throw e; }
        return r.json();
      });
  }

  // ---- styles (scoped inside the shadow root) ------------------------------
  var CSS = "\
  :host{ all: initial; }\
  *{ box-sizing:border-box; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif; }\
  .launch{ position:fixed; bottom:24px; right:24px; z-index:2147483000; display:flex; align-items:center; gap:8px;\
    padding:13px 18px; border:0; border-radius:999px; cursor:pointer; color:#fff;\
    background:linear-gradient(135deg,#015253,#013b3c); box-shadow:0 8px 24px -8px rgba(1,82,83,.6);\
    font-size:14px; font-weight:600; transition:transform .15s, box-shadow .15s; }\
  .launch:hover{ transform:translateY(-1px); box-shadow:0 12px 28px -8px rgba(1,82,83,.7); }\
  .panel{ position:fixed; bottom:24px; right:24px; z-index:2147483000; width:400px; max-width:calc(100vw - 32px);\
    height:600px; max-height:calc(100vh - 48px); max-height:calc(100dvh - 48px); background:#fff; border:1px solid #e2e8f0; border-radius:16px;\
    box-shadow:0 24px 60px -20px rgba(15,23,42,.45); display:flex; flex-direction:column; overflow:hidden; }\
  .hd{ display:flex; align-items:center; justify-content:space-between; padding:14px 16px; color:#fff;\
    background:linear-gradient(135deg,#015253,#013b3c); }\
  .hd b{ font-size:14px; } .hd small{ display:block; font-size:11px; opacity:.8; }\
  .hd button{ background:rgba(255,255,255,.2); border:0; color:#fff; width:28px; height:28px; border-radius:8px; cursor:pointer; font-size:16px; }\
  .body{ flex:1; overflow-y:auto; padding:16px; background:#f8fafc; display:flex; flex-direction:column; gap:12px; }\
  .row{ display:flex; } .row.u{ justify-content:flex-end; } .row.a{ justify-content:flex-start; }\
  .bub{ max-width:88%; padding:9px 13px; border-radius:14px; font-size:13.5px; line-height:1.4; }\
  .u .bub{ background:#015253; color:#fff; border-bottom-right-radius:4px; }\
  .a .bub{ background:#fff; color:#334155; border:1px solid #e2e8f0; border-bottom-left-radius:4px; }\
  .card{ display:flex; gap:10px; margin-top:8px; padding:9px; background:#fff; border:1px solid #e2e8f0; border-radius:12px; text-decoration:none; }\
  a.card:hover{ border-color:#7fb3b3; } .card img{ width:52px; height:52px; border-radius:8px; object-fit:cover; background:#f1f5f9; flex:none; }\
  .card .nm{ font-size:12px; font-weight:600; color:#0f172a; }\
  .card .pr{ font-size:13px; font-weight:700; color:#059669; margin-top:3px; }\
  .card .tax{ font-size:10px; font-weight:400; color:#94a3b8; }\
  .card .pop{ font-size:10px; font-weight:600; color:#92400e; background:#fef3c7; border:1px solid #fde68a; border-radius:999px; padding:1px 6px; vertical-align:1px; }\
  .card .vw{ font-size:11px; color:#015253; } \
  .fu{ margin-top:8px; font-size:12px; color:#014748; background:#e9f3f3; border:1px solid #d3e6e5; border-radius:10px; padding:8px 11px; }\
  .fb{ display:flex; gap:4px; margin-top:6px; } .fb button{ border:0; background:none; cursor:pointer; padding:4px; border-radius:6px; color:#94a3b8; font-size:13px; }\
  .fb button.on-up{ color:#059669; background:#ecfdf5; } .fb button.on-dn{ color:#e11d48; background:#fff1f2; }\
  .chips{ display:flex; flex-wrap:wrap; gap:6px; padding:10px 12px; background:#f8fafc; border-top:1px solid #eef2f6; }\
  .chip{ font-size:12px; padding:6px 10px; background:#fff; border:1px solid #e2e8f0; border-radius:999px; cursor:pointer; color:#475569; }\
  .chip:hover{ border-color:#4d8a8a; color:#015253; }\
  .inp{ display:flex; gap:8px; padding:12px; background:#fff; border-top:1px solid #e2e8f0; }\
  .inp input{ flex:1; padding:10px 12px; font-size:16px; background:#f1f5f9; border:0; border-radius:10px; outline:none; }\
  .inp input:focus{ background:#fff; box-shadow:0 0 0 2px #015253; }\
  .inp button{ width:40px; border:0; border-radius:10px; background:#015253; color:#fff; cursor:pointer; font-size:16px; }\
  .inp button:disabled{ background:#cbd5e1; } .muted{ color:#94a3b8; font-size:12px; } .empty{ text-align:center; color:#64748b; font-size:13px; padding-top:12px; }\
  ";

  // ---- mount (GTM-safe: document.body may not exist yet) --------------------
  var root, wrap, focusInputNext = false;

  function mount() {
    var host = document.createElement("div");
    document.body.appendChild(host);
    root = host.attachShadow({ mode: "open" });
    var styleEl = document.createElement("style"); styleEl.textContent = CSS; root.appendChild(styleEl);
    wrap = document.createElement("div"); root.appendChild(wrap);
    // Escape closes the open panel (basic keyboard support).
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && state.open) { state.open = false; render(); }
    });
    render();
  }

  function lastUserAssistant() { // history for the backend (snapshot BEFORE push)
    return state.messages.slice(-8).map(function (m) { return { role: m.role, content: m.text }; });
  }

  function loadSuggestions() {
    var q = state.category ? "?category=" + encodeURIComponent(state.category) : "";
    api("/api/suggestions" + q).then(function (d) { state.suggestions = (d && d.suggestions) || []; render(); }).catch(function () {});
  }

  function chatBody(message, isRefinement, history) {
    var b = { message: message, history: history, is_refinement: !!isRefinement };
    if (state.productId) b.product_id = state.productId;   // launch context (PDP)
    if (state.category) b.category = state.category;
    return JSON.stringify(b);
  }

  function pushAssistant(res) {
    state.messages.push({ role: "assistant", text: res.answer, products: res.products || [],
      refine: res.refine_suggestions || [], followUp: res.follow_up_question || "", interactionId: res.interaction_id });
  }

  function send(text, isRefinement) {
    var q = (text || "").trim();
    if (!q || state.loading) return;
    // Snapshot the history BEFORE pushing the new message, so the current
    // question is not duplicated into the prior-turns context.
    var history = lastUserAssistant();
    state.messages.push({ role: "user", text: q });
    state.loading = true; focusInputNext = true; render();
    api("/api/chat", { method: "POST", body: chatBody(q, isRefinement, history) })
      .then(pushAssistant)
      .catch(function (err) {
        state.messages.push({ role: "assistant", text: (err && err.status === 429) ? T.errRate : T.errGeneric });
      })
      .then(function () { state.loading = false; focusInputNext = true; render(); });
  }

  // When opened on a product page, fetch a grounded opening (no user bubble):
  // the backend produces an overview of the viewed product + alternatives.
  function introOnProduct() {
    state.loading = true; render();
    api("/api/chat", { method: "POST", body: chatBody("", false, []) })
      .then(pushAssistant)
      .catch(function () { state.messages.push({ role: "assistant", text: T.introFallback }); })
      .then(function () { state.loading = false; render(); });
  }

  function rate(idx, rating) {
    var m = state.messages[idx]; if (!m || !m.interactionId) return;
    var prev = m.feedback || null;
    var next = m.feedback === rating ? "none" : rating;
    m.feedback = next === "none" ? null : next; render();
    api("/api/chat/feedback", { method: "POST", body: JSON.stringify({ interaction_id: m.interactionId, rating: next }) })
      .catch(function () { m.feedback = prev; render(); });  // revert optimistic UI on failure
  }

  function productCard(p) {
    var url = safeUrl(p.url);
    var img = safeUrl(p.image);
    var price = p.price != null
      ? '<div class="pr">' + (p.has_variants ? "ab " : "") + esc(fmtPrice(p.price)) +
        ' <span class="tax">inkl. MwSt.</span></div>'
      : "";
    var inner =
      (img ? '<img src="' + esc(img) + '" alt="">' : "") +
      '<div><div class="nm">' + esc(p.name) +
      (p.popular ? ' <span class="pop">Beliebt</span>' : "") + "</div>" +
      price +
      (url ? '<div class="vw">' + T.view + "</div>" : "") + "</div>";
    return url
      ? '<a class="card" href="' + esc(url) + '" target="_blank" rel="noopener">' + inner + "</a>"
      : '<div class="card">' + inner + "</div>";
  }

  function render() {
    // Preserve the user's draft + focus across full re-renders (async updates
    // like arriving suggestions must not eat what they're typing).
    var prevInput = root && root.getElementById && root.getElementById("pc-in");
    var draft = prevInput ? prevInput.value : "";
    var hadFocus = prevInput && root.activeElement === prevInput;

    if (!state.open) {
      wrap.innerHTML = '<button class="launch" id="pc-open" aria-label="' + T.open + '">💬 <span>' + T.launcher + "</span></button>";
      root.getElementById("pc-open").onclick = function () {
        state.open = true; focusInputNext = true;
        if (!state.suggestions.length) loadSuggestions();
        // On a product page, open already grounded on that product.
        if (state.productId && !state.messages.length) introOnProduct();
        render();
      };
      return;
    }
    var msgs = state.messages.map(function (m, i) {
      var html = '<div class="row ' + (m.role === "user" ? "u" : "a") + '"><div>';
      html += '<div class="bub">' + esc(m.text) + "</div>";
      if (m.products && m.products.length) html += m.products.map(productCard).join("");
      if (m.followUp) html += '<div class="fu">' + esc(m.followUp) + "</div>";
      if ((m.role === "assistant") && m.interactionId)
        html += '<div class="fb"><button data-i="' + i + '" data-r="up" aria-label="' + T.thumbUp + '" class="' + (m.feedback === "up" ? "on-up" : "") + '">👍</button>' +
                '<button data-i="' + i + '" data-r="down" aria-label="' + T.thumbDown + '" class="' + (m.feedback === "down" ? "on-dn" : "") + '">👎</button></div>';
      return html + "</div></div>";
    }).join("");

    var empty = state.messages.length ? "" :
      '<div class="empty">' + (state.category ? T.emptyCat + esc(state.category) + T.emptyCatTail : T.empty) + "</div>";
    var loading = state.loading ? '<div class="muted">' + T.thinking + "</div>" : "";

    var lastA = null;
    for (var k = state.messages.length - 1; k >= 0; k--) if (state.messages[k].role === "assistant") { lastA = state.messages[k]; break; }
    var chipList = state.messages.length ? (state.loading ? [] : (lastA && lastA.refine) || []) : state.suggestions;
    var chips = chipList.slice(0, 5).map(function (s) { return '<button class="chip" data-c="' + esc(s) + '">' + esc(s) + "</button>"; }).join("");

    wrap.innerHTML =
      '<div class="panel"><div class="hd"><div><b>' + T.title + "</b><small>" +
      (state.category ? T.browsing + esc(state.category) : T.subtitle) + "</small></div>" +
      '<button id="pc-close" aria-label="' + T.close + '">✕</button></div>' +
      '<div class="body" id="pc-body">' + empty + msgs + loading + "</div>" +
      (chips ? '<div class="chips">' + chips + "</div>" : "") +
      '<form class="inp" id="pc-form"><input id="pc-in" placeholder="' + T.placeholder + '" ' + (state.loading ? "disabled" : "") + ">" +
      '<button type="submit" aria-label="' + T.send + '" ' + (state.loading ? "disabled" : "") + ">➤</button></form></div>";

    root.getElementById("pc-close").onclick = function () { state.open = false; render(); };
    root.getElementById("pc-form").onsubmit = function (e) { e.preventDefault(); var inp = root.getElementById("pc-in"); send(inp.value); };
    Array.prototype.forEach.call(root.querySelectorAll(".chip"), function (b) {
      b.onclick = function () { send(b.getAttribute("data-c"), state.messages.length > 0); };
    });
    Array.prototype.forEach.call(root.querySelectorAll(".fb button"), function (b) {
      b.onclick = function () { rate(parseInt(b.getAttribute("data-i"), 10), b.getAttribute("data-r")); };
    });
    // Hide broken product images without inline handlers (CSP-safe).
    Array.prototype.forEach.call(root.querySelectorAll(".card img"), function (im) {
      im.addEventListener("error", function () { im.style.display = "none"; });
    });
    var body = root.getElementById("pc-body"); if (body) body.scrollTop = body.scrollHeight;
    var input = root.getElementById("pc-in");
    if (input && !state.loading) {
      if (draft) input.value = draft;                        // restore the draft
      if (focusInputNext || hadFocus) { input.focus(); focusInputNext = false; }
    }
  }

  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);
})();
