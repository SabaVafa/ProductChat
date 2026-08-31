"""Tests for the 'ohne Gravur' category-membership capture.

The capture's whole value is resolving a category-listing product URL to a
catalog product_id even when the listing links a *variant* URL our catalog
stored under a different canonical URL (the URL-alias gap). These pin the three
resolution paths (url -> slug -> data-product-id) and the never-empty-on-partial
safety, without hitting the network.
"""
import types
from app.services.gravur import GravurService, BASE_URL

B = BASE_URL


def _svc():
    return GravurService(db=None)


def test_resolver_matches_by_exact_url():
    svc = _svc()
    by_url = {f"{B}/metzler-briefkasten-hoffmann": "100"}
    assert svc._resolve_to_product_id(f"{B}/metzler-briefkasten-hoffmann", by_url, {}, {"100"}) == "100"


def test_resolver_matches_by_slug_when_url_differs():
    svc = _svc()
    by_slug = {"metzler-briefkasten-hoffmann": "100"}
    # trailing slash / different host prefix still resolves via the last path segment
    assert svc._resolve_to_product_id(f"{B}/metzler-briefkasten-hoffmann/", {}, by_slug, {"100"}) == "100"


def test_resolver_bridges_url_alias_via_product_id():
    # The listing links a variant URL we don't have; the product page prints the
    # JTL id, which IS in our catalog -> resolve by id.
    svc = _svc()
    svc._get = types.MethodType(
        lambda self, url: '<div data-product-id="42877">…</div>', svc)
    pid = svc._resolve_to_product_id(
        f"{B}/metzler-briefkasten-aus-hochwertigem-stahl-lepo", {}, {}, {"42877"})
    assert pid == "42877"


def test_resolver_ignores_non_product_links():
    # A nav/CMS link (no product slug hint) is never fetched or resolved.
    svc = _svc()
    svc._get = types.MethodType(lambda self, url: (_ for _ in ()).throw(AssertionError("should not fetch")), svc)
    assert svc._resolve_to_product_id(f"{B}/metzler-garantieerklaerung", {}, {}, {"1"}) is None


def test_resolver_id_not_in_catalog_is_rejected():
    svc = _svc()
    svc._get = types.MethodType(lambda self, url: 'data-product-id="99999"', svc)
    assert svc._resolve_to_product_id(f"{B}/metzler-briefkasten-ghost", {}, {}, {"100"}) is None


def test_members_collects_and_dedups_across_pages():
    svc = _svc()
    page1 = (f'<a href="{B}/metzler-briefkasten-hoffmann"></a>'
             f'<a href="{B}/metzler-briefkasten-hugo"></a>'
             f'<a href="{B}/impressum"></a>')          # non-product -> ignored
    page2 = f'<a href="{B}/metzler-briefkasten-hoffmann"></a>'  # dup -> no new products -> stop
    pages = {f"{B}/briefkasten-ohne-gravur": page1,
             f"{B}/briefkasten-ohne-gravur?seite=2": page2}
    svc._get = types.MethodType(lambda self, url: pages.get(url), svc)
    by_url = {f"{B}/metzler-briefkasten-hoffmann": "100", f"{B}/metzler-briefkasten-hugo": "101"}
    ids = svc._members(f"{B}/briefkasten-ohne-gravur", by_url, {}, {"100", "101"})
    assert ids == {"100", "101"}
