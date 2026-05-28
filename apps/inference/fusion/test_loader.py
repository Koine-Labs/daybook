from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fusion.belief_state import BeliefState
from fusion.loader import load_belief_state


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_a, **_k):
        return None

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_load_belief_state_builds_axis_estimates(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        ("meta_context", {"category": "waking/focused"}, 0.8, "L3.fusion.meta_context", now, "waking/focused", None),
        ("sleep_stage", {"label": "rem", "prob": 0.7}, 0.7, "classifier.binary_rem", now, None, None),
    ]
    monkeypatch.setattr("fusion.loader.get_conn", lambda: _FakeConn(rows))

    belief = load_belief_state("user-123", now=now)

    assert isinstance(belief, BeliefState)
    assert belief.user_id == "user-123"
    meta = belief.get("meta_context", now=now)
    assert meta is not None
    assert meta.value == {"category": "waking/focused"}
    assert meta.source == "L3.fusion.meta_context"
    assert meta.meta_context == "waking/focused"


def test_load_belief_state_empty_returns_empty_belief(monkeypatch):
    monkeypatch.setattr("fusion.loader.get_conn", lambda: _FakeConn([]))
    belief = load_belief_state("user-123")
    assert isinstance(belief, BeliefState)
    assert belief.estimates == {}
