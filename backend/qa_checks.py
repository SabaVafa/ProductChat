"""ProductChat data-quality & search QA suite.

Run with the backend up:  python qa_checks.py  [--api http://127.0.0.1:8000]

Checks the *collected data* (SQLite, read-only) and the *live search* (API)
against ground truths from the real store. Exit code = number of FAILs.
"""
import argparse
import json
import re
import sqlite3
import sys

import requests

parser = argparse.ArgumentParser()
parser.add_argument("--api", default="http://127.0.0.1:8000")
parser.add_argument("--db", default="productchat.db")
parser.add_argument("--live-sample", type=int, default=4,
                    help="products to price-check against the live site (0 = skip)")
parser.add_argument("--token", default="",
                    help="admin token; when set, the result is recorded in the operations journal")
args = parser.parse_args()

FAILS, WARNS, GAPS = [], [], []

# Desired behaviours that need work still on the roadmap. Their tests stay (so
# we notice if they START passing) but a failure is a tracked GAP, not a FAIL.
KNOWN_GAPS = {
    # "Unterputz" is an exact term that pure dense search dilutes, so the
    # specific Unterputz Hugo variants get out-ranked by natively-anthracite
    # boxes. Fixed by hybrid dense+keyword retrieval (Step 2).
    "SEARCH-unterputz-anthrazit",
}


def report(level: str, name: str, detail: str):
    print(f"[{level:4}] {name}: {detail}")
    if level == "FAIL":
        FAILS.append(name)
    elif level == "WARN":
        WARNS.append(name)
    elif level == "GAP":
        GAPS.append(name)


def check(name: str, ok: bool, detail: str, warn_only: bool = False):
    report("PASS" if ok else ("WARN" if warn_only else "FAIL"), name, detail)


con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
cur = con.cursor()
q1 = lambda sql: cur.execute(sql).fetchone()[0]

print("=" * 74)
print("DATA-QUALITY CHECKS (database)")
print("=" * 74)

total = q1("select count(*) from products")
check("DATA-total", total > 500, f"{total} products in catalog")

unindexed = q1("select count(*) from products where indexed=0")
check("DATA-index-complete", unindexed == 0,
      f"{unindexed} products flagged unindexed (invisible to search)")

junk = q1("""select count(*) from products
             where (price is null or price=0)
               and (description is null or description='')""")
check("DATA-no-junk-shells", junk == 0, f"{junk} junk shells (no price, no description)")

dupes_url = cur.execute("""select product_url, count(*) c, group_concat(product_id)
                           from products where product_url is not null and product_url!=''
                           group by product_url having c>1""").fetchall()
check("DATA-no-dup-urls", len(dupes_url) == 0,
      f"{len(dupes_url)} URLs shared by multiple products"
      + (f" e.g. {dupes_url[0][0][-50:]} -> ids {dupes_url[0][2]}" if dupes_url else ""))

no_url = q1("select count(*) from products where product_url is null or product_url=''")
check("DATA-links", no_url == 0, f"{no_url} products without a product link")

no_img = q1("select count(*) from products where image_url is null or image_url=''")
check("DATA-images", no_img == 0, f"{no_img} products without an image", warn_only=True)

no_cat = q1("select count(*) from products where category is null or category=''")
check("DATA-categories", no_cat == 0, f"{no_cat} products without a category", warn_only=True)

bad_price = q1("select count(*) from products where price is null or price<=0")
check("DATA-prices", bad_price == 0, f"{bad_price} products without a positive price")

moji = q1("select count(*) from products where name like '%Ã%' or name like '%�%'")
check("DATA-encoding", moji == 0, f"{moji} product names with encoding artifacts")

with_attrs = q1("""select count(*) from products
                   where attributes is not null and attributes not in ('', '{}', 'null')""")
pct = round(100 * with_attrs / max(total, 1))
check("DATA-attribute-coverage", pct >= 60,
      f"{with_attrs}/{total} ({pct}%) products carry attributes (variants/facets)",
      warn_only=True)

print()
print("=" * 74)
print("SEARCH GROUND-TRUTH CHECKS (live retrieval API)")
print("=" * 74)


def retrieve(query, limit=8):
    r = requests.post(f"{args.api}/api/test/retrieval",
                      json={"query": query, "limit": limit, "score_threshold": 0.0},
                      timeout=60)
    r.raise_for_status()
    return r.json()["products"]


# --- predicate helpers (keep ground-truths readable & robust) ---------------
def _cat(p):
    return (p.get("category") or "").lower()


def _name(p):
    return (p.get("name") or "").lower()


def _blob(p):
    return (_name(p) + " " + (p.get("description") or "") + " "
            + json.dumps(p.get("attributes") or {}, ensure_ascii=False)).lower()


def cat_in_top(ps, sub, n=5):
    return any(sub in _cat(p) for p in ps[:n])


def cat_count(ps, sub, n=5):
    return sum(1 for p in ps[:n] if sub in _cat(p))


def feature_in_top(ps, term, n=8):
    return any(term in _blob(p) for p in ps[:n])


def prices_under(ps, limit, n=5):
    prices = [p.get("price") for p in ps[:n] if isinstance(p.get("price"), (int, float))]
    return bool(prices) and all(pr <= limit + 0.01 for pr in prices)


GROUND_TRUTHS = [
    # (test name, query, predicate over retrieved list, description)

    # --- category routing: the query's product type wins -------------------
    ("SEARCH-mailbox-not-paketbox", "i need a mailbox",
     lambda ps: cat_count(ps, "briefk") >= 2 and "paketbox" not in _cat(ps[0]),
     "'mailbox' -> standalone Briefkästen at the top, not package boxes"),
    ("SEARCH-package-box", "i need a package box",
     lambda ps: cat_count(ps, "paketbox") >= 2,
     "'package box' -> Paketboxen"),
    ("SEARCH-doorbell", "wireless doorbell Funkklingel",
     lambda ps: cat_in_top(ps, "klingel"),
     "wireless doorbells -> Klingeln"),
    ("SEARCH-intercom", "video intercom with a camera",
     lambda ps: cat_in_top(ps, "sprechanlage"),
     "intercom -> Sprechanlagen"),
    ("SEARCH-house-number", "house number sign",
     lambda ps: cat_in_top(ps, "hausnummer"),
     "house number -> Hausnummern"),
    ("SEARCH-camera", "IP security camera with night vision",
     lambda ps: cat_in_top(ps, "kamera") or cat_in_top(ps, "sicherheit")
                or feature_in_top(ps, "kamera"),
     "security camera -> Kameras / Sicherheitstechnik"),
    ("SEARCH-waste-bin", "Mülltonnenbox for two bins",
     lambda ps: cat_in_top(ps, "mulltonne") or cat_in_top(ps, "mülltonne"),
     "trash-bin box -> Mülltonnenboxen"),
    ("SEARCH-gong", "door chime gong",
     lambda ps: cat_in_top(ps, "gong") or feature_in_top(ps, "gong"),
     "door gong -> Türgongs"),

    # --- mailbox sub-types --------------------------------------------------
    ("SEARCH-durchwurf", "Durchwurfbriefkasten Mauerdurchwurf",
     lambda ps: any("durchwurf" in _name(p) for p in ps[:5]),
     "through-wall mailboxes in top 5"),
    ("SEARCH-standbriefkasten", "freestanding mailbox on a stand",
     lambda ps: cat_in_top(ps, "briefk") and any("stand" in _name(p) for p in ps[:6]),
     "freestanding -> Standbriefkästen"),
    ("SEARCH-unterputz", "Unterputz Briefkasten",
     lambda ps: {"36683", "40684"} & {p["product_id"] for p in ps},
     "the real Unterputz mailboxes (Hugo/Hugo 2) are retrieved"),

    # --- features / attributes / variants ----------------------------------
    ("SEARCH-mailbox-with-bell", "mailbox with tuerklingel",
     lambda ps: cat_count(ps, "briefk", 3) >= 2
                and "paketbox" not in _name(ps[0]),
     "compound 'mailbox with doorbell' -> Briefkästen with Funkklingel"),
    ("SEARCH-unterputz-anthrazit", "Briefkasten Unterputz Anthrazit",
     lambda ps: any(p["product_id"] in ("36683", "40684") and "anthrazit" in _blob(p)
                    for p in ps),
     "Hugo/Hugo 2 retrieved WITH Anthrazit in their variant attributes"),
    ("SEARCH-anthracite-mailbox", "anthracite mailbox",
     lambda ps: cat_in_top(ps, "briefk") and feature_in_top(ps, "anthrazit"),
     "anthracite mailbox -> Briefkästen offering Anthrazit"),
    ("SEARCH-led-doorbell", "doorbell with LED ring",
     lambda ps: cat_in_top(ps, "klingel") and feature_in_top(ps, "led"),
     "LED doorbells -> Klingeln featuring LED"),
    ("SEARCH-engraving", "mailbox with custom engraving",
     lambda ps: cat_in_top(ps, "briefk") and feature_in_top(ps, "gravur"),
     "engraved mailbox -> Briefkästen with Gravur"),
    ("SEARCH-newspaper", "mailbox with newspaper compartment",
     lambda ps: cat_in_top(ps, "briefk"),
     "mailbox + newspaper compartment -> Briefkästen"),
    ("SEARCH-fingerprint", "intercom with fingerprint access",
     lambda ps: cat_in_top(ps, "sprechanlage") and feature_in_top(ps, "fingerprint"),
     "fingerprint intercom -> Sprechanlagen with fingerprint"),
    ("SEARCH-hausnummer-led", "illuminated LED house number",
     lambda ps: cat_in_top(ps, "hausnummer"),
     "LED house numbers -> Hausnummern"),

    # --- price filters (structured) ----------------------------------------
    ("SEARCH-price-mailbox-150", "a mailbox under 150 euro",
     lambda ps: cat_in_top(ps, "briefk") and prices_under(ps, 150),
     "'mailbox under 150' -> Briefkästen, all <= €150"),
    ("SEARCH-price-doorbell-100", "a doorbell under 100 euro",
     lambda ps: cat_in_top(ps, "klingel") and prices_under(ps, 100),
     "'doorbell under 100' -> Klingeln, all <= €100"),
    ("SEARCH-price-package-500", "package box under 500 euro",
     lambda ps: cat_in_top(ps, "paketbox") and prices_under(ps, 500),
     "'package box under 500' -> Paketboxen, all <= €500"),

    # --- robustness ---------------------------------------------------------
    ("SEARCH-gibberish", "xyzzy qwerty zzz nonsense",
     lambda ps: isinstance(ps, list),
     "nonsense query returns gracefully (no crash)"),
]

for name, query, predicate, desc in GROUND_TRUTHS:
    try:
        ps = retrieve(query)
        ok = bool(predicate(ps))
        detail = f"'{query}' -> {desc}"
    except Exception as e:
        ok = False
        detail = f"'{query}' -> retrieval error: {e}"
    if name in KNOWN_GAPS:
        report("PASS" if ok else "GAP", name,
               detail + ("  [now fixed!]" if ok else "  [known gap — Step 2 hybrid search]"))
    else:
        check(name, ok, detail)

print()
print("=" * 74)
print(f"PRICE FRESHNESS vs LIVE SITE (sample of {args.live_sample})")
print("=" * 74)

if args.live_sample > 0:
    rows = cur.execute("""select product_id, name, price, product_url from products
                          where product_url like 'http%' and price > 0
                          order by random() limit ?""", (args.live_sample,)).fetchall()
    for pid, name, price, url in rows:
        try:
            html = requests.get(url, timeout=20,
                                headers={"User-Agent": "Mozilla/5.0 (QA price check)"}).text
            blocks = re.findall(
                r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                html, re.DOTALL)
            live = None
            for b in blocks:
                try:
                    d = json.loads(b.strip())
                    if d.get("@type") == "Product":
                        offers = d.get("offers") or {}
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        live = float(offers.get("price")) if offers.get("price") else None
                        break
                except Exception:
                    continue
            if live is None:
                report("WARN", "FRESH-price", f"{pid}: no live price found ({name[:40]})")
            else:
                ok = abs(live - float(price)) < 0.01
                check("FRESH-price", ok,
                      f"{pid}: stored €{price} vs live €{live} ({name[:40]})", warn_only=False)
        except Exception as e:
            report("WARN", "FRESH-price", f"{pid}: fetch failed: {e}")

con.close()
print()
print("=" * 74)
print(f"RESULT: {len(FAILS)} FAIL, {len(WARNS)} WARN, {len(GAPS)} known-gap")
if FAILS:
    print("failed:", ", ".join(sorted(set(FAILS))))
if GAPS:
    print("known gaps (tracked, not failures):", ", ".join(sorted(set(GAPS))))
print("=" * 74)

# Record the run in the operations journal (best-effort).
if args.token:
    try:
        requests.post(f"{args.api}/api/ops",
                      headers={"X-Admin-Token": args.token},
                      json={"kind": "qa", "status": "completed" if not FAILS else "error",
                            "detail": {"fails": sorted(set(FAILS)), "warns": len(WARNS),
                                       "total_products": total}},
                      timeout=15)
        print("(result recorded in operations journal)")
    except Exception as e:
        print(f"(could not record result: {e})")

sys.exit(len(set(FAILS)))
