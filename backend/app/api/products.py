from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.database import get_db
from app.models.product import Product
from typing import Dict, Any, Optional, List
from collections import Counter, defaultdict
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["products"])


def _serialize(p: Product) -> Dict[str, Any]:
    """Full record — this is what the Explorer shows as raw JSON."""
    return {
        "product_id": p.product_id,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "brand": p.brand,
        "price": p.price,
        "image_url": p.image_url,
        "product_url": p.product_url,
        "attributes": p.attributes,
        "source": p.source,
        "lastmod": p.lastmod,
        "content_hash": p.content_hash,
        "indexed": bool(p.indexed),
    }


def _apply_filters(q, search, category, brand, source, indexed, min_price, max_price):
    if category:
        q = q.filter(Product.category == category)
    if brand:
        q = q.filter(Product.brand == brand)
    if source:
        q = q.filter(Product.source == source)
    if indexed is not None:
        q = q.filter(Product.indexed == (1 if indexed else 0))
    if min_price is not None:
        q = q.filter(Product.price >= min_price)
    if max_price is not None:
        q = q.filter(Product.price <= max_price)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Product.name.ilike(like),
            Product.description.ilike(like),
            Product.brand.ilike(like),
            Product.product_id.ilike(like),
        ))
    return q


@router.get("/products", response_model=Dict[str, Any])
async def list_products(
    search: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    source: Optional[str] = None,
    indexed: Optional[bool] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    limit: int = Query(24, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Filterable, paginated product list. Records are returned in full so the
    Explorer can render them as raw JSON."""
    q = _apply_filters(
        db.query(Product), search, category, brand, source, indexed, min_price, max_price
    )
    total = q.count()
    rows = q.order_by(Product.category, Product.name).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "products": [_serialize(p) for p in rows],
    }


@router.get("/categories", response_model=Dict[str, Any])
async def list_categories(db: Session = Depends(get_db)):
    """Distinct categories with product counts (storefront tabs/filters)."""
    rows = (
        db.query(Product.category, func.count(Product.id))
        .filter(Product.category.isnot(None))
        .group_by(Product.category)
        .order_by(Product.category)
        .all()
    )
    total = db.query(func.count(Product.id)).scalar() or 0
    return {
        "categories": [{"name": name, "count": count} for name, count in rows],
        "total": total,
    }


def _group_counts(db: Session, column) -> List[Dict[str, Any]]:
    rows = (
        db.query(column, func.count(Product.id))
        .group_by(column)
        .order_by(func.count(Product.id).desc())
        .all()
    )
    return [{"value": v if v is not None else "(none)", "count": c} for v, c in rows]


@router.get("/facets", response_model=Dict[str, Any])
async def facets(db: Session = Depends(get_db)):
    """Aggregated view of the catalog: the groups/topics products are built from.

    Returns group-by counts for category / brand / source / indexed, price
    statistics with buckets, and the attribute keys + their most common values
    (the 'topics' attached to products).
    """
    total = db.query(func.count(Product.id)).scalar() or 0

    # Price stats + buckets.
    prices = [p for (p,) in db.query(Product.price).filter(Product.price.isnot(None)).all()]
    price_stats: Dict[str, Any] = {"count": len(prices)}
    price_buckets: List[Dict[str, Any]] = []
    if prices:
        price_stats.update({
            "min": min(prices),
            "max": max(prices),
            "avg": round(sum(prices) / len(prices), 2),
        })
        edges = [0, 50, 100, 200, 350, 500, 1000, float("inf")]
        labels = ["< €50", "€50–100", "€100–200", "€200–350", "€350–500", "€500–1000", "€1000+"]
        counts = [0] * len(labels)
        for p in prices:
            for i in range(len(labels)):
                if edges[i] <= p < edges[i + 1]:
                    counts[i] += 1
                    break
        price_buckets = [
            {"range": l, "count": c} for l, c in zip(labels, counts) if c > 0
        ]

    # Attribute keys + top values ("topics" used by products).
    attr_key_counts: Counter = Counter()
    attr_values: Dict[str, Counter] = defaultdict(Counter)
    for (attrs,) in db.query(Product.attributes).filter(Product.attributes.isnot(None)).all():
        if isinstance(attrs, dict):
            for k, v in attrs.items():
                attr_key_counts[k] += 1
                attr_values[k][str(v)] += 1
        elif isinstance(attrs, list):
            for v in attrs:
                attr_key_counts[str(v)] += 1

    attributes = [
        {
            "key": key,
            "count": count,
            "top_values": [
                {"value": val, "count": vc}
                for val, vc in attr_values[key].most_common(6)
            ],
        }
        for key, count in attr_key_counts.most_common(30)
    ]

    indexed_count = db.query(func.count(Product.id)).filter(Product.indexed == 1).scalar() or 0

    return {
        "total": total,
        "indexed": indexed_count,
        "not_indexed": total - indexed_count,
        "groups": {
            "category": _group_counts(db, Product.category),
            "brand": _group_counts(db, Product.brand),
            "source": _group_counts(db, Product.source),
        },
        "price": {"stats": price_stats, "buckets": price_buckets},
        "attributes": attributes,
    }
