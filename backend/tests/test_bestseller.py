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
