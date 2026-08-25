# Reference: JTL-Shop bestsellers — mechanics & how ProductChat uses them

> **Provenance:** distilled from the shop owner's own explainer ("Bestsellers, in plain
> language", shared as an image, 2026-08) plus a live inspection of
> edelstahl-tuerklingel.de. Facts describe the JTL-Shop's *native* bestseller
> feature; the implementation notes describe how ProductChat consumes it.

## What a "bestseller" is (the shop's native rule)

It's an **automatic "popular" label** — nobody picks bestsellers by hand; the shop
counts what people actually bought and decides on its own. Every night the shop
asks one question per product:

> *"Was this sold at least **10 times** in the last **90 days**?"* → Yes = bestseller.

Both numbers (10 sales, 90 days) are configurable in the backend. Details that
matter for design:

- Only **real, paid orders** count — cancelled/unpaid ones don't.
- **Colour/size variants roll up to their parent product** (a product isn't
  penalised for being split into variants).
- Products can be **excluded by hand** via a flag in JTL-Wawi (nobody uses this today).
- The list **updates once a day** — it is **not live**. A product selling like crazy
  this morning won't be a bestseller until tomorrow. So never design anything that
  implies "live"/"right now" ("Trending now", a live counter, …). The honest framing
  the shop already uses is **"Beliebte Produkte."**

## Where bestsellers can appear (7 placements; 3 switched on)

| Placement | Status |
|---|---|
| Dedicated page at `/Bestseller` (headline "Beliebte Produkte aus unserem Shop:") | **on** |
| "Bestseller" option in the **sort dropdown** on category pages (`?Sortierung=11`) | **on** |
| Slider on category landing pages that have no products of their own (subcategories) | **on** |
| Bestsellers pulled to the top of a product list, above everything else | off (would show 4) |
| A bestseller row on the homepage | off |
| A "Bestseller" sidebar box | off (never set up) |
| "Bestseller" as a filter chip alongside the other filters | off |

The "off" ones are built and merely switched off — enabling them is a config change,
not development.

## Two things to know before designing with this

1. **The local/dev shop is empty** — no order data, so `/Bestseller` renders empty and
   no sliders appear. That's not a bug; there's just nothing to count. To see it
   populated you need a copy that has orders. (This is why ProductChat captures rank
   from the **live** shop, not a dev copy.)
2. **There's an image "Bestseller" badge overlay** the shop can stamp onto product
   images. It is currently **off for the German shop but on for the English one** —
   almost certainly unintentional; invisible today only because there's no data. Worth
   deciding deliberately: badge everywhere, or nowhere.

## The one number worth arguing about

**10 sales in 90 days is a low bar** for a store selling mailboxes/intercoms —
expensive, considered, buy-once items. That threshold can either flag almost nothing,
or flag a handful of cheap accessories (nameplates, fonts, "no advertising" signs) and
nothing else — in the old test data the top sellers were mailboxes but the tail was all
small parts. A "Beliebte Produkte" row full of €5 signs would undersell the shop. So
before surfacing bestsellers prominently, check what the list *actually* looks like
against real numbers. **This is a business decision, not a technical one.**

## How ProductChat uses this (implementation)

ProductChat does **not** use the polluted global `/Bestseller` page. It captures the
**per-category** bestseller ordering, which is clean:

- **Source signal:** the category sort `?Sortierung=11` ("Bestseller"), per category —
  a clean ranking of real products (the €0 variation-option shells that pollute the
  global page never match our catalog, so they're excluded for free).
- **Capture:** `backend/app/services/bestsellers.py` crawls each category's
  `?Sortierung=11` listing, records each product's best (lowest) position across
  categories, and stores it as `bestseller_rank` (payload in Qdrant, no re-embed).
  Runs nightly (~02:00 Europe/Berlin, just after the shop's 01:00 recompute).
- **Use:** a **relevance-gated, banded tie-break** in retrieval — popularity only
  reorders results that are *already* comparably relevant, and (per the "low bar"
  caveat) it never surfaces an off-topic or cheap-accessory product on its own. See
  the memory note `bestseller-feature.md` for the tuning.
- **Out of scope for the assistant:** the DE/EN image-badge inconsistency and the
  threshold decision are **shop-config/business** choices, not things ProductChat
  touches.
