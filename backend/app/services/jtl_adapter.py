"""Map a JTL-Shop 'finder' export into the shape the importer expects.

The finder export is a wrapper object:
    { "category": ..., "count": N, "products": [ {finder item}, ... ], ... }
Each finder item looks like:
    { "id", "sku", "name", "categories": [...], "variants_count",
      "price_eur_gross": {"from", "to"}, "url", "short_description",
      "characteristics": {...}, "finder_facets": {...}, "cross_sell": [...] }

We translate each into the importer's product dict:
    { product_id, name, description, category, brand, price,
      image_url, product_url, attributes }
"""

from typing import Any, Dict, List


def extract_items(payload: Any) -> List[Dict[str, Any]]:
    """Pull the product list out of a JTL export (wrapper dict or bare list)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("products"), list):
            return payload["products"]
        for value in payload.values():  # fall back to the first list found
            if isinstance(value, list):
                return value
    return []


def _price(price_field: Any):
    """JTL gives a {from, to} gross-price range; take a single representative value."""
    if isinstance(price_field, dict):
        val = price_field.get("from")
        return val if val is not None else price_field.get("to")
    if isinstance(price_field, (int, float)):
        return price_field
    return None


def _category(categories: Any):
    """Use the most specific (leaf) category from the hierarchy."""
    if isinstance(categories, list) and categories:
        return categories[-1]
    if isinstance(categories, str) and categories:
        return categories
    return None


def _brand(name: Any):
    return "Metzler" if isinstance(name, str) and "metzler" in name.lower() else None


def map_jtl_finder(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Translate JTL finder items to importer product dicts (skips invalid rows)."""
    mapped: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue

        # Merge characteristics + finder facets (+ the full category path) into
        # attributes, which feed the embedding text and the refine chips.
        attributes: Dict[str, Any] = {}
        for src in ("characteristics", "finder_facets"):
            if isinstance(it.get(src), dict):
                attributes.update(it[src])
        if it.get("categories"):
            attributes["categories"] = it["categories"]

        # Prefer the numeric article id — it equals the scraped JSON-LD sku, so
        # imports update the scraper's records instead of creating duplicates.
        product_id = it.get("id") if it.get("id") is not None else it.get("sku")
        mapped.append({
            "product_id": str(product_id) if product_id is not None else None,
            "name": it.get("name"),
            "description": it.get("short_description") or "",
            "category": _category(it.get("categories")),
            "brand": _brand(it.get("name")),
            "price": _price(it.get("price_eur_gross")),
            # No image in the finder export today; supported if a future export adds one.
            "image_url": it.get("image") or it.get("image_url"),
            "product_url": it.get("url"),
            "attributes": attributes or None,
        })

    # Only keep rows that have the minimum needed to index and display.
    return [p for p in mapped if p["product_id"] and p["name"]]


def enrich_from_jtl(db, items: List[Dict[str, Any]]) -> Dict[str, int]:
    """Enrich EXISTING products with JTL finder variant data (characteristics +
    finder_facets: colours, Montageart, material, ...).

    The scraper only sees the default variant's JSON-LD, so colour options like
    "Anthrazit" are invisible to search without this. Matching is by the finder
    numeric id (== scraped JSON-LD sku), the finder sku string, or the product
    URL. Scraper-authoritative fields (name/description/price/category/image)
    are NEVER overwritten — only attributes are merged and missing links filled.
    Products whose attributes changed are flagged indexed=0 for re-embedding.
    """
    from app.models.product import Product  # local import avoids cycles

    stats = {"matched": 0, "attrs_updated": 0, "url_filled": 0, "not_found": 0}

    # Build lookups once.
    products = db.query(Product).all()
    by_id = {p.product_id: p for p in products}
    by_url = {p.product_url: p for p in products if p.product_url}

    for it in items:
        if not isinstance(it, dict):
            continue
        candidates = [str(it["id"])] if it.get("id") is not None else []
        if it.get("sku"):
            candidates.append(str(it["sku"]))
        target = next((by_id[c] for c in candidates if c in by_id), None)
        if target is None and it.get("url"):
            target = by_url.get(it["url"])
        if target is None:
            stats["not_found"] += 1
            continue

        stats["matched"] += 1

        incoming: Dict[str, Any] = {}
        for src in ("characteristics", "finder_facets"):
            if isinstance(it.get(src), dict):
                incoming.update(it[src])
        if it.get("categories"):
            incoming["categories"] = it["categories"]

        if incoming:
            current = target.attributes if isinstance(target.attributes, dict) else {}
            merged = dict(current)
            merged.update(incoming)  # finder data wins for facet keys (richer)
            if merged != current:
                target.attributes = merged
                target.indexed = 0
                stats["attrs_updated"] += 1

        if not target.product_url and it.get("url"):
            target.product_url = it["url"]
            stats["url_filled"] += 1

    db.commit()
    return stats
