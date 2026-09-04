"""In-process BM25 (lexical) index over the product catalog.

Dense vector search blurs exact terms — a specific token like "Unterputz" gets
diluted, so the flush-mount mailboxes that literally say "Unterputz Briefkasten"
can rank below generic mailboxes and drop out of the top-K. BM25 scores the
LITERAL token overlap, so it reliably surfaces those. The retrieval layer fuses
the two (hybrid search), behind the `enable_hybrid_search` setting.

Self-contained (pure stdlib, no new dependency, no Qdrant migration): the catalog
is tiny (~1.5k products), so a full BM25 pass in memory is microseconds. The index
is cached per process and rebuilt only when the product count changes.
"""

import math
import re
import threading
from collections import Counter
from typing import List, Tuple, Optional, Set

# Fold umlauts + lowercase so the index and the query tokenise identically
# ("Briefkästen" -> "briefkasten"); keep alphanumerics, drop 1-char noise.
_TRANS = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


def _tokenize(text: Optional[str]) -> List[str]:
    t = (text or "").lower().translate(_TRANS)
    return [w for w in re.findall(r"[a-z0-9]+", t) if len(w) >= 2]


class BM25Index:
    """Okapi BM25 over (product_id, category, tokens) documents."""

    def __init__(self, docs: List[Tuple[str, Optional[str], List[str]]], k1: float = 1.5, b: float = 0.75):
        self.pids = [d[0] for d in docs]
        self.cats = [d[1] for d in docs]
        self.doc_len = [len(d[2]) for d in docs]
        self.tf = [Counter(d[2]) for d in docs]
        self.N = len(docs)
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0
        self.k1 = k1
        self.b = b
        df: Counter = Counter()
        for _pid, _cat, toks in docs:
            for w in set(toks):
                df[w] += 1
        # BM25 idf (with the +1 so common terms stay non-negative).
        self.idf = {w: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for w, n in df.items()}

    def search(
        self, query: str, top_n: int = 10, allowed_categories: Optional[Set[str]] = None
    ) -> List[Tuple[str, float]]:
        """Return [(product_id, score)] best-first for docs with any query term.

        `allowed_categories` (exact category strings) keeps the lexical hits in the
        same product domain as the dense filter; None = search the whole catalog.
        """
        q = _tokenize(query)
        if not q or self.N == 0 or self.avgdl == 0:
            return []
        out: List[Tuple[str, float]] = []
        for i in range(self.N):
            if allowed_categories is not None and self.cats[i] not in allowed_categories:
                continue
            tf = self.tf[i]
            dl = self.doc_len[i]
            s = 0.0
            for w in q:
                f = tf.get(w)
                if f:
                    s += self.idf.get(w, 0.0) * (f * (self.k1 + 1)) / (
                        f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                    )
            if s > 0:
                out.append((self.pids[i], s))
        out.sort(key=lambda x: -x[1])
        return out[:top_n]


# ---- process-level cache (rebuilt when the catalog size changes) ------------
_lock = threading.Lock()
_cache = {"sig": None, "index": None}


def get_bm25_index(db) -> BM25Index:
    """Build (or reuse) the BM25 index from the current catalog."""
    from app.models.product import Product

    sig = db.query(Product).count()  # cheap signature: rebuild if the catalog grew/shrank
    cached = _cache["index"]
    if cached is not None and _cache["sig"] == sig:
        return cached
    with _lock:
        if _cache["index"] is not None and _cache["sig"] == sig:
            return _cache["index"]
        rows = db.query(
            Product.product_id, Product.name, Product.description,
            Product.attributes, Product.category,
        ).all()
        docs = [
            (pid, cat, _tokenize(f"{name or ''} {desc or ''} {attrs or ''} {cat or ''}"))
            for pid, name, desc, attrs, cat in rows
        ]
        idx = BM25Index(docs)
        _cache["sig"] = sig
        _cache["index"] = idx
        return idx
