"""Tests for FusionParticipant calibration wiring (#4 -> L3 hot path)."""
from __future__ import annotations

from datetime import datetime, timezone

from arbitration.blend import BlendResult, CalibrationState
from core.protocol.enums import Modality
from core.protocol.payloads import FeatureSnapshot
from fusion.belief_state import AxisEstimate
from fusion.participant import FusionParticipant


def _packet(user="u1"):
    return FeatureSnapshot(
        user_id=user,
        timestamp=datetime(2026, 5, 31, tzinfo=timezone.utc),
        modality=Modality.TEXT,
        source="L2.test",
        payload={"kind": "state_declaration", "features": {}},
    )


def _live_est(packet, now):
    return AxisEstimate(
        axis="x",
        value={"arousal": 0.7},
        timestamp=now,
        confidence=0.4,
        source="L3.test.x",
    )


def _calib(axis):
    return BlendResult(
        axis=axis, w_personal=0.0, w_population=1.0,
        calibration_state=CalibrationState.CALIBRATING, e_personal=0.0,
        evidence_by_tier={}, population_value=0.0, population_variance=1.0,
        demographics_applied=False, population_seeded=False,
    )


def test_no_reader_leaves_estimates_unenriched() -> None:
    part = FusionParticipant(registry={"x": _live_est})
    belief = part.fuse(_packet())
    assert "calibration_state" not in belief.estimates["x"].value


def test_reader_enriches_live_estimates() -> None:
    calls = []
    def reader(user_id, axis):
        calls.append((user_id, axis))
        return _calib(axis)
    part = FusionParticipant(registry={"x": _live_est}, calibration_reader=reader)
    belief = part.fuse(_packet())
    assert belief.estimates["x"].value["calibration_state"] == "calibrating"
    assert ("u1", "x") in calls


def test_reader_failure_never_crashes_fuse() -> None:
    def boom(user_id, axis):
        raise RuntimeError("db down")
    part = FusionParticipant(registry={"x": _live_est}, calibration_reader=boom)
    belief = part.fuse(_packet())  # must not raise
    assert belief.estimates["x"].value["arousal"] == 0.7  # original estimate preserved


def test_offline_axis_not_passed_to_reader() -> None:
    calls = []
    def reader(user_id, axis):
        calls.append(axis)
        return _calib(axis)
    part = FusionParticipant(registry={"x": lambda p, n: None}, calibration_reader=reader)
    belief = part.fuse(_packet())
    assert belief.estimates["x"].value["category"] == "offline"
    assert calls == []  # never enrich an OFFLINE sentinel
