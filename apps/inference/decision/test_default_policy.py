# apps/inference/decision/test_default_policy.py
"""Unit tests for the deterministic waking warrant policy (DefaultPolicy).

Drive DefaultPolicy.decide directly with hand-built DecisionContexts — the
cheapest, most deterministic level. The three gates (meta-context, salient-fresh-
signal, rate-limit) are exercised individually and as sequences (a single
instance accumulates last-seen state across calls, mirroring the registry-held
singleton). No DB, no network, no LLM, no audio.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.protocol.enums import MetaContext
from core.protocol.payloads import ActionDecision, Prediction

from decision.policies.default import (DefaultPolicy, FRESH_SECONDS,
                                        MIN_INTERVAL_SECONDS, WARRANT_AXIS)
from decision.policy import DecisionContext

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
IMODEL = "im-default-001"


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _prediction(
    *,
    axis: str = WARRANT_AXIS,
    category: str | None = "alone",
    made_at: datetime | None = None,
) -> Prediction:
    """Stub-shaped Prediction: persistence carry-forward of a social category."""
    made_at = made_at or _utc()
    if category is None:
        distribution = {"kind": "persistence", "informative": False, "carried_value": {}}
    else:
        distribution = {
            "kind": "persistence",
            "informative": False,
            "carried_value": {"category": category},
            "note": "placeholder",
        }
    return Prediction(
        user_id=USER,
        axis=axis,
        made_at=made_at,
        horizon_seconds=300,
        distribution=distribution,
        model_id="prediction.stub.persistence.v0",
        confidence=None,
        provenance="placeholder",
        cold_start=True,
        i_model_id=IMODEL,
    )


def _ctx(
    *,
    axis: str = WARRANT_AXIS,
    category: str | None = "alone",
    meta: MetaContext = MetaContext.WAKING,
    now: datetime | None = None,
    made_at: datetime | None = None,
) -> DecisionContext:
    now = now or _utc()
    return DecisionContext(
        user_id=USER,
        prediction=_prediction(axis=axis, category=category, made_at=made_at or now),
        meta_context=meta,
        consent_scope="mic_continuous_v1",
        now=now,
        i_model_id=IMODEL,
    )


def _gate(decision: ActionDecision, name: str) -> dict:
    return next(g for g in decision.gate_trace["gates"] if g["name"] == name)


# 1. first social observation HOLDs (establishes baseline) -------------------
def test_first_social_observation_holds_and_records_baseline():
    policy = DefaultPolicy()
    decision = policy.decide(_ctx(category="with_other"))

    assert decision.action == "hold"
    assert decision.mode == "companion"
    assert decision.content_kind is None
    salient = _gate(decision, "salient-fresh-signal")
    assert salient["passed"] is False
    assert "first observation" in salient["detail"]
    # baseline recorded for next time
    assert policy._last_category[USER] == "with_other"
    # a held first observation must not arm the cooldown
    assert USER not in policy._last_interjection_at


# 2. no transition HOLDs ------------------------------------------------------
def test_no_transition_holds():
    policy = DefaultPolicy()
    policy.decide(_ctx(category="alone"))           # baseline
    decision = policy.decide(_ctx(category="alone"))  # same → no transition

    assert decision.action == "hold"
    salient = _gate(decision, "salient-fresh-signal")
    assert salient["passed"] is False
    assert "no transition" in salient["detail"]
    assert "alone" in salient["detail"]


# 3. transition INTERJECTS ----------------------------------------------------
def test_transition_interjects_with_companion_tease():
    policy = DefaultPolicy()
    policy.decide(_ctx(category="alone"))           # baseline
    decision = policy.decide(_ctx(category="with_other"))

    assert decision.action == "interject"
    assert decision.mode == "companion"
    assert decision.content_kind == "conversation_tease"
    assert decision.gate_trace["all_passed"] is True
    assert all(g["passed"] for g in decision.gate_trace["gates"])
    assert "alone" in decision.rationale and "with_other" in decision.rationale


# 4. wrong meta-context HOLDs -------------------------------------------------
def test_unknown_meta_context_holds():
    policy = DefaultPolicy()
    policy.decide(_ctx(category="alone", meta=MetaContext.UNKNOWN))
    decision = policy.decide(_ctx(category="with_other", meta=MetaContext.UNKNOWN))

    assert decision.action == "hold"
    meta_gate = _gate(decision, "meta-context")
    assert meta_gate["passed"] is False


def test_sleep_meta_context_holds_fail_safe():
    policy = DefaultPolicy()
    # Even a clean transition must fail-safe if asked under SLEEP (sleep_cue owns it).
    policy.decide(_ctx(category="alone", meta=MetaContext.SLEEP))
    decision = policy.decide(_ctx(category="with_other", meta=MetaContext.SLEEP))

    assert decision.action == "hold"
    assert _gate(decision, "meta-context")["passed"] is False


# 4b. a non-WAKING observation must NOT leak a baseline into waking ----------
def test_non_waking_observation_does_not_leak_baseline_into_waking():
    """UNKNOWN routes here too (intent_dispatch); a social observation seen under
    UNKNOWN must not establish the waking baseline. The FIRST true waking window
    must therefore HOLD (no fabricated transition), even if its category differs
    from the leaked non-waking one."""
    policy = DefaultPolicy()
    # Observed 'alone' under UNKNOWN — action held by the meta-context gate, AND the
    # baseline must NOT be written (it would belong to the wrong context).
    held = policy.decide(_ctx(category="alone", meta=MetaContext.UNKNOWN))
    assert held.action == "hold"
    assert USER not in policy._last_category, "non-waking obs must not record a baseline"

    # First WAKING observation of a DIFFERENT category: with the leak fixed there is
    # no prior waking baseline, so this is a first observation → HOLD, not interject.
    first_waking = policy.decide(_ctx(category="with_other", meta=MetaContext.WAKING))
    assert first_waking.action == "hold", "first waking window must not interject on a leaked baseline"
    salient = _gate(first_waking, "salient-fresh-signal")
    assert salient["passed"] is False
    assert "first observation" in salient["detail"]
    # NOW the waking baseline is recorded.
    assert policy._last_category[USER] == "with_other"


def test_sleep_observation_does_not_corrupt_waking_baseline():
    """A SLEEP-context room-conversation flip must not rewrite the waking baseline.
    After a waking baseline is set, SLEEP observations leave it untouched, so the
    next genuine waking transition is detected against the real waking prior."""
    policy = DefaultPolicy()
    # Establish a genuine waking baseline.
    policy.decide(_ctx(category="alone", meta=MetaContext.WAKING))
    assert policy._last_category[USER] == "alone"

    # SLEEP flips (sleep_cue normally owns SLEEP; this is the fail-safe path) must
    # NOT overwrite the waking baseline.
    policy.decide(_ctx(category="with_other", meta=MetaContext.SLEEP))
    policy.decide(_ctx(category="alone", meta=MetaContext.SLEEP))
    assert policy._last_category[USER] == "alone", "SLEEP obs must not rewrite the waking baseline"

    # A real waking transition is now detected against the preserved 'alone' prior.
    decision = policy.decide(_ctx(category="with_other", meta=MetaContext.WAKING))
    assert decision.action == "interject"
    assert "alone" in decision.rationale and "with_other" in decision.rationale


# 5. rate-limit HOLDs then clears after cooldown ------------------------------
def test_rate_limit_holds_within_cooldown_then_clears():
    policy = DefaultPolicy()
    t0 = _utc()
    # baseline + first interject
    policy.decide(_ctx(category="alone", now=t0))
    first = policy.decide(_ctx(category="with_other", now=t0 + timedelta(seconds=1)))
    assert first.action == "interject"

    # a fresh transition within the cooldown window → rate-limit gate blocks
    within = policy.decide(
        _ctx(category="alone", now=t0 + timedelta(seconds=1 + 60))
    )
    assert within.action == "hold"
    rl = _gate(within, "rate-limit")
    assert rl["passed"] is False
    assert "cooldown" in rl["detail"].lower()

    # advance past the cooldown, feed another transition → interjects again
    after = policy.decide(
        _ctx(category="with_other", now=t0 + timedelta(seconds=1 + MIN_INTERVAL_SECONDS + 5))
    )
    assert after.action == "interject"
    assert _gate(after, "rate-limit")["passed"] is True


# 6. non-social axis HOLDs and does NOT mutate _last_category -----------------
def test_non_social_axis_holds_and_does_not_touch_state():
    policy = DefaultPolicy()
    decision = policy.decide(_ctx(axis="meta_context", category="waking/focused"))

    assert decision.action == "hold"
    salient = _gate(decision, "salient-fresh-signal")
    assert salient["passed"] is False
    assert "axis not warrant-bearing" in salient["detail"]
    assert USER not in policy._last_category  # non-social axis never records baseline


def test_missing_category_holds():
    policy = DefaultPolicy()
    decision = policy.decide(_ctx(category=None))
    assert decision.action == "hold"
    salient = _gate(decision, "salient-fresh-signal")
    assert salient["passed"] is False
    assert "no social category" in salient["detail"]


# 7. cooldown armed only on interject ----------------------------------------
def test_cooldown_armed_only_on_interject():
    policy = DefaultPolicy()
    # a held decision must not arm the cooldown
    policy.decide(_ctx(category="alone"))            # baseline (hold)
    assert USER not in policy._last_interjection_at
    policy.decide(_ctx(category="alone"))            # no transition (hold)
    assert USER not in policy._last_interjection_at
    # the interject arms it
    decision = policy.decide(_ctx(category="with_other"))
    assert decision.action == "interject"
    assert USER in policy._last_interjection_at


# 8. gate_trace is honest + JSON-serializable --------------------------------
def test_gate_trace_is_honest_and_json_serializable():
    import json

    policy = DefaultPolicy()
    policy.decide(_ctx(category="alone"))
    decision = policy.decide(_ctx(category="with_other"))

    trace = decision.gate_trace
    assert trace["policy"] == "default"
    names = {g["name"] for g in trace["gates"]}
    assert names == {"meta-context", "salient-fresh-signal", "rate-limit"}
    # all_passed consistent with action
    assert trace["all_passed"] is (decision.action == "interject")

    d = decision.to_dict()
    assert isinstance(d["decided_at"], str)  # isoformat round-trips
    json.dumps(d)  # must not raise


def test_hold_gate_trace_all_passed_false():
    policy = DefaultPolicy()
    decision = policy.decide(_ctx(category="alone"))  # first obs → hold
    assert decision.gate_trace["all_passed"] is False
    assert decision.action == "hold"


# 9. determinism --------------------------------------------------------------
def test_determinism_identical_inputs_and_state_give_identical_decision():
    def _run() -> dict:
        policy = DefaultPolicy()
        now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
        policy.decide(_ctx(category="alone", now=now))
        decision = policy.decide(
            _ctx(category="with_other", now=now + timedelta(seconds=2))
        )
        d = decision.to_dict()
        d.pop("decided_at")  # the only nondeterministic-by-clock field (we pinned now anyway)
        return d

    assert _run() == _run()


def test_stale_prediction_holds():
    """A Prediction object older than the freshness ceiling fails the salience gate.

    Constructed off FRESH_SECONDS (the ceiling this gate actually checks), not the
    incidentally-equal MIN_INTERVAL_SECONDS, so the intent survives a future tune
    that diverges the two knobs."""
    policy = DefaultPolicy()
    now = _utc()
    policy.decide(_ctx(category="alone", now=now))
    # transition, but the prediction object was made well beyond the freshness ceiling
    decision = policy.decide(
        _ctx(
            category="with_other",
            now=now,
            made_at=now - timedelta(seconds=FRESH_SECONDS + 600),
        )
    )
    assert decision.action == "hold"
    assert _gate(decision, "salient-fresh-signal")["passed"] is False
