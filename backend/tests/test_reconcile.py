"""Reconciliation safeguard: detect DB↔Qdrant gaps and re-flag them for repair.

Silent index-loss = a product flagged indexed in the DB but absent from Qdrant,
which makes a whole category return nothing. reconcile() must re-flag such
products for re-index, while never resurrecting a product parked (-1) after
repeated failures — otherwise a broken product loops forever on the quota.
"""
from app.services.indexing import IndexingService


class _P:
    def __init__(self, pid, indexed=1, attempts=0):
        self.product_id = pid
        self.indexed = indexed
        self.index_attempts = attempts


class _FakeQuery:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)


class _FakeDB:
    def __init__(self, rows): self._rows = rows; self.commits = 0
    def query(self, *_): return _FakeQuery(self._rows)
    def commit(self): self.commits += 1
    def add(self, *_): pass


class _FakeQdrant:
    def __init__(self, ids): self._ids = ids
    def all_indexed_product_ids(self): return set(self._ids)


def _svc(rows, qdrant_ids, monkeypatch):
    svc = IndexingService.__new__(IndexingService)          # bypass __init__ (no network)
    svc.db = _FakeDB(rows)
    svc.qdrant = _FakeQdrant(qdrant_ids)
    monkeypatch.setattr("app.services.ops.record_operation", lambda *a, **k: None)
    return svc


def test_health_reports_missing_and_parked(monkeypatch):
    rows = [_P("a", 1), _P("b", 1), _P("c", -1)]          # b missing, c missing+parked
    svc = _svc(rows, {"a"}, monkeypatch)
    h = svc.health()
    assert h["ok"] is False
    assert h["db_count"] == 3 and h["qdrant_count"] == 1
    assert h["missing_count"] == 2            # b and c
    assert h["parked_count"] == 1             # c


def test_reconcile_reflags_missing_but_not_parked(monkeypatch):
    a, b, c = _P("a", 1), _P("b", 1), _P("c", -1)
    svc = _svc([a, b, c], {"a"}, monkeypatch)
    res = svc.reconcile(trigger_repair=False)
    assert res["reflagged_for_reindex"] == 1          # only b
    assert res["parked_persistent_failures"] == 1     # c reported, not touched
    assert b.indexed == 0                             # b queued for re-index
    assert c.indexed == -1                            # c left parked (no loop)
    assert a.indexed == 1                             # a untouched


def test_reconcile_noop_when_consistent(monkeypatch):
    rows = [_P("a", 1), _P("b", 1)]
    svc = _svc(rows, {"a", "b"}, monkeypatch)
    res = svc.reconcile(trigger_repair=False)
    assert res["missing_count"] == 0 and res["reflagged_for_reindex"] == 0


def test_health_handles_qdrant_read_failure(monkeypatch):
    svc = IndexingService.__new__(IndexingService)
    svc.db = _FakeDB([_P("a", 1)])
    svc.qdrant = type("Q", (), {"all_indexed_product_ids": lambda self: None})()
    h = svc.health()
    assert h["ok"] is False and "error" in h          # not mistaken for "all missing"
