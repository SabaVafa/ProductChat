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
  .launch{ position:fixed; bottom:20px; right:20px; z-index:2147483000; width:58px; height:58px; padding:0;\
    display:flex; align-items:center; justify-content:center; border:0; border-radius:50%; cursor:pointer; color:#fff;\
    background:rgba(1,82,83,.82); backdrop-filter:blur(14px) saturate(1.5); -webkit-backdrop-filter:blur(14px) saturate(1.5);\
    box-shadow:0 4px 12px -3px rgba(1,82,83,.32), 0 1px 3px rgba(0,0,0,.1);\
    transition:transform .22s cubic-bezier(.34,1.56,.64,1), box-shadow .22s, background .22s; }\
  .launch:hover{ transform:translateY(-2px) scale(1.05); background:rgba(2,105,106,.88); box-shadow:0 8px 20px -6px rgba(1,82,83,.4), 0 2px 5px rgba(0,0,0,.12); }\
  .launch:active{ transform:scale(.96); }\
  .launch svg{ width:34px; height:34px; display:block; }\
  .panel{ position:fixed; bottom:20px; right:20px; z-index:2147483000; width:358px; max-width:calc(100vw - 28px);\
    height:min(552px, calc(100dvh - 36px)); background:#fff; border:1px solid rgba(1,82,83,.1); border-radius:20px;\
    box-shadow:0 32px 64px -24px rgba(1,44,45,.5), 0 8px 20px -12px rgba(0,0,0,.16); display:flex; flex-direction:column; overflow:hidden;\
    transform-origin:bottom right; animation:pcpop .22s cubic-bezier(.22,.68,.4,1.02); }\
  @keyframes pcpop{ from{ opacity:0; transform:translateY(10px) scale(.97); } to{ opacity:1; transform:none; } }\
  @media (prefers-reduced-motion: reduce){ .panel{ animation:none; } .launch{ transition:none; } .empty .hero{ animation:none; } .typing i{ animation:none; } }\
  .hd{ display:flex; align-items:center; gap:11px; padding:13px 14px; color:#fff; background:radial-gradient(95% 130% at 22% -20%, rgba(255,255,255,.14), rgba(255,255,255,0) 55%), radial-gradient(120% 150% at 20% 0%, #05867f 0%, #015b58 42%, #013d3e 100%); box-shadow:inset 0 -1px 0 rgba(255,255,255,.1); }\
  .hd .av{ position:relative; width:36px; height:36px; border-radius:12px; background:rgba(255,255,255,.16); box-shadow:inset 0 0 0 1px rgba(255,255,255,.12); display:flex; align-items:center; justify-content:center; flex:none; }\
  .hd .av svg{ width:21px; height:21px; display:block; }\
  .hd .av::after{ content:''; position:absolute; right:-2px; bottom:-2px; width:10px; height:10px; border-radius:50%; background:#2fd08a; box-shadow:0 0 0 2px #024e4c, 0 0 6px rgba(47,208,138,.7); }\
  .hd .tt{ flex:1; min-width:0; } .hd b{ font-size:14px; font-weight:600; letter-spacing:.01em; display:block; }\
  .hd small{ display:block; font-size:11px; opacity:.72; margin-top:1px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }\
  .hd button{ background:rgba(255,255,255,.12); border:0; color:#fff; width:28px; height:28px; border-radius:9px; cursor:pointer; font-size:14px; line-height:1; flex:none; transition:background .15s; }\
  .hd button:hover{ background:rgba(255,255,255,.24); }\
  .body{ flex:1; overflow-y:auto; padding:14px; background:#f5f6fa; display:flex; flex-direction:column; gap:9px; scrollbar-width:none; }\
  .body.pc-empty{ justify-content:center; }\
  .body::-webkit-scrollbar{ display:none; }\
  .row{ display:flex; } .row.u{ justify-content:flex-end; } .row.a{ justify-content:flex-start; }\
  .bub{ max-width:86%; padding:9px 12px; border-radius:15px; font-size:13.5px; line-height:1.45; }\
  .u .bub{ background:linear-gradient(155deg,#02696a,#014a4b); color:#fff; border-bottom-right-radius:5px; box-shadow:0 2px 8px -3px rgba(1,82,83,.4); }\
  .a .bub{ background:#fff; color:#26302f; border:1px solid rgba(1,44,45,.07); border-bottom-left-radius:5px; box-shadow:0 2px 6px -3px rgba(1,44,45,.09); }\
  .typing{ align-self:flex-start; display:inline-flex; align-items:center; gap:5px; padding:12px 14px; background:#fff; border:1px solid rgba(1,44,45,.07); border-radius:15px; border-bottom-left-radius:5px; box-shadow:0 2px 6px -3px rgba(1,44,45,.09); }\
  .typing i{ width:7px; height:7px; border-radius:50%; background:#8fbcb8; display:block; animation:pctype 1.3s infinite ease-in-out; }\
  .typing i:nth-child(2){ animation-delay:.16s; } .typing i:nth-child(3){ animation-delay:.32s; }\
  @keyframes pctype{ 0%,60%,100%{ transform:translateY(0); opacity:.45; } 30%{ transform:translateY(-5px); opacity:1; } }\
  .card{ display:flex; gap:11px; margin-top:7px; padding:9px; background:#fff; border:1px solid rgba(1,44,45,.09); border-radius:13px; text-decoration:none; transition:border-color .15s, box-shadow .15s, transform .15s; }\
  a.card:hover{ border-color:#4d8a8a; box-shadow:0 6px 16px -10px rgba(1,82,83,.4); transform:translateY(-1px); }\
  .card img{ width:50px; height:50px; border-radius:9px; object-fit:cover; background:#eef2f1; flex:none; }\
  .card .nm{ font-size:12px; font-weight:600; color:#14201f; line-height:1.3; }\
  .card .pr{ font-size:13px; font-weight:700; color:#0b7a5b; margin-top:3px; }\
  .card .tax{ font-size:10px; font-weight:400; color:#9aa5a3; }\
  .card .pop{ font-size:9.5px; font-weight:600; color:#015253; background:#e3f0ef; border:1px solid #cfe6e4; border-radius:999px; padding:1px 6px; vertical-align:1px; }\
  .card .vw{ font-size:11px; font-weight:500; color:#015253; margin-top:4px; }\
  .fu{ margin-top:8px; font-size:12px; color:#014748; background:#eaf4f3; border:1px solid #d3e6e5; border-radius:12px; padding:8px 11px; }\
  .fb{ display:flex; gap:3px; margin-top:5px; } .fb button{ border:0; background:none; cursor:pointer; padding:4px; border-radius:7px; color:#9aa5a3; font-size:12px; transition:background .12s; }\
  .fb button:hover{ background:rgba(1,44,45,.06); } .fb button.on-up{ color:#0b7a5b; background:#e6f5ef; } .fb button.on-dn{ color:#e11d48; background:#fff1f2; }\
  .chips{ display:flex; flex-wrap:wrap; gap:6px; padding:10px 12px; background:#fff; border-top:1px solid rgba(1,44,45,.07); }\
  .chip{ font-size:12px; padding:6px 11px; background:#f2f7f6; border:1px solid transparent; border-radius:999px; cursor:pointer; color:#3d5250; font-weight:500; text-align:left; transition:all .14s; }\
  .chip:hover{ background:#e3f0ef; border-color:#bcdedb; color:#015253; }\
  .inp{ display:flex; gap:8px; padding:11px 12px; background:#fff; border-top:1px solid rgba(1,44,45,.07); }\
  .inp input{ flex:1; height:44px; padding:0 14px; font-size:16px; background:#f5f6fa; border:1px solid #dadada; border-radius:8px; outline:none; color:#000; transition:border-color .15s, box-shadow .15s; }\
  .inp input::placeholder{ color:#a1a1a1; }\
  .inp input:focus{ border-color:#015253; box-shadow:0 0 0 3px rgba(1,82,83,.10); }\
  .inp input::-webkit-search-cancel-button{ -webkit-appearance:none; appearance:none; width:16px; height:16px; margin-left:8px; cursor:pointer; opacity:.85; transition:opacity .15s; background:url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23A1A1A1' stroke-width='2.2' stroke-linecap='round'><line x1='6' y1='6' x2='18' y2='18'/><line x1='6' y1='18' x2='18' y2='6'/></svg>\") center / contain no-repeat; }\
  .inp input::-webkit-search-cancel-button:hover{ opacity:1; }\
  .inp button{ width:44px; height:44px; border:0; border-radius:8px; background:linear-gradient(150deg,#02726e,#015253); color:#fff; cursor:pointer; font-size:15px; flex:none; display:flex; align-items:center; justify-content:center; box-shadow:0 4px 12px -4px rgba(1,82,83,.5); transition:filter .15s, transform .12s, box-shadow .15s; }\
  .inp button:hover{ filter:brightness(1.12); box-shadow:0 6px 16px -4px rgba(1,82,83,.55); } .inp button:active{ transform:scale(.94); }\
  .inp button:disabled{ background:#c3d3d1; box-shadow:none; cursor:default; } .muted{ color:#9aa5a3; font-size:12px; padding:2px; }\
  .empty{ text-align:center; color:#5b6c6a; font-size:13px; line-height:1.5; padding:8px 14px; }\
  .empty .hero-logo{ display:block; width:66px; height:auto; margin:2px auto 14px; }\
  @keyframes pchero{ 0%,100%{ transform:translateY(0); } 50%{ transform:translateY(-3px); } }\
  @media (max-width:480px){ .panel{ width:calc(100vw - 20px); height:calc(100dvh - 20px); bottom:10px; right:10px; border-radius:16px; } .launch{ bottom:14px; right:14px; } }\
  ";

  // Support-agent avatar (head + shoulders with a headset), white on teal.
  var AVATAR_SVG =
    '<svg viewBox="0 0 28 28" fill="none">' +
    '<path d="M8.2 12.6a5.8 5.8 0 0 1 11.6 0" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>' +
    '<rect x="6.6" y="11.3" width="2.6" height="3.4" rx="1.3" fill="currentColor"/>' +
    '<rect x="18.8" y="11.3" width="2.6" height="3.4" rx="1.3" fill="currentColor"/>' +
    '<path d="M19.9 14.7v.8a1.6 1.6 0 0 1-1.6 1.6h-2.3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<circle cx="14" cy="12.4" r="3.7" fill="currentColor"/>' +
    '<path d="M20.6 24c0-3.5-3-5.7-6.6-5.7S7.4 20.5 7.4 24z" fill="currentColor"/></svg>';

  // Metzler wordmark logo (red/black), inlined so it works cross-origin.
  var LOGO_IMG = "data:image/png;base64,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";

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
      wrap.innerHTML = '<button class="launch" id="pc-open" aria-label="' + T.open + '" title="' + T.launcher + '">' + AVATAR_SVG + "</button>";
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
      '<div class="empty"><img class="hero-logo" src="' + LOGO_IMG + '" alt="Metzler">' +
      (state.category ? T.emptyCat + esc(state.category) + T.emptyCatTail : T.empty) + "</div>";
    var loading = state.loading ? '<div class="typing"><i></i><i></i><i></i></div>' : "";

    var lastA = null;
    for (var k = state.messages.length - 1; k >= 0; k--) if (state.messages[k].role === "assistant") { lastA = state.messages[k]; break; }
    var chipList = state.messages.length ? (state.loading ? [] : (lastA && lastA.refine) || []) : state.suggestions;
    var chips = chipList.slice(0, 5).map(function (s) { return '<button class="chip" data-c="' + esc(s) + '">' + esc(s) + "</button>"; }).join("");

    wrap.innerHTML =
      '<div class="panel"><div class="hd">' +
      '<span class="av">' + AVATAR_SVG + "</span>" +
      '<div class="tt"><b>' + T.title + "</b><small>" +
      (state.category ? T.browsing + esc(state.category) : T.subtitle) + "</small></div>" +
      '<button id="pc-close" aria-label="' + T.close + '">✕</button></div>' +
      '<div class="body' + (state.messages.length ? "" : " pc-empty") + '" id="pc-body">' + empty + msgs + loading + "</div>" +
      (chips ? '<div class="chips">' + chips + "</div>" : "") +
      '<form class="inp" id="pc-form"><input id="pc-in" type="search" placeholder="' + T.placeholder + '" ' + (state.loading ? "disabled" : "") + ">" +
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
