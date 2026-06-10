"""Model invariant tests — #17 enforced at the type layer. Pure, DB-free, LLM-free."""
from __future__ import annotations

from uuid import uuid4

import pytest

from literature_priors.models import (
    LiteraturePrior,
    PriorOrigin,
    PriorStatus,
    Rule,
    RuleClaim,
)


def _claim(axis: str = "arousal_inferred", direction: str = "increase") -> RuleClaim:
    return RuleClaim(axis=axis, direction=direction)


def _rule(axis: str = "arousal_inferred") -> Rule:
    return Rule(feature="hrv_rmssd", operator="decrease", claim=_claim(axis=axis))


def _prior(**overrides) -> LiteraturePrior:
    base = dict(
        target_axis="arousal_inferred",
        rule=_rule(),
        claim_summary="RMSSD decrease -> arousal increase",
        population="healthy adults",
        confidence=0.4,
        known_limitations="confounded by motion/respiration",
        source_id=uuid4(),
        origin=PriorOrigin.SEED,
    )
    base.update(overrides)
    return LiteraturePrior(**base)


def test_valid_prior_constructs() -> None:
    p = _prior()
    assert p.status is PriorStatus.CANDIDATE
    assert p.target_axis == "arousal_inferred"


def test_claim_axis_must_equal_target_axis() -> None:
    with pytest.raises(ValueError, match="must equal target_axis"):
        _prior(rule=_rule(axis="cognitive_load"))


def test_confidence_below_zero_rejected() -> None:
    with pytest.raises(ValueError, match="confidence"):
        _prior(confidence=-0.01)


def test_confidence_above_one_rejected() -> None:
    with pytest.raises(ValueError, match="confidence"):
        _prior(confidence=1.01)


def test_confidence_bounds_inclusive() -> None:
    assert _prior(confidence=0.0).confidence == 0.0
    assert _prior(confidence=1.0).confidence == 1.0


def test_empty_known_limitations_rejected() -> None:
    with pytest.raises(ValueError, match="known_limitations"):
        _prior(known_limitations="")


def test_whitespace_known_limitations_rejected() -> None:
    with pytest.raises(ValueError, match="known_limitations"):
        _prior(known_limitations="   ")


def test_empty_population_rejected() -> None:
    with pytest.raises(ValueError, match="population"):
        _prior(population="")


def test_origin_coerced_from_str() -> None:
    p = _prior(origin="seed")
    assert p.origin is PriorOrigin.SEED


def test_rule_threshold_required_for_gt() -> None:
    with pytest.raises(ValueError, match="threshold"):
        Rule(feature="hr_bpm", operator="gt", claim=_claim(), threshold=None)


def test_rule_in_band_requires_pair() -> None:
    with pytest.raises(ValueError, match="in_band"):
        Rule(feature="hr_bpm", operator="in_band", claim=_claim(), threshold=5)


def test_rule_unknown_operator_rejected() -> None:
    with pytest.raises(ValueError, match="operator"):
        Rule(feature="hr_bpm", operator="wiggle", claim=_claim())


def test_claim_requires_direction_or_value() -> None:
    with pytest.raises(ValueError, match="direction or a value"):
        RuleClaim(axis="arousal_inferred")


def test_rule_round_trips_through_dict() -> None:
    r = Rule(
        feature="hr_bpm",
        operator="in_band",
        claim=_claim(),
        threshold=(60, 100),
        context_gate={"meta_context": "waking"},
    )
    r2 = Rule.from_dict(r.to_dict())
    assert r2.operator == "in_band"
    assert r2.threshold == (60, 100)
    assert r2.claim.axis == "arousal_inferred"
    assert r2.context_gate == {"meta_context": "waking"}
