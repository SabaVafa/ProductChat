"""Tests for the bestseller tie-break reaching the user (finding C-1).

The retrieval layer applies a relevance-gated banded tie-break, but the chat
path rebuilds the final list from the LLM's own order/selection and the LLM
never sees bestseller_rank. These tests pin the intended behavior: among the
LLM's SELECTED products, a genuine bestseller must lead when the picks are
comparably relevant — WITHOUT a clearly-more-relevant pick ever being demoted.
"""
from app.services.rag import _order_recommendations


def _prod(pid, score, rank=None):
    return {
        "product_id": pid, "name": pid, "description": "", "price": 1.0,
        "image_url": "", "product_url": "", "brand": "", "attributes": None,
        "score": score, "bestseller_rank": rank,
    }


def test_bestseller_leads_among_comparably_relevant_picks():
    # Two equally-relevant products (same ~0.80 score tier); one is a strong
    # bestseller (rank 3), one is unranked. The LLM, blind to rank, listed the
    # unranked one first.
    retrieved = [_prod("UNRANKED", 0.805, None), _prod("BESTSELLER", 0.800, 3)]
    recs = [
        {"product_id": "UNRANKED", "reason": "x", "score": 0.9},
        {"product_id": "BESTSELLER", "reason": "y", "score": 0.9},
    ]
    ids = [p["id"] for p in _order_recommendations(recs, retrieved)]
    assert ids[0] == "BESTSELLER", f"expected the bestseller to lead, got {ids}"


def test_more_relevant_pick_is_not_demoted_by_popularity():
    # Relevance gate: a clearly-more-relevant product (higher score tier) must
    # stay first even against a rank-1 bestseller in a lower tier.
    retrieved = [_prod("RELEVANT", 0.86, None), _prod("POPULAR", 0.70, 1)]
    recs = [
        {"product_id": "RELEVANT", "reason": "x", "score": 0.9},
        {"product_id": "POPULAR", "reason": "y", "score": 0.9},
    ]
    ids = [p["id"] for p in _order_recommendations(recs, retrieved)]
    assert ids[0] == "RELEVANT", f"relevance must win across tiers, got {ids}"


def test_api_shape_is_unchanged_and_internal_keys_do_not_leak():
    out = _order_recommendations(
        [{"product_id": "A", "reason": "r", "score": 0.5}], [_prod("A", 0.8, 2)]
    )
    assert set(out[0]) == {"id", "name", "price", "image", "url", "reason", "score"}


def test_hallucinated_ids_are_dropped():
    out = _order_recommendations(
        [{"product_id": "GHOST", "reason": "r", "score": 0.5}], [_prod("A", 0.8, 2)]
    )
    assert out == []


# --- capture hardening (H-1, H-2, L-1, robots/parsers) ---------------------
from app.services.bestsellers import (
    _stale_ranks_to_clear, BestsellerService, BASE_URL,
)
import app.services.bestsellers as bs


def test_partial_run_clears_nothing_H1():
    # A product that WAS ranked and is now missing would normally be cleared...
    prev = {"KEPT", "DROPPED"}
    ranked = {"KEPT"}
    # ...but on a partial run (a category fetch failed) we must clear NOTHING,
    # so a transient blip can never erase a real bestseller.
    assert _stale_ranks_to_clear(prev, ranked, partial=True) == set()
    # On a clean run the genuinely-dropped product is cleared as before.
    assert _stale_ranks_to_clear(prev, ranked, partial=False) == {"DROPPED"}


class _FakeResp:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text


def test_get_transient_failure_returns_none_and_counts(monkeypatch):
    monkeypatch.setattr(bs.time, "sleep", lambda *a, **k: None)  # no real backoff wait
    svc = BestsellerService(db=None)

    def boom(*a, **k):
        raise ConnectionError("network down")
    monkeypatch.setattr(svc.session, "get", boom)
    assert svc._get("http://x/y") is None
    assert svc._fetch_errors == 1          # transient failure => partial-run signal


def test_get_client_error_is_not_a_transient_failure(monkeypatch):
    svc = BestsellerService(db=None)
    monkeypatch.setattr(svc.session, "get", lambda *a, **k: _FakeResp(404))
    assert svc._get("http://x/missing") is None
    assert svc._fetch_errors == 0          # a 404 is definitive, not counted


def test_product_order_dedups_and_ignores_non_catalog():
    svc = BestsellerService(db=None)
    catalog = {f"{BASE_URL}/alpha", f"{BASE_URL}/beta"}
    html = (f'<a href="{BASE_URL}/alpha"></a><a href="{BASE_URL}/alpha"></a>'  # dup
            f'<a href="{BASE_URL}/beta"></a><a href="{BASE_URL}/not-a-product"></a>')
    assert svc._product_order(html, catalog) == [f"{BASE_URL}/alpha", f"{BASE_URL}/beta"]
    assert svc._product_order(None, catalog) == []  # None page is safe


def test_discover_excludes_products_and_cms_pages():
    svc = BestsellerService(db=None)
    catalog = {f"{BASE_URL}/some-product"}  # a real product, not a category
    html = (f'<a href="{BASE_URL}/briefkasten"></a>'          # category -> keep
            f'<a href="{BASE_URL}/some-product"></a>'         # in catalog -> drop
            f'<a href="{BASE_URL}/impressum"></a>'            # CMS -> drop
            f'<a href="{BASE_URL}/briefkasten"></a>')         # dup -> dedup
    import types
    svc._get = types.MethodType(lambda self, url: html, svc)  # avoid network
    assert svc.discover_category_urls(catalog) == [f"{BASE_URL}/briefkasten"]


# --- pure tie-break math (H-3) ---------------------------------------------
from app.services.retrieval import _bestseller_band, _apply_bestseller_tiebreak


def test_bestseller_band_thresholds():
    assert [_bestseller_band(r) for r in (None, 1, 5, 6, 15, 16, 50, 51)] == \
        [4, 0, 0, 1, 1, 2, 2, 3]


def test_tiebreak_relative_tiers_not_absolute_grid():
    # Two near-identical scores that straddle a fixed 0.02 grid line (0.8399 vs
    # 0.8401) must still count as the SAME relevance tier, so popularity can
    # break the tie — the old absolute-grid logic split them and could not.
    products = [
        {"product_id": "hi_unranked", "score": 0.8401, "bestseller_rank": None},
        {"product_id": "lo_bestseller", "score": 0.8399, "bestseller_rank": 2},
    ]
    out = [p["product_id"] for p in _apply_bestseller_tiebreak(products)]
    assert out[0] == "lo_bestseller", out


def test_tiebreak_never_crosses_relevance_tiers():
    products = [
        {"product_id": "relevant", "score": 0.90, "bestseller_rank": None},
        {"product_id": "popular_but_distant", "score": 0.70, "bestseller_rank": 1},
    ]
    out = [p["product_id"] for p in _apply_bestseller_tiebreak(products)]
    assert out[0] == "relevant", out
