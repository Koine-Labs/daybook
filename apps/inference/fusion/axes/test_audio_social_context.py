from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from features.snapshot import FeatureSnapshot
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


# --- live fusion from an L2 FeatureSnapshot (no DB) --------------------------

def _feature(payload: dict) -> FeatureSnapshot:
    return FeatureSnapshot(
        user_id="u1",
        timestamp=datetime.now(timezone.utc),
        modality="audio",
        source="mic_listener_v1",
        payload=payload,
    )


def test_fuse_from_feature_with_other():
    now = datetime.now(timezone.utc)
    packet = _feature({"kind": "audio_social_context",
                       "social_category": "with_other", "speaker": "both"})
    est = asc.fuse_from_feature(packet, now=now)
    assert isinstance(est, AxisEstimate)
    assert est.value == {"category": "with_other"}
    assert est.confidence == 0.8
    assert est.source.endswith(".live")


def test_fuse_from_feature_alone():
    packet = _feature({"kind": "audio_social_context",
                       "social_category": "alone", "speaker": "self"})
    assert asc.fuse_from_feature(packet).value == {"category": "alone"}


def test_fuse_from_feature_derives_category_from_speaker_when_missing():
    packet = _feature({"kind": "audio_social_context", "speaker": "other"})
    assert asc.fuse_from_feature(packet).value == {"category": "with_other"}


def test_fuse_from_feature_ignores_non_audio_kind():
    packet = _feature({"kind": "mac_activity", "active_app": "Cursor"})
    assert asc.fuse_from_feature(packet) is None
