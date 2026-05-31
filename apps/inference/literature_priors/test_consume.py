"""Consumer API tests — applies_to_user + injected listers/emitters. DB-free."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from literature_priors.consume import (
    applies_to_user,
    materialize_prior,
    priors_for,
    weak_supervision_for,
)
from literature_priors.models import (
    Context,
    LiteraturePrior,
    PriorOrigin,
    PriorStatus,
    Rule,
    RuleClaim,
    SubjectProfile,
    Window,
)


def _prior(applicability=None, status=PriorStatus.LIVE, threshold=None, operator="decrease") -> LiteraturePrior:
    return LiteraturePrior(
        id=uuid4(),
        target_axis="arousal_inferred",
        rule=Rule(
            feature="hrv_rmssd",
            operator=operator,
            claim=RuleClaim(axis="arousal_inferred", direction="increase"),
            threshold=threshold,
            context_gate={"meta_context": "waking"},
        ),
        claim_summary="RMSSD decrease -> arousal increase",
        population="healthy adults",
        confidence=0.4,
        known_limitations="motion confound",
        source_id=uuid4(),
        origin=PriorOrigin.SEED,
        applicability=applicability or {},
        status=status,
        citation="Author 2020",
    )


# --- applies_to_user (pure) --------------------------------------------------


def test_no_gate_applies_to_unknown_subject() -> None:
    assert applies_to_user(_prior(), None) is True


def test_hard_gate_excludes_unknown_subject() -> None:
    assert applies_to_user(_prior(applicability={"age_min": 18}), None) is False


def test_age_in_range_applies() -> None:
    p = _prior(applicability={"age_min": 18, "age_max": 65})
    assert applies_to_user(p, SubjectProfile(age=30)) is True


def test_age_below_min_excluded() -> None:
    p = _prior(applicability={"age_min": 18})
    assert applies_to_user(p, SubjectProfile(age=12)) is False


def test_age_above_max_excluded() -> None:
    p = _prior(applicability={"age_max": 65})
    assert applies_to_user(p, SubjectProfile(age=80)) is False


def test_age_gate_with_missing_age_excluded() -> None:
    p = _prior(applicability={"age_min": 18})
    assert applies_to_user(p, SubjectProfile(age=None)) is False


def test_medication_exclusion() -> None:
    p = _prior(applicability={"excludes": ["beta_blockers"]})
    assert applies_to_user(p, SubjectProfile(medications=("Beta_Blockers",))) is False
    assert applies_to_user(p, SubjectProfile(medications=("aspirin",))) is True


def test_meta_context_gate() -> None:
    p = _prior(applicability={"meta_context": "waking"})
    assert applies_to_user(p, SubjectProfile(meta_context="waking")) is True
    assert applies_to_user(p, SubjectProfile(meta_context="sleep")) is False


# --- priors_for / weak_supervision_for (injected lister) ---------------------


def test_priors_for_filters_by_population() -> None:
    in_pop = _prior(applicability={"age_min": 18, "age_max": 65})
    out_pop = _prior(applicability={"age_max": 10})

    def lister(axis, status):
        return [in_pop, out_pop]

    got = priors_for("arousal_inferred", subject=SubjectProfile(age=30), lister=lister)
    assert got == [in_pop]


def test_weak_supervision_emits_for_satisfied_priors() -> None:
    prior = _prior()

    def lister(axis, status):
        return [prior]

    labels = weak_supervision_for(
        "arousal_inferred",
        {"hrv_rmssd_delta": -3.0},
        Context(meta_context="waking"),
        SubjectProfile(age=30),
        lister=lister,
    )
    assert len(labels) == 1
    wl = labels[0]
    assert wl.source == "literature_prior"
    assert wl.population == "healthy adults"
    assert wl.citation == "Author 2020"
    assert wl.known_limitations == "motion confound"
    assert wl.literature_prior_id == prior.id


def test_weak_supervision_silent_when_context_gate_unmet() -> None:
    prior = _prior()

    def lister(axis, status):
        return [prior]

    labels = weak_supervision_for(
        "arousal_inferred",
        {"hrv_rmssd_delta": -3.0},
        Context(meta_context="sleep"),
        SubjectProfile(age=30),
        lister=lister,
    )
    assert labels == []


# --- materialize_prior (injected loader + emitter) ---------------------------


def _window() -> Window:
    now = datetime.now(timezone.utc)
    return Window(start=now, end=now)


def test_materialize_fires_and_emits_one_label() -> None:
    prior = _prior()
    captured: list = []

    def emitter(claim, p, user_id, window, context):
        captured.append((claim, p, user_id))
        return "ledger-id-123"

    out = materialize_prior(
        prior.id,
        uuid4(),
        _window(),
        {"hrv_rmssd_delta": -2.0},
        Context(meta_context="waking"),
        loader=lambda pid: prior,
        emitter=emitter,
    )
    assert out == "ledger-id-123"
    assert len(captured) == 1


def test_materialize_returns_none_when_rule_does_not_fire() -> None:
    prior = _prior()
    out = materialize_prior(
        prior.id,
        uuid4(),
        _window(),
        {"hrv_rmssd_delta": 5.0},  # positive -> decrease rule no fire
        Context(meta_context="waking"),
        loader=lambda pid: prior,
        emitter=lambda *a, **k: "should-not-happen",
    )
    assert out is None


def test_materialize_refuses_non_live_prior() -> None:
    prior = _prior(status=PriorStatus.REVIEWED)
    out = materialize_prior(
        prior.id,
        uuid4(),
        _window(),
        {"hrv_rmssd_delta": -2.0},
        Context(meta_context="waking"),
        loader=lambda pid: prior,
        emitter=lambda *a, **k: "should-not-happen",
    )
    assert out is None


def test_materialize_returns_none_when_prior_absent() -> None:
    out = materialize_prior(
        uuid4(),
        uuid4(),
        _window(),
        {"hrv_rmssd_delta": -2.0},
        Context(meta_context="waking"),
        loader=lambda pid: None,
        emitter=lambda *a, **k: "x",
    )
    assert out is None
