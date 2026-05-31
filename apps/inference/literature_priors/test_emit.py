"""emit.record_weak_label — LabelRecord construction with an injected recorder. DB-free."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from literature_priors.emit import record_weak_label
from literature_priors.models import (
    Context,
    LiteraturePrior,
    PriorOrigin,
    PriorStatus,
    Rule,
    RuleClaim,
    Window,
)


def _prior() -> LiteraturePrior:
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
        origin=PriorOrigin.LLM_LITERATURE_BOOTSTRAP,
        status=PriorStatus.LIVE,
        citation="Author 2020",
    )


def _window() -> Window:
    start = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 30, 12, 1, tzinfo=timezone.utc)
    return Window(start=start, end=end)


def test_record_weak_label_builds_literature_prior_source() -> None:
    prior = _prior()
    user_id = uuid4()
    captured: list = []

    def recorder(record):
        captured.append(record)
        return "ledger-id"

    out = record_weak_label(
        prior.rule.claim,
        prior,
        user_id,
        _window(),
        Context(meta_context="waking"),
        recorder=recorder,
    )
    assert out == "ledger-id"
    assert len(captured) == 1
    rec = captured[0]
    from labels import LabelSource

    assert rec.source is LabelSource.LITERATURE_PRIOR
    assert rec.user_id == str(user_id)
    assert rec.axis == "arousal_inferred"
    assert rec.confidence == 0.4
    assert rec.consent_scope == "literature_prior_v1"
    assert rec.meta_context == "waking"
    assert rec.observed_at == _window().end


def test_provenance_round_trips_full_payload() -> None:
    prior = _prior()
    captured: list = []
    record_weak_label(
        prior.rule.claim,
        prior,
        uuid4(),
        _window(),
        Context(meta_context="waking"),
        recorder=lambda r: captured.append(r) or "id",
    )
    prov = captured[0].provenance
    assert prov["literature_prior_id"] == str(prior.id)
    assert prov["citation"] == "Author 2020"
    assert prov["population"] == "healthy adults"
    assert prov["known_limitations"] == "motion confound"
    assert prov["proposed_source"] == "llm_literature_bootstrap"
    assert prov["idempotency_key"]


def test_idempotency_key_stable_for_same_window() -> None:
    prior = _prior()
    user_id = uuid4()
    window = _window()
    keys: list[str] = []
    for _ in range(2):
        captured: list = []
        record_weak_label(
            prior.rule.claim,
            prior,
            user_id,
            window,
            recorder=lambda r: captured.append(r) or "id",
        )
        keys.append(captured[0].provenance["idempotency_key"])
    assert keys[0] == keys[1]


def test_directional_value_encoded_when_no_absolute_value() -> None:
    prior = _prior()
    captured: list = []
    record_weak_label(
        prior.rule.claim,
        prior,
        uuid4(),
        _window(),
        recorder=lambda r: captured.append(r) or "id",
    )
    assert captured[0].value == {"direction": "increase", "magnitude": "weak"}
