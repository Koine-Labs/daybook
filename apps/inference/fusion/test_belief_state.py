"""Tests for BeliefState + freshness policy."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fusion.belief_state import AxisEstimate, BeliefState


def _ts(offset_s: int = 0) -> datetime:
    return datetime(2026, 5, 27, 15, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_s)


def test_axis_estimate_fresh_default():
    est = AxisEstimate(
        axis="meta_context",
        value={"category": "waking/focused"},
        timestamp=_ts(0),
        confidence=0.8,
        source="L3.fusion.meta_context",
    )
    # default freshness threshold is 120s → fresh at "now=0"
    assert est.is_fresh(now=_ts(0)) is True
    assert est.is_fresh(now=_ts(60)) is True
    assert est.is_fresh(now=_ts(125)) is False


def test_axis_estimate_custom_fresh_window():
    est = AxisEstimate(
        axis="sleep_stage",
        value={"label": "rem"},
        timestamp=_ts(0),
        confidence=0.9,
        source="apple_health_sleep_stage",
        fresh_for_seconds=600,  # 10min for sleep
    )
    assert est.is_fresh(now=_ts(300)) is True
    assert est.is_fresh(now=_ts(700)) is False


def test_belief_state_get_returns_fresh_only():
    bs = BeliefState(user_id="u1")
    bs.update(AxisEstimate(
        axis="meta_context",
        value={"category": "waking"},
        timestamp=_ts(0),
        confidence=0.7,
        source="L3.fusion.meta_context",
    ))
    # fresh
    assert bs.get("meta_context", now=_ts(60)).value["category"] == "waking"
    # stale
    assert bs.get("meta_context", now=_ts(200)) is None


def test_belief_state_replaces_axis():
    bs = BeliefState(user_id="u1")
    bs.update(AxisEstimate(
        axis="meta_context",
        value={"category": "waking"},
        timestamp=_ts(0),
        confidence=0.7,
        source="L3.fusion.meta_context",
    ))
    bs.update(AxisEstimate(
        axis="meta_context",
        value={"category": "waking/focused"},
        timestamp=_ts(30),
        confidence=0.85,
        source="L3.fusion.meta_context",
    ))
    assert bs.get("meta_context", now=_ts(40)).value["category"] == "waking/focused"
