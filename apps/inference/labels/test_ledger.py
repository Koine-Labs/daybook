from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels import ledger
from labels.provenance import LabelSource
from labels.record import LabelRecord

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _rec(axis: str = "fatigue") -> LabelRecord:
    return LabelRecord(
        user_id=DEFAULT_USER_ID,
        axis=axis,
        value=0.8,
        source=LabelSource.SELF_REPORT,
        observed_at=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
        confidence=0.9,
        provenance={"declaration_text": "wiped but wired", "classifier": "quickpick"},
        consent_scope="self_report_v1",
        meta_context="waking",
    )


class _FakeCursor:
    def __init__(self, store, rows):
        self._store = store
        self._rows = rows
        self._last = None

    def execute(self, sql, params=None):
        self._store.append((sql, params))
        self._last = (sql, params)

    def fetchone(self):
        return (str(uuid.uuid4()),)

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _FakeConn:
    def __init__(self, store, rows):
        self._store = store
        self._rows = rows
        self.committed = False

    def cursor(self):
        return _FakeCursor(self._store, self._rows)

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


# --- DB-free behaviour: get_conn raises (no DATABASE_URL) ---------------------

def test_record_label_returns_none_when_db_absent(monkeypatch):
    def _boom():
        raise RuntimeError("DATABASE_URL not set")

    monkeypatch.setattr(ledger, "get_conn", _boom)
    assert ledger.record_label(_rec()) is None


def test_read_labels_returns_empty_when_db_absent(monkeypatch):
    def _boom():
        raise RuntimeError("DATABASE_URL not set")

    monkeypatch.setattr(ledger, "get_conn", _boom)
    assert ledger.read_labels(DEFAULT_USER_ID) == []


def test_record_labels_counts_only_successful_writes(monkeypatch):
    def _boom():
        raise RuntimeError("DATABASE_URL not set")

    monkeypatch.setattr(ledger, "get_conn", _boom)
    assert ledger.record_labels([_rec("fatigue"), _rec("arousal")]) == 0


# --- DB-free behaviour: get_conn mocked to a fake conn -----------------------

def test_record_label_inserts_and_commits(monkeypatch):
    store: list = []
    conn = _FakeConn(store, [])
    monkeypatch.setattr(ledger, "get_conn", lambda: conn)

    new_id = ledger.record_label(_rec())
    assert new_id is not None
    assert conn.committed is True
    sql, params = store[0]
    assert "INSERT INTO label_observations" in sql
    # value + provenance are json-serialized, source is the enum's str value.
    assert params[4] == "self_report"
    assert params[0] == DEFAULT_USER_ID


def test_record_labels_returns_written_count(monkeypatch):
    store: list = []
    monkeypatch.setattr(ledger, "get_conn", lambda: _FakeConn(store, []))
    assert ledger.record_labels([_rec("fatigue"), _rec("arousal")]) == 2


class _CountingConn:
    """Fake conn that counts commit()/rollback() and how many conns get opened."""

    opened = 0

    def __init__(self, store):
        type(self)._opened()
        self._store = store
        self.commits = 0
        self.rollbacks = 0

    @classmethod
    def _opened(cls):
        cls.opened += 1

    def cursor(self):
        return _FakeCursor(self._store, [])

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_record_labels_commits_once_for_n_records(monkeypatch):
    store: list = []
    _CountingConn.opened = 0
    conn = _CountingConn(store)
    monkeypatch.setattr(ledger, "get_conn", lambda: conn)

    written = ledger.record_labels([_rec("fatigue"), _rec("arousal"), _rec("focus")])
    assert written == 3
    assert conn.commits == 1                 # ONE commit for the whole batch.
    assert _CountingConn.opened == 1         # ONE connection opened.
    assert len([s for s in store if "INSERT INTO label_observations" in s[0]]) == 3


def test_read_labels_skips_off_taxonomy_source_row(monkeypatch):
    observed = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    rows = [
        (DEFAULT_USER_ID, "fatigue", 0.8, 0.9, "self_report", {}, "self_report_v1", None, "waking", observed),
        (DEFAULT_USER_ID, "fatigue", 0.8, 0.9, "not_a_real_source", {}, "self_report_v1", None, "waking", observed),
    ]
    monkeypatch.setattr(ledger, "get_conn", lambda: _FakeConn([], rows))

    out = ledger.read_labels(DEFAULT_USER_ID)
    assert len(out) == 1                       # the bad row is skipped, not fatal.
    assert out[0].source is LabelSource.SELF_REPORT


def test_read_labels_rebuilds_records(monkeypatch):
    observed = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    rows = [
        (
            DEFAULT_USER_ID,
            "fatigue",
            0.8,
            0.9,
            "self_report",
            {"classifier": "quickpick"},
            "self_report_v1",
            None,
            "waking",
            observed,
        )
    ]
    monkeypatch.setattr(ledger, "get_conn", lambda: _FakeConn([], rows))

    out = ledger.read_labels(DEFAULT_USER_ID, axis="fatigue", sources=[LabelSource.SELF_REPORT])
    assert len(out) == 1
    rec = out[0]
    assert isinstance(rec, LabelRecord)
    assert rec.axis == "fatigue"
    assert rec.source is LabelSource.SELF_REPORT
    assert rec.observed_at == observed
    assert rec.meta_context == "waking"


def test_read_labels_builds_filtered_query(monkeypatch):
    store: list = []
    monkeypatch.setattr(ledger, "get_conn", lambda: _FakeConn(store, []))

    ledger.read_labels(
        DEFAULT_USER_ID,
        axis="arousal",
        sources=["self_report"],
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        limit=10,
    )
    sql, params = store[0]
    assert "axis = %s" in sql
    assert "source = ANY(%s)" in sql
    assert "observed_at >= %s" in sql
    assert "LIMIT %s" in sql
    assert params[-1] == 10


# --- DATABASE_URL-gated real round trip -------------------------------------

@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — real-DB smoke skipped",
)
def test_real_db_round_trip():
    rec = LabelRecord(
        user_id=DEFAULT_USER_ID,
        axis="__ledger_smoke__",
        value={"smoke": True},
        source=LabelSource.SELF_REPORT,
        observed_at=datetime.now(timezone.utc),
        confidence=0.99,
        provenance={"declaration_text": "smoke", "classifier": "quickpick"},
        consent_scope="self_report_v1",
        meta_context="waking",
    )
    new_id = ledger.record_label(rec)
    assert new_id is not None
    try:
        out = ledger.read_labels(DEFAULT_USER_ID, axis="__ledger_smoke__", limit=1)
        assert len(out) == 1
        assert out[0].axis == "__ledger_smoke__"
        assert out[0].source is LabelSource.SELF_REPORT
    finally:
        from db import get_conn

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM label_observations WHERE id = %s", (new_id,))
            conn.commit()
