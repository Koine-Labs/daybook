"""Tests for the L3 state_declared axis."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fusion.axes import state_declared
from labels import LabelSource


def _snap(*, kind: str = "state_declaration", classifier: str = "quickpick", claims=None):
    feats = {
        "claims": claims if claims is not None else [{"axis": "fatigue", "value": 0.9, "confidence": 0.85}],
        "raw_text": "I'm exhausted",
        "classifier": classifier,
    }
    return SimpleNamespace(
        payload={"kind": kind, "features": feats},
        timestamp=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
        user_id="u1",
    )


def test_fuse_belief_shape_and_provenance():
    est = state_declared.fuse_from_feature(_snap())
    assert est is not None
    assert est.axis == "state_declared"
    assert est.value["raw_text"] == "I'm exhausted"
    assert est.value["claims"][0]["axis"] == "fatigue"
    assert est.value["scaffold"] is False
    assert est.value["classifier"] == "quickpick"
    assert est.confidence == 0.9
    assert est.source == LabelSource.SELF_REPORT.value
    assert est.meta_context == "waking"


def test_fuse_ignores_non_declaration_kind():
    assert state_declared.fuse_from_feature(_snap(kind="audio_prosody")) is None


def test_fuse_ignores_features_without_claims():
    snap = SimpleNamespace(
        payload={"kind": "state_declaration", "features": {"raw_text": "x"}},
        timestamp=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
        user_id="u1",
    )
    assert state_declared.fuse_from_feature(snap) is None


def test_fuse_ignores_empty_claims_list():
    """An empty claims list is OFFLINE (None), never a hollow persisted belief (BUG)."""
    assert state_declared.fuse_from_feature(_snap(claims=[])) is None
