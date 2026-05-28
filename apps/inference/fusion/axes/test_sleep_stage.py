"""Tests for sleep_stage axis fusion (pure-logic part)."""
from __future__ import annotations

from datetime import datetime, timezone

from fusion.axes.sleep_stage import classify_sleep_stage


def test_active_stage():
    out = classify_sleep_stage(stage="rem", duration_s=600, source="Apple Watch")
    assert out["label"] == "rem"
    assert out["active"] is True


def test_awake_in_bed_classified_as_offline():
    out = classify_sleep_stage(stage="in_bed", duration_s=120, source="Apple Watch")
    assert out["label"] == "in_bed"
    assert out["active"] is False  # not actually sleeping


def test_awake_offline():
    out = classify_sleep_stage(stage="awake", duration_s=300, source="Apple Watch")
    assert out["label"] == "awake"
    assert out["active"] is False
