from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fusion.axes import audio_social_context as asc
from fusion.belief_state import AxisEstimate


class _Cur:
    def __init__(self, rows): self._rows = rows
    def execute(self, *a, **k): pass
    def fetchone(self): return self._rows[0] if self._rows else None
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Conn:
    def __init__(self, rows): self._rows = rows
    def cursor(self): return _Cur(self._rows)
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_with_other_when_latest_packet_has_other(monkeypatch):
    now = datetime.now(timezone.utc)
    # latest packet payload speaker='both', recorded_at=now
    monkeypatch.setattr(asc, "get_conn",
                        lambda: _Conn([({"speaker": "both"}, now)]))
    est = asc.fuse_recent(user_id="u1", now=now)
    assert isinstance(est, AxisEstimate)
    assert est.axis == "audio_social_context"
    assert est.value == {"category": "with_other"}


def test_alone_when_latest_self(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(asc, "get_conn",
                        lambda: _Conn([({"speaker": "self"}, now)]))
    est = asc.fuse_recent(user_id="u1", now=now)
    assert est.value == {"category": "alone"}


def test_none_when_no_packets(monkeypatch):
    monkeypatch.setattr(asc, "get_conn", lambda: _Conn([]))
    assert asc.fuse_recent(user_id="u1") is None
