"""Exhaustive evaluate_rule table tests. Pure, DB-free, LLM-free."""
from __future__ import annotations

import pytest

from literature_priors.models import Context, Rule, RuleClaim
from literature_priors.rules import evaluate_rule


def _claim() -> RuleClaim:
    return RuleClaim(axis="arousal_inferred", direction="increase")


# --- directional operators ---------------------------------------------------


def test_decrease_fires_on_negative_delta() -> None:
    rule = Rule(feature="hrv_rmssd", operator="decrease", claim=_claim())
    out = evaluate_rule(rule, {"hrv_rmssd_delta": -3.0})
    assert out is not None and out.axis == "arousal_inferred"


def test_decrease_does_not_fire_on_positive_delta() -> None:
    rule = Rule(feature="hrv_rmssd", operator="decrease", claim=_claim())
    assert evaluate_rule(rule, {"hrv_rmssd_delta": 2.0}) is None


def test_decrease_zero_delta_does_not_fire() -> None:
    rule = Rule(feature="hrv_rmssd", operator="decrease", claim=_claim())
    assert evaluate_rule(rule, {"hrv_rmssd_delta": 0.0}) is None


def test_increase_fires_on_positive_delta() -> None:
    rule = Rule(feature="hr_bpm", operator="increase", claim=_claim())
    assert evaluate_rule(rule, {"hr_bpm_delta": 5.0}) is not None


def test_increase_does_not_fire_on_negative_delta() -> None:
    rule = Rule(feature="hr_bpm", operator="increase", claim=_claim())
    assert evaluate_rule(rule, {"hr_bpm_delta": -5.0}) is None


def test_directional_missing_delta_feature_does_not_fire() -> None:
    rule = Rule(feature="hrv_rmssd", operator="decrease", claim=_claim())
    assert evaluate_rule(rule, {"hrv_rmssd": 40.0}) is None


# --- threshold operators -----------------------------------------------------


def test_gt_fires_above_threshold() -> None:
    rule = Rule(feature="hr_bpm", operator="gt", claim=_claim(), threshold=100.0)
    assert evaluate_rule(rule, {"hr_bpm": 110.0}) is not None


def test_gt_boundary_does_not_fire() -> None:
    rule = Rule(feature="hr_bpm", operator="gt", claim=_claim(), threshold=100.0)
    assert evaluate_rule(rule, {"hr_bpm": 100.0}) is None


def test_lt_fires_below_threshold() -> None:
    rule = Rule(feature="hf_hrv", operator="lt", claim=_claim(), threshold=50.0)
    assert evaluate_rule(rule, {"hf_hrv": 30.0}) is not None


def test_lt_boundary_does_not_fire() -> None:
    rule = Rule(feature="hf_hrv", operator="lt", claim=_claim(), threshold=50.0)
    assert evaluate_rule(rule, {"hf_hrv": 50.0}) is None


def test_ratio_gt_fires_above_threshold() -> None:
    rule = Rule(feature="theta_beta_ratio", operator="ratio_gt", claim=_claim(), threshold=1.5)
    assert evaluate_rule(rule, {"theta_beta_ratio": 2.0}) is not None


def test_ratio_gt_boundary_does_not_fire() -> None:
    rule = Rule(feature="theta_beta_ratio", operator="ratio_gt", claim=_claim(), threshold=1.5)
    assert evaluate_rule(rule, {"theta_beta_ratio": 1.5}) is None


def test_in_band_fires_inside() -> None:
    rule = Rule(feature="hr_bpm", operator="in_band", claim=_claim(), threshold=(60, 100))
    assert evaluate_rule(rule, {"hr_bpm": 80.0}) is not None


def test_in_band_boundaries_inclusive() -> None:
    rule = Rule(feature="hr_bpm", operator="in_band", claim=_claim(), threshold=(60, 100))
    assert evaluate_rule(rule, {"hr_bpm": 60.0}) is not None
    assert evaluate_rule(rule, {"hr_bpm": 100.0}) is not None


def test_in_band_outside_does_not_fire() -> None:
    rule = Rule(feature="hr_bpm", operator="in_band", claim=_claim(), threshold=(60, 100))
    assert evaluate_rule(rule, {"hr_bpm": 120.0}) is None


def test_threshold_missing_feature_does_not_fire() -> None:
    rule = Rule(feature="hr_bpm", operator="gt", claim=_claim(), threshold=100.0)
    assert evaluate_rule(rule, {"other": 110.0}) is None


# --- context gate (commitment #14) ------------------------------------------


def test_context_gate_satisfied_allows_fire() -> None:
    rule = Rule(
        feature="hr_bpm",
        operator="gt",
        claim=_claim(),
        threshold=100.0,
        context_gate={"meta_context": "waking"},
    )
    out = evaluate_rule(rule, {"hr_bpm": 110.0}, Context(meta_context="waking"))
    assert out is not None


def test_context_gate_mismatch_blocks_fire() -> None:
    rule = Rule(
        feature="hr_bpm",
        operator="gt",
        claim=_claim(),
        threshold=100.0,
        context_gate={"meta_context": "waking"},
    )
    assert evaluate_rule(rule, {"hr_bpm": 110.0}, Context(meta_context="sleep")) is None


def test_context_gate_requires_context_when_gated() -> None:
    rule = Rule(
        feature="hr_bpm",
        operator="gt",
        claim=_claim(),
        threshold=100.0,
        context_gate={"meta_context": "waking"},
    )
    assert evaluate_rule(rule, {"hr_bpm": 110.0}, None) is None


def test_no_context_gate_fires_without_context() -> None:
    rule = Rule(feature="hr_bpm", operator="gt", claim=_claim(), threshold=100.0)
    assert evaluate_rule(rule, {"hr_bpm": 110.0}, None) is not None


def test_sub_context_gate_enforced() -> None:
    rule = Rule(
        feature="hr_bpm",
        operator="gt",
        claim=_claim(),
        threshold=100.0,
        context_gate={"sub_context": "non_exercise"},
    )
    assert evaluate_rule(rule, {"hr_bpm": 110.0}, Context(sub_context="exercise")) is None
    assert (
        evaluate_rule(rule, {"hr_bpm": 110.0}, Context(sub_context="non_exercise"))
        is not None
    )
