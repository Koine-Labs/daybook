"""L3 arousal_inferred axis unit tests — pure, DB-free.

Mirrors test_cognitive_load.py's fuse_from_feature block. Asserts the heuristic
responds to HR/HRV, carries honest scaffold provenance, tags meta_context=None
(it genuinely cannot tell SLEEP from WAKING), and never weights the near-constant
hr_pct_above_baseline into the scalar (BLOCKING FIX #1).
"""
from __future__ import annotations

from datetime import datetime, timezone

from features.snapshot import FeatureSnapshot
from fusion.axes import arousal_inferred as ai
from fusion.belief_state import AxisEstimate


def _feature(features: dict, *, kind: str = "biometric_window") -> FeatureSnapshot:
    return FeatureSnapshot(
        user_id="u1",
        timestamp=datetime.now(timezone.utc),
        modality="biometric",
        source="watch.hr_30s",
        payload={"kind": kind, "features": features},
    )


def test_high_hr_low_hrv_yields_medium_or_high_arousal():
    now = datetime.now(timezone.utc)
    est = ai.fuse_from_feature(
        _feature({"hr_mean": 100.0, "hrv_mean": 25.0, "hr_slope": 0.5}),
        now=now,
    )
    assert isinstance(est, AxisEstimate)
    assert est.axis == "arousal_inferred"
    assert 0.0 <= est.value["arousal"] <= 1.0
    assert est.value["band"] in {"medium", "high"}
    assert est.value["scaffold"] is True
    assert est.value["method"] == "biometric_arousal_linear_v1"
    assert est.confidence == 0.4


def test_low_hr_high_hrv_yields_low_band_and_lower_arousal():
    high = ai.fuse_from_feature(_feature({"hr_mean": 100.0, "hrv_mean": 25.0}))
    low = ai.fuse_from_feature(_feature({"hr_mean": 58.0, "hrv_mean": 65.0}))
    assert low.value["band"] == "low"
    assert low.value["arousal"] < high.value["arousal"]


def test_arousal_clamped_to_unit_interval():
    huge = ai.fuse_from_feature(_feature({"hr_mean": 200.0, "hrv_mean": 10.0}))
    tiny = ai.fuse_from_feature(_feature({"hr_mean": 30.0, "hrv_mean": 80.0}))
    assert huge.value["arousal"] == 1.0
    assert tiny.value["arousal"] == 0.0


def test_non_biometric_kind_returns_none():
    assert ai.fuse_from_feature(_feature({"hr_mean": 100.0}, kind="mac_activity")) is None


def test_both_hr_and_hrv_missing_returns_none():
    assert ai.fuse_from_feature(_feature({"hr_slope": 0.5})) is None


def test_honest_no_frame_tag_and_exposed_components():
    est = ai.fuse_from_feature(_feature({"hr_mean": 90.0, "hrv_mean": 30.0}))
    assert est.meta_context is None
    assert est.value["hr_mean"] == 90.0
    assert est.value["hrv_mean"] == 30.0
    assert est.value["baseline"] == "in_window_only"
    assert est.value["meta_context_aware"] is False


def test_hr_pct_above_baseline_does_not_move_scalar():
    low_pct = ai.fuse_from_feature(
        _feature({"hr_mean": 90.0, "hrv_mean": 30.0, "hr_pct_above_baseline": 0.1})
    )
    high_pct = ai.fuse_from_feature(
        _feature({"hr_mean": 90.0, "hrv_mean": 30.0, "hr_pct_above_baseline": 0.9})
    )
    assert low_pct.value["arousal"] == high_pct.value["arousal"]
    assert low_pct.value["hr_pct_above_baseline"] == 0.1
    assert high_pct.value["hr_pct_above_baseline"] == 0.9


def test_fresh_and_source_provenance():
    est = ai.fuse_from_feature(_feature({"hr_mean": 90.0, "hrv_mean": 30.0}))
    assert est.fresh_for_seconds == 120
    assert est.source.endswith("v1_heuristic")


def test_single_component_carries_full_weight():
    """A single present component renormalizes to full magnitude, not half.

    Kills the mutation that drops `/ weight` (arousal = contrib without renorm):
    an HRV-only window would silently collapse 0.9 -> 0.36, and an HR-only window
    0.818 -> 0.491, halving every single-sensor reading.
    """
    hrv_only = ai.fuse_from_feature(_feature({"hrv_mean": 25.0}))
    assert hrv_only.value["arousal"] == 0.9
    assert hrv_only.value["band"] == "high"

    hr_only = ai.fuse_from_feature(_feature({"hr_mean": 100.0}))
    assert hr_only.value["arousal"] == round((100.0 - 55.0) / (110.0 - 55.0), 3)
    assert hr_only.value["band"] == "high"


def test_band_boundary_low_medium_cut_at_034():
    """Pin the low/medium band cut at 0.34 (kills the 0.34 -> 0.5 mutation).

    hr_mean=77, hrv_mean=45 yields arousal 0.44 (just above the cut -> medium);
    an HR-only window at 0.30 sits just below -> low.
    """
    at_044 = ai.fuse_from_feature(_feature({"hr_mean": 77.0, "hrv_mean": 45.0}))
    assert at_044.value["arousal"] == 0.44
    assert at_044.value["band"] == "medium"

    at_030 = ai.fuse_from_feature(_feature({"hr_mean": 71.5}))
    assert at_030.value["arousal"] == 0.3
    assert at_030.value["band"] == "low"
