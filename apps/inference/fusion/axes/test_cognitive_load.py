"""L3 cognitive_load axis unit tests — pure, DB-free.

Mirrors test_audio_social_context.py's fuse_from_feature block. Asserts the
heuristic responds to band content and carries honest scaffold provenance.
"""
from __future__ import annotations

from datetime import datetime, timezone

from features.snapshot import FeatureSnapshot
from fusion.axes import cognitive_load as cl
from fusion.belief_state import AxisEstimate


def _feature(features: dict, *, kind: str = "eeg_bandpower") -> FeatureSnapshot:
    return FeatureSnapshot(
        user_id="u1",
        timestamp=datetime.now(timezone.utc),
        modality="bci",
        source="eeg_edge_v1",
        payload={"kind": kind, "features": features},
    )


def test_high_engagement_yields_medium_or_high_load():
    now = datetime.now(timezone.utc)
    est = cl.fuse_from_feature(
        _feature({"engagement_index": 0.9, "theta_beta_ratio": 0.4, "alpha_power": 0.2}),
        now=now,
    )
    assert isinstance(est, AxisEstimate)
    assert est.axis == "cognitive_load"
    assert 0.0 <= est.value["load"] <= 1.0
    assert est.value["band"] in {"medium", "high"}
    assert est.value["scaffold"] is True
    assert est.value["method"] == "engagement_index_linear_v1"
    assert est.confidence == 0.4
    assert est.meta_context == "waking"
    assert est.source.endswith("v1_heuristic")


def test_low_engagement_yields_low_band_and_lower_load():
    high = cl.fuse_from_feature(_feature({"engagement_index": 0.9}))
    low = cl.fuse_from_feature(_feature({"engagement_index": 0.12}))
    assert low.value["band"] == "low"
    assert low.value["load"] < high.value["load"]


def test_engagement_clamped_to_unit_interval():
    huge = cl.fuse_from_feature(_feature({"engagement_index": 5.0}))
    tiny = cl.fuse_from_feature(_feature({"engagement_index": -1.0}))
    assert huge.value["load"] == 1.0
    assert tiny.value["load"] == 0.0


def test_non_eeg_kind_returns_none():
    assert cl.fuse_from_feature(_feature({"engagement_index": 0.9}, kind="mac_activity")) is None


def test_missing_engagement_returns_none():
    assert cl.fuse_from_feature(_feature({"theta_beta_ratio": 0.4})) is None


def test_none_engagement_returns_none():
    assert cl.fuse_from_feature(_feature({"engagement_index": None})) is None
