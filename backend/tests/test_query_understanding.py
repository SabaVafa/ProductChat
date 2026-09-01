"""Category family-expansion: a family-head category must pull in its siblings.

Regression for "I need a bus system sprechanlage" returning security cameras:
understanding picked the near-empty head category "Sprechanlagen" (2 products),
so the filter matched almost nothing and retrieval fell back to an unfiltered
search that drifted to unrelated products.
"""
from app.services.query_understanding import _expand_category_families

CATS = [
    "Sprechanlagen", "Video Sprechanlagen", "Audio Sprechanlagen", "Sprechanlagen Sets",
    "Briefkasten mit Klingel & Sprechanlage", "IP Kameras", "Alarmanlagen",
    "Briefkästen", "Mehrfamilien Briefkästen",
]


def test_head_expands_to_sibling_subcategories():
    out = _expand_category_families(["Sprechanlagen"], CATS)
    assert "Video Sprechanlagen" in out and "Audio Sprechanlagen" in out and "Sprechanlagen Sets" in out
    # singular "…Sprechanlage" is NOT the plural token -> not pulled in
    assert "Briefkasten mit Klingel & Sprechanlage" not in out
    # unrelated families are never added
    assert "IP Kameras" not in out and "Alarmanlagen" not in out


def test_specific_subcategory_is_not_widened_back():
    # Asymmetric: an explicit sub-type stays narrow.
    out = _expand_category_families(["Video Sprechanlagen"], CATS)
    assert out == ["Video Sprechanlagen"]


def test_no_categories_stays_empty():
    assert _expand_category_families([], CATS) == []


def test_briefkaesten_head_expands():
    out = _expand_category_families(["Briefkästen"], CATS)
    assert "Mehrfamilien Briefkästen" in out
