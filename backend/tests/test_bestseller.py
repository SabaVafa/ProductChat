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


def test_api_shape_is_stable_and_internal_keys_do_not_leak():
    out = _order_recommendations(
        [{"product_id": "A", "reason": "r", "score": 0.5}], [_prod("A", 0.8, 2)]
    )
    assert set(out[0]) == {"id", "name", "price", "image", "url", "reason", "score",
                           "popular", "has_variants"}


def test_popular_flag_only_for_top_band_bestsellers():
    def card(rank):
        return _order_recommendations(
            [{"product_id": "A", "reason": "r", "score": 0.5}], [_prod("A", 0.8, rank)]
        )[0]
    assert card(3)["popular"] is True        # top band
    assert card(15)["popular"] is True       # band boundary
    assert card(16)["popular"] is False      # below the honest "Beliebt" bar
    assert card(None)["popular"] is False    # unranked


def test_has_variants_flag_from_attribute_option_lists():
    def card(attrs):
        p = _prod("A", 0.8, None)
        p["attributes"] = attrs
        return _order_recommendations(
            [{"product_id": "A", "reason": "r", "score": 0.5}], [p]
        )[0]
    assert card({"Farbe": ["Anthrazit", "Edelstahl"]})["has_variants"] is True
    assert card({"Farbe": ["Anthrazit"]})["has_variants"] is False   # single option ≠ variant choice
    assert card({})["has_variants"] is False
    assert card(None)["has_variants"] is False


from app.services.rag import _apply_negation_filter


def test_negation_filter_drops_headlined_feature_keeps_optional():
    prods = [
        {"name": "Metzler Briefkasten Design | Modell-G"},              # plain -> keep
        {"name": "Metzler Briefkasten mit Lasergravur | Stencil"},     # gravur -> drop
        {"name": "Metzler Briefkasten Edelstahl Gravur optional | Moris"},  # optional -> keep
        {"name": "Metzler Briefkasten Unterputz | personalisiert mit Gravur"},  # gravur -> drop
        {"name": "Metzler Briefkasten aus Edelstahl | personalisiert"},  # plain -> keep
    ]
    for msg in ["Briefkasten ohne Gravur", "without gravur", "ohne Gravur bitte"]:
        names = [p["name"] for p in _apply_negation_filter(prods, msg)]
        assert not any("lasergravur" in n.lower() for n in names), (msg, names)
        assert not any("personalisiert mit gravur" in n.lower() for n in names), (msg, names)
        assert any("Modell-G" in n for n in names) and any("optional" in n.lower() for n in names)


def test_negation_optional_must_qualify_the_negated_term_not_another_feature():
    # Real bug: "... mit Gravur | Zeitungsfach optional ..." has the Gravur
    # INCLUDED; the "optional" belongs to the newspaper slot, not the gravur.
    # A stray "optional" elsewhere must not rescue a "mit Gravur" product.
    prods = [
        {"name": "Metzler Briefkasten aus Edelstahl | personalisiert mit Gravur | Zeitungsfach optional | Moris"},
        {"name": "Metzler Briefkasten Edelstahl Gravur optional | Modell02"},  # gravur itself optional -> keep
    ]
    names = [p["name"] for p in _apply_negation_filter(prods, "without gravur")]
    assert not any("mit Gravur" in n for n in names), names   # dropped
    assert any("Modell02" in n for n in names)                # gravur-optional kept


def test_negation_filter_noop_without_negation():
    prods = [{"name": "Briefkasten mit Gravur A"}, {"name": "Briefkasten mit Gravur B"}]
    # no negation in the message -> unchanged
    assert _apply_negation_filter(prods, "Briefkasten mit Gravur") == prods


def test_negation_filter_drops_all_excluded_rather_than_showing_them():
    # If EVERY retrieved product headlines the excluded feature (e.g. query
    # understanding drifted to nameplates, which all carry "Gravur"), returning
    # an empty set routes to the German no-results/offer-to-broaden path.
    # Showing the excluded products instead is the drift-to-nameplates bug.
    prods = [{"name": "Namensschild mit Lasergravur"}, {"name": "Hausnummernschild mit Gravur"}]
    assert _apply_negation_filter(prods, "ohne Gravur") == []


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


def test_discover_handles_uppercase_relative_and_nested_slugs():
    # Audit finding: the old regex silently missed /Paketboxen (uppercase),
    # href="/topshop" (relative) and nested category paths — real JTL shapes.
    svc = BestsellerService(db=None)
    html = (f'<a href="{BASE_URL}/Paketboxen"></a>'                    # uppercase -> keep
            '<a href="/topshop"></a>'                                  # relative -> keep
            f'<a href="{BASE_URL}/garten/beleuchtung"></a>'            # nested -> keep
            f'<a href="{BASE_URL}/paketboxen"></a>'                    # case-dup -> dedup
            f'<a href="{BASE_URL}/media/image/product/1/x.jpg"></a>'   # asset -> drop
            '<a href="//evil.example/x"></a>')                         # protocol-relative -> drop
    import types
    svc._get = types.MethodType(lambda self, url: html, svc)
    assert svc.discover_category_urls(set()) == [
        f"{BASE_URL}/Paketboxen", f"{BASE_URL}/topshop", f"{BASE_URL}/garten/beleuchtung",
    ]


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
