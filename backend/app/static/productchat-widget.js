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
    display:flex; align-items:center; justify-content:center; border:0; border-radius:50%; cursor:pointer; color:#fff; background:#015253;\
    box-shadow:0 4px 12px -3px rgba(1,82,83,.32), 0 1px 3px rgba(0,0,0,.1);\
    transition:transform .22s cubic-bezier(.34,1.56,.64,1), box-shadow .22s, background .22s; }\
  .launch:hover{ transform:translateY(-2px) scale(1.05); background:#02696a; box-shadow:0 8px 20px -6px rgba(1,82,83,.4), 0 2px 5px rgba(0,0,0,.12); }\
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
  .body{ flex:1; overflow-y:auto; padding:14px; background:#f5f8f7; display:flex; flex-direction:column; gap:9px; scrollbar-width:none; }\
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
  .inp input{ flex:1; padding:10px 13px; font-size:15px; background:#f2f6f5; border:1px solid transparent; border-radius:12px; outline:none; color:#14201f; transition:background .15s, border-color .15s, box-shadow .15s; }\
  .inp input::placeholder{ color:#9aa5a3; }\
  .inp input:focus{ background:#fff; border-color:#7fb3b3; box-shadow:0 0 0 3px rgba(1,82,83,.14); }\
  .inp button{ width:40px; height:40px; border:0; border-radius:12px; background:linear-gradient(150deg,#02726e,#015253); color:#fff; cursor:pointer; font-size:15px; flex:none; display:flex; align-items:center; justify-content:center; box-shadow:0 4px 12px -4px rgba(1,82,83,.5); transition:filter .15s, transform .12s, box-shadow .15s; }\
  .inp button:hover{ filter:brightness(1.12); box-shadow:0 6px 16px -4px rgba(1,82,83,.55); } .inp button:active{ transform:scale(.94); }\
  .inp button:disabled{ background:#c3d3d1; box-shadow:none; cursor:default; } .muted{ color:#9aa5a3; font-size:12px; padding:2px; }\
  .empty{ text-align:center; color:#5b6c6a; font-size:13px; line-height:1.5; padding:8px 14px; }\
  .empty .hero{ display:flex; align-items:center; justify-content:center; width:58px; height:58px; border-radius:19px; color:#fff; background:#2e2e36; box-shadow:0 8px 18px -6px rgba(46,46,54,.42); margin:0 auto 14px; animation:pchero 3.6s ease-in-out infinite; }\
  .empty .hero svg{ width:31px; height:31px; }\
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
      '<div class="empty"><span class="hero">' + AVATAR_SVG + "</span>" +
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
