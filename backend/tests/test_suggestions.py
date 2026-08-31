"""Default starter chips must span product categories, not collapse onto one.

Regression test for the widget showing five doorbell questions and nothing else.
The guarantee is structural (one-per-family + template backfill), so it must
hold even when the cached LLM global list is skewed to a single category.
"""
from app.services.suggestions import SuggestionsService


class _FakeQuery:
    def __init__(self, rows): self._rows = rows
    def distinct(self): return self
    def filter(self, *a, **k): return self
    def all(self): return self._rows


class _FakeDB:
    def __init__(self, cats): self._cats = cats
    def query(self, *a, **k): return _FakeQuery([(c,) for c in self._cats])


CATS = ["Türklingeln", "Briefkästen", "Sprechanlagen", "Paketboxen",
        "Hausnummern", "Außenleuchten", "Funkklingeln", "Zubehör"]


def _svc(global_qs):
    svc = SuggestionsService.__new__(SuggestionsService)     # bypass DB __init__
    svc.db = _FakeDB(CATS)
    svc._get_cached_llm_questions = lambda: global_qs
    svc.build_template_suggestions = lambda category=None: (
        [f"Zeig mir alle {category}"] if category else [])
    return svc


def _families(svc, chips):
    return {svc._family_of(c) for c in chips}


def test_diverse_global_keeps_one_per_family():
    svc = _svc([
        "Welche Türklingel passt zu meinem Haus?",
        "Briefkasten mit Zeitungsfach?",
        "Sprechanlage mit Video?",
        "Paketbox für große Pakete?",
        "Hausnummer aus Edelstahl?",
        "Außenleuchte mit LED?",
    ])
    chips = svc.get_suggestions(limit=6)
    fams = _families(svc, chips)
    assert {"Türklingeln", "Briefkästen", "Sprechanlagen", "Paketboxen",
            "Hausnummern", "Außenleuchten"} <= fams


def test_doorbell_skewed_global_is_still_diverse():
    # Worst case: the LLM returned six doorbell questions. The chips must NOT be
    # six doorbell chips — other families are backfilled from templates.
    svc = _svc([
        "Welche Türklingel passt?", "Funkklingel mit Gravur?", "LED-Klingel Sound?",
        "Türgong unter 50 €?", "Fingerprint-Klingel?", "Edelstahl-Klingel?",
    ])
    chips = svc.get_suggestions(limit=6)
    doorbell = [c for c in chips if svc._family_of(c) == "Türklingeln"]
    assert len(doorbell) == 1, chips                    # at most one doorbell chip
    assert len(_families(svc, chips)) >= 5, chips        # spans >= 5 families


def test_family_classifier_maps_known_terms():
    svc = _svc([])
    assert svc._family_of("Zeig mir alle Briefkästen") == "Briefkästen"
    assert svc._family_of("Sprechanlage mit Video?") == "Sprechanlagen"
    assert svc._family_of("Etwas ganz anderes") is None


from app.services.suggestions import _normalize_de


def test_normalize_capitalizes_standalone_colour_nouns():
    assert _normalize_de("Welche Außenleuchte passt zu anthrazit?") == \
        "Welche Außenleuchte passt zu Anthrazit?"
    assert _normalize_de("Edelstahl oder anthrazit?") == "Edelstahl oder Anthrazit?"
    assert _normalize_de("Briefkasten in weiß") == "Briefkasten in Weiß"
    assert _normalize_de("Warmweiß oder kaltweiß?") == "Warmweiß oder Kaltweiß?"


def test_normalize_leaves_inflected_adjectives_and_compounds_alone():
    # Inflected colour adjectives and colour-compounds are NOT nouns -> untouched.
    assert _normalize_de("eine weiße Klingel") == "eine weiße Klingel"
    assert _normalize_de("die schwarze Türklingel") == "die schwarze Türklingel"
    assert _normalize_de("Briefkasten in anthrazitgrau") == "Briefkasten in anthrazitgrau"


def test_default_chips_are_normalized(monkeypatch):
    svc = _svc(["Welche Leuchte passt zu anthrazit?", "Briefkasten in weiß?"])
    chips = svc.get_suggestions(limit=6)
    assert any("Anthrazit" in c for c in chips)
    assert not any("anthrazit?" in c for c in chips)   # no lower-case colour noun left
