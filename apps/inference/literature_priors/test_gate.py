"""Gate scoring + pass/fail via a dependency-injected fake ledger reader. DB-free."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest

from literature_priors.gate import (
    promote_prior,
    sign_agreement_rate,
    validate_against_ledger,
)
from literature_priors.models import (
    LiteraturePrior,
    PriorOrigin,
    PriorStatus,
    Rule,
    RuleClaim,
)

USER = uuid4()


@dataclass
class FakeLabel:
    value: Any
    provenance: dict = field(default_factory=dict)


def _prior(status: PriorStatus = PriorStatus.REVIEWED) -> LiteraturePrior:
    return LiteraturePrior(
        id=uuid4(),
        target_axis="arousal_inferred",
        rule=Rule(
            feature="hrv_rmssd",
            operator="decrease",
            claim=RuleClaim(axis="arousal_inferred", direction="increase"),
        ),
        claim_summary="RMSSD decrease -> arousal increase",
        population="healthy adults",
        confidence=0.4,
        known_limitations="motion confound",
        source_id=uuid4(),
        origin=PriorOrigin.SEED,
        status=status,
    )


def test_sign_agreement_perfect() -> None:
    rule = _prior().rule
    # RMSSD decreased -> rule predicts arousal increase; observed increase => match.
    evidence = [
        FakeLabel(value={"direction": "increase"}, provenance={"features": {"hrv_rmssd_delta": -2}})
        for _ in range(4)
    ]
    score, n = sign_agreement_rate(rule, evidence)
    assert score == 1.0 and n == 4


def test_sign_agreement_half() -> None:
    rule = _prior().rule
    good = FakeLabel(value={"direction": "increase"}, provenance={"features": {"hrv_rmssd_delta": -2}})
    bad = FakeLabel(value={"direction": "decrease"}, provenance={"features": {"hrv_rmssd_delta": -2}})
    score, n = sign_agreement_rate(rule, [good, bad])
    assert score == 0.5 and n == 2


def test_sign_agreement_skips_labels_without_features() -> None:
    rule = _prior().rule
    evidence = [FakeLabel(value={"direction": "increase"})]  # no provenance.features
    score, n = sign_agreement_rate(rule, evidence)
    assert score is None and n == 0


def test_sign_agreement_skips_when_rule_does_not_fire() -> None:
    rule = _prior().rule
    # positive delta -> 'decrease' rule does not fire -> not comparable
    evidence = [FakeLabel(value={"direction": "increase"}, provenance={"features": {"hrv_rmssd_delta": 3}})]
    score, n = sign_agreement_rate(rule, evidence)
    assert score is None and n == 0


def _reader_factory(labels: list[FakeLabel]):
    def reader(axis: str, user_id) -> list[FakeLabel]:
        return labels
    return reader


def test_validate_passes_when_above_threshold_and_enough_labels() -> None:
    labels = [
        FakeLabel(value={"direction": "increase"}, provenance={"features": {"hrv_rmssd_delta": -1}})
        for _ in range(25)
    ]
    promo = validate_against_ledger(
        _prior(), USER, min_labels=20, threshold=0.6, reader=_reader_factory(labels)
    )
    assert promo.passed is True
    assert promo.validation_score == 1.0
    assert promo.evidence_label_count == 25
    assert promo.to_status is PriorStatus.LIVE


def test_validate_fails_when_too_few_labels() -> None:
    labels = [
        FakeLabel(value={"direction": "increase"}, provenance={"features": {"hrv_rmssd_delta": -1}})
        for _ in range(5)
    ]
    promo = validate_against_ledger(
        _prior(), USER, min_labels=20, threshold=0.6, reader=_reader_factory(labels)
    )
    assert promo.passed is False
    assert promo.to_status is PriorStatus.REVIEWED


def test_validate_fails_when_below_threshold() -> None:
    good = [
        FakeLabel(value={"direction": "increase"}, provenance={"features": {"hrv_rmssd_delta": -1}})
        for _ in range(10)
    ]
    bad = [
        FakeLabel(value={"direction": "decrease"}, provenance={"features": {"hrv_rmssd_delta": -1}})
        for _ in range(15)
    ]
    promo = validate_against_ledger(
        _prior(), USER, min_labels=20, threshold=0.6, reader=_reader_factory(good + bad)
    )
    assert promo.validation_score == pytest.approx(0.4)
    assert promo.passed is False


def test_validate_unsupported_metric_raises() -> None:
    with pytest.raises(ValueError, match="metric"):
        validate_against_ledger(_prior(), USER, metric="cohen_kappa", reader=_reader_factory([]))


def test_promote_requires_reviewer() -> None:
    with pytest.raises(ValueError, match="reviewer"):
        promote_prior(uuid4(), reviewer="", evidence_user_id=USER)


def test_promote_flips_live_on_pass_and_writes_audit() -> None:
    prior = _prior()
    labels = [
        FakeLabel(value={"direction": "increase"}, provenance={"features": {"hrv_rmssd_delta": -1}})
        for _ in range(25)
    ]
    written: list = []
    flipped: list = []
    promo = promote_prior(
        prior.id,
        reviewer="aakash",
        evidence_user_id=USER,
        min_labels=20,
        threshold=0.6,
        reader=_reader_factory(labels),
        prior_loader=lambda pid: prior,
        promotion_writer=lambda p: written.append(p),
        status_setter=lambda pid, status: flipped.append((pid, status)),
    )
    assert promo.passed is True
    assert promo.decided_by == "aakash"
    assert promo.to_status is PriorStatus.LIVE
    assert len(written) == 1 and written[0].passed is True
    assert flipped == [(prior.id, PriorStatus.LIVE)]


def test_promote_writes_audit_but_no_flip_on_fail() -> None:
    prior = _prior()
    labels = [FakeLabel(value={"direction": "increase"}, provenance={"features": {"hrv_rmssd_delta": -1}})]
    written: list = []
    flipped: list = []
    promo = promote_prior(
        prior.id,
        reviewer="aakash",
        evidence_user_id=USER,
        min_labels=20,
        reader=_reader_factory(labels),
        prior_loader=lambda pid: prior,
        promotion_writer=lambda p: written.append(p),
        status_setter=lambda pid, status: flipped.append((pid, status)),
    )
    assert promo.passed is False
    assert len(written) == 1 and written[0].passed is False
    assert flipped == []


def test_promote_unknown_prior_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        promote_prior(
            uuid4(),
            reviewer="aakash",
            evidence_user_id=USER,
            prior_loader=lambda pid: None,
            reader=_reader_factory([]),
        )
