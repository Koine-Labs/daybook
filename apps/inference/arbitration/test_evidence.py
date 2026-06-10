"""DB-free + LLM-free tests for evidence.summarize() — decay, anti-swamp, tier grouping."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelRecord, LabelSource

from arbitration import blend
from arbitration.constants import default_profile
from arbitration.evidence import summarize

NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)


def _rec(source: LabelSource, *, age_s: float = 0.0, confidence: float = 1.0):
    return LabelRecord(
        user_id="u",
        axis="arousal",
        value=0.5,
        source=source,
        observed_at=NOW - timedelta(seconds=age_s),
        confidence=confidence,
    )


def test_population_pole_rows_excluded_from_evidence():
    rows = [
        _rec(LabelSource.LITERATURE_PRIOR),
        _rec(LabelSource.DEMOGRAPHIC_PRIOR),
        _rec(LabelSource.LLM_LITERATURE_BOOTSTRAP),
        _rec(LabelSource.SELF_REPORT),
    ]
    ev = summarize(rows, default_profile("arousal"), now=NOW)
    assert set(ev.keys()) == {LabelSource.SELF_REPORT.value}


def test_empty_rows_give_empty_evidence():
    assert summarize([], default_profile("arousal"), now=NOW) == {}


def test_tier_trust_orders_masses_for_equal_volume_and_recency():
    p = default_profile("arousal")
    sr = summarize([_rec(LabelSource.SELF_REPORT)], p, now=NOW)[LabelSource.SELF_REPORT.value]
    oo = summarize([_rec(LabelSource.OBSERVED_OUTCOME)], p, now=NOW)[LabelSource.OBSERVED_OUTCOME.value]
    he = summarize([_rec(LabelSource.HEURISTIC)], p, now=NOW)[LabelSource.HEURISTIC.value]
    assert sr.effective_mass > oo.effective_mass > he.effective_mass


def test_recency_decay_old_label_contributes_less():
    p = default_profile("arousal")
    fresh = summarize([_rec(LabelSource.SELF_REPORT, age_s=0)], p, now=NOW)[LabelSource.SELF_REPORT.value]
    halflife = p.halflife_for(LabelSource.SELF_REPORT.value)
    one_hl = summarize([_rec(LabelSource.SELF_REPORT, age_s=halflife)], p, now=NOW)[LabelSource.SELF_REPORT.value]
    assert one_hl.effective_mass == pytest.approx(fresh.effective_mass * 0.5, rel=1e-6)


def test_confidence_scales_mass():
    p = default_profile("arousal")
    full = summarize([_rec(LabelSource.SELF_REPORT, confidence=1.0)], p, now=NOW)[LabelSource.SELF_REPORT.value]
    half = summarize([_rec(LabelSource.SELF_REPORT, confidence=0.5)], p, now=NOW)[LabelSource.SELF_REPORT.value]
    assert half.effective_mass == pytest.approx(full.effective_mass * 0.5)


def test_count_reflects_raw_label_count():
    p = default_profile("arousal")
    ev = summarize([_rec(LabelSource.HEURISTIC) for _ in range(5)], p, now=NOW)
    assert ev[LabelSource.HEURISTIC.value].count == 5


def test_last_observed_at_is_newest():
    p = default_profile("arousal")
    rows = [_rec(LabelSource.SELF_REPORT, age_s=1000), _rec(LabelSource.SELF_REPORT, age_s=10)]
    ev = summarize(rows, p, now=NOW)[LabelSource.SELF_REPORT.value]
    assert ev.last_observed_at == NOW - timedelta(seconds=10)


def test_anti_swamp_volume_of_sensor_cannot_beat_one_self_report():
    """1000 HEURISTIC (sensor) labels must NOT yield more w_personal than ONE
    high-confidence SELF_REPORT — proves Apple-Health volume can't beat self-report."""
    p = default_profile("arousal")
    sensor_rows = [_rec(LabelSource.HEURISTIC, confidence=1.0) for _ in range(1000)]
    self_rows = [_rec(LabelSource.SELF_REPORT, confidence=1.0)]

    sensor_ev = summarize(sensor_rows, p, now=NOW)
    self_ev = summarize(self_rows, p, now=NOW)

    sensor_w = blend("arousal", sensor_ev, p, 0.0, 1.0, now=NOW).w_personal
    self_w = blend("arousal", self_ev, p, 0.0, 1.0, now=NOW).w_personal
    assert sensor_w < self_w


def test_heuristic_tier_saturates_with_volume():
    p = default_profile("arousal")
    cap = p.saturation_for(LabelSource.HEURISTIC.value)
    trust = p.trust_for(LabelSource.HEURISTIC.value)
    huge = summarize([_rec(LabelSource.HEURISTIC) for _ in range(10_000)], p, now=NOW)
    mass = huge[LabelSource.HEURISTIC.value].effective_mass
    assert mass == pytest.approx(trust * cap)


def test_future_timestamp_treated_as_no_decay():
    p = default_profile("arousal")
    ev = summarize([_rec(LabelSource.SELF_REPORT, age_s=-500)], p, now=NOW)
    assert ev[LabelSource.SELF_REPORT.value].effective_mass == pytest.approx(
        p.trust_for(LabelSource.SELF_REPORT.value)
    )
