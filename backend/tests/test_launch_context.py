"""Tests for launch-context helpers (Zalando teardown #3)."""
from types import SimpleNamespace
from app.services.rag import _product_to_dict, _anchor_note


def _fake_product(**kw):
    base = dict(product_id="P1", name="Briefkasten Hoffmann", description="d",
                category="Briefkästen", brand="Metzler", price=79.99,
                image_url="http://x/i.jpg", product_url="http://x/p", attributes={"Farbe": ["Anthrazit"]},
                bestseller_rank=3)
    base.update(kw)
    return SimpleNamespace(**base)


def test_product_to_dict_maps_retrieval_shape():
    d = _product_to_dict(_fake_product(), score=0.87)
    assert d["product_id"] == "P1"
    assert d["name"] == "Briefkasten Hoffmann"
    assert d["bestseller_rank"] == 3
    assert d["score"] == 0.87
    # must carry the fields retrieval._format produces, so it can join candidates
    for k in ("description", "category", "brand", "price", "image_url", "product_url", "attributes"):
        assert k in d


def test_product_to_dict_default_score_and_missing_rank():
    p = _fake_product()
    del p.bestseller_rank  # simulate a product without the attribute
    d = _product_to_dict(p)
    assert d["score"] == 1.0
    assert d["bestseller_rank"] is None


def test_anchor_note_names_the_product_and_id():
    note = _anchor_note("Briefkasten Hoffmann", "P1")
    assert "Briefkasten Hoffmann" in note and "P1" in note
    assert note.endswith("] ")  # prefix form, ready to prepend to the message
