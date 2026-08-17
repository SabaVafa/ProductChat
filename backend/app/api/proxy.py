"""Reverse proxy for the live Metzler storefront.

The real site sends `X-Frame-Options: SAMEORIGIN` / CSP `frame-ancestors 'self'`,
so it cannot be embedded in an iframe from our app directly. This proxy fetches
the site server-side, strips those framing headers, and serves the HTML from our
own origin — which makes it same-origin and therefore framable. A `<base>` tag is
injected so the page's assets still load from the real site, and a small script
keeps in-page navigation inside the proxy (so the whole browsing experience works
and the parent app can read which category page is showing).

Demo/PoC use only.
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
import logging
import re

import requests

logger = logging.getLogger(__name__)

router = APIRouter(tags=["proxy"])

SITE = "https://edelstahl-tuerklingel.de"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Headers we must not copy back from the upstream response.
STRIP_HEADERS = {
    "x-frame-options", "content-security-policy", "content-security-policy-report-only",
    "content-encoding", "content-length", "transfer-encoding", "connection",
    "strict-transport-security", "set-cookie",
}

# Injected into <head>: base tag (assets resolve to the real site) + a script
# that rewrites clicks/form GETs so navigation stays within /api/site/.
INJECT = """
<base href="{site}/">
<script>
(function(){{
  var SITE = "{site}";
  function toProxy(url){{
    try {{
      var u = new URL(url, SITE);
      if (u.hostname.indexOf("edelstahl-tuerklingel.de") === -1) return null;
      // Must be absolute against the app origin: the injected <base> tag would
      // otherwise make a relative location.href resolve to the real domain.
      return window.location.origin + "/api/site/" + u.pathname.replace(/^\\//, "") + (u.search || "");
    }} catch (e) {{ return null; }}
  }}
  document.addEventListener("click", function(e){{
    var a = e.target && e.target.closest ? e.target.closest("a") : null;
    if (!a || !a.getAttribute("href")) return;
    if (a.target && a.target === "_blank") return;
    var p = toProxy(a.href);
    if (p) {{ e.preventDefault(); window.location.href = p; }}
  }}, true);
  document.addEventListener("submit", function(e){{
    var f = e.target;
    if (!f || (f.method && f.method.toLowerCase() !== "get")) return;
    var action = f.getAttribute("action") || window.location.href;
    var p = toProxy(action);
    if (!p) return;
    e.preventDefault();
    var params = new URLSearchParams(new FormData(f)).toString();
    window.location.href = p + (p.indexOf("?") === -1 ? "?" : "&") + params;
  }}, true);
}})();
</script>
""".replace("{site}", SITE)


def _inject_head(html: str) -> str:
    if "<head" in html.lower():
        return re.sub(r"(<head[^>]*>)", r"\1" + INJECT, html, count=1, flags=re.IGNORECASE)
    return INJECT + html


@router.get("/site")
@router.get("/site/{path:path}")
def proxy_site(path: str = "", request: Request = None):
    target = f"{SITE}/{path}"
    if request and request.url.query:
        target += f"?{request.url.query}"

    try:
        upstream = requests.get(
            target,
            headers={"User-Agent": BROWSER_UA, "Accept-Language": "de,en;q=0.8"},
            timeout=20,
            allow_redirects=True,
        )
    except Exception as e:
        logger.error(f"Proxy fetch failed for {target}: {e}")
        return PlainTextResponse(f"Proxy error: {e}", status_code=502)

    content_type = upstream.headers.get("Content-Type", "")
    headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in STRIP_HEADERS
    }

    if "text/html" in content_type.lower():
        html = _inject_head(upstream.text)
        return HTMLResponse(content=html, status_code=upstream.status_code, headers=headers)

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )
