"""L3 visual_context axis unit tests — pure, DB-free.

Mirrors test_cognitive_load.py's fuse_from_feature block. Asserts the heuristic
maps the semantic scene dict to a context estimate and carries honest scaffold
provenance, and returns None for any non-vision packet.
"""
from __future__ import annotations

from datetime import datetime, timezone

from features.snapshot import FeatureSnapshot
from fusion.axes import visual_context as vc
from fusion.belief_state import AxisEstimate


def _feature(semantics: dict, features: dict, *, kind: str = "visual_scene") -> FeatureSnapshot:
    return FeatureSnapshot(
        user_id="u1",
        timestamp=datetime.now(timezone.utc),
        modality="vision",
        source="camera.visual_scene",
        payload={"kind": kind, "semantics": semantics, "features": features},
    )


def test_with_people_yields_with_people_category():
    now = datetime.now(timezone.utc)
    est = vc.fuse_from_feature(
        _feature(
            {"setting": "indoor", "salient_objects": ["person", "laptop"]},
            {"people_present": True, "crowd_size": "few"},
        ),
        now=now,
    )
    assert isinstance(est, AxisEstimate)
    assert est.axis == "visual_context"
    assert est.value["setting"] == "indoor"
    assert est.value["people_present"] is True
    assert est.value["category"] == "with_people"
    assert est.value["salient_objects"] == ["person", "laptop"]
    assert est.value["method"] == "scene_mapping_v1"
    assert est.value["scaffold"] is True
    assert est.confidence == 0.5
    assert est.meta_context == "waking"
    assert est.source.endswith("v1_heuristic")
    assert est.fresh_for_seconds == vc.FRESH_SECONDS


def test_no_people_yields_alone_category():
    est = vc.fuse_from_feature(
        _feature(
            {"setting": "outdoor", "salient_objects": ["car"]},
            {"people_present": False, "crowd_size": "none"},
        ),
    )
    assert est.value["category"] == "alone"
    assert est.value["people_present"] is False
    assert est.value["setting"] == "outdoor"


def test_missing_setting_defaults_unknown():
    est = vc.fuse_from_feature(_feature({}, {"people_present": False}))
    assert est.value["setting"] == "unknown"
    assert est.value["salient_objects"] == []


def test_non_vision_kind_returns_none():
    assert vc.fuse_from_feature(
        _feature({"setting": "indoor"}, {"people_present": True}, kind="eeg_bandpower")
    ) is None


def test_non_packet_offline_returns_none():
    # A FeatureSnapshot whose kind is not visual_scene (e.g. an audio packet) -> None.
    assert vc.fuse_from_feature(
        _feature({"setting": "indoor"}, {"people_present": True}, kind="speech_final")
    ) is None
