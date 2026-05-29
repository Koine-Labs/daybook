# apps/inference/decision/policies/default.py
"""Default waking policy: hold unless an interjection is clearly warranted.

Used for waking/unknown contexts where no specialized policy applies (Companion
posture, #5/#14). Like the sleep-cue policy it defaults to silence; an
interjection requires ALL gates to clear. Three named gates, evaluated with no
short-circuit so the gate_trace records every verdict (mirrors sleep_cue):

  meta-context        : only speak in WAKING (companion posture, #5/#14)
  salient-fresh-signal: only speak on a fresh, salient social-context TRANSITION
  rate-limit          : don't be chatty — one interjection per cooldown window

The warrant is DETERMINISTIC: identical inputs + identical prior state ⇒
identical decision. The policy holds the minimal mutable state it needs — the
last social category seen *while waking* per user (to detect a transition;
Predictions are snapshots, not deltas) and the last interjection instant per user
(the cooldown). The baseline is recorded ONLY when the meta-context gate passes,
so a social observation routed here under UNKNOWN/SLEEP can't leak a baseline that
fabricates a transition on the first true waking window.

The salient-fresh-signal gate's freshness sub-check guards the Prediction OBJECT
(L4 restamps made_at at prediction time, so it measures L4->L5 latency, not the
age of the underlying reading — upstream staleness is gated at L3). It is a cheap
defensive backstop, not the primary staleness defense.

Deterministic pre-bandit scaffold for commitment #13. The `cleared` warrant
boolean is the single seam a Thompson contextual bandit (`learned_decider.py`)
later replaces; every decision's `gate_trace` is the outcome-labelable context
(meta-context, category transition, cooldown state all appear in gate details),
so a nightly job can label outcomes without any change here. The bandit is NOT
built here.
"""
from __future__ import annotations

from datetime import datetime

from core.protocol.enums import MetaContext
from core.protocol.payloads import ActionDecision

from decision.policy import (DecisionContext, GateResult, gate_trace_dict)

# Cooldown: at most one interjection per this many seconds, per user. Matches the
# audio_social_context freshness horizon (FRESH_SECONDS) — conservative, tune later.
MIN_INTERVAL_SECONDS = 300

# Freshness ceiling for the inbound Prediction *object* (defensive). NOTE: in the
# live pipeline L4 restamps made_at = now() at prediction time, so this measures
# L4->L5 in-process latency, not the age of the underlying social reading —
# upstream staleness is gated at L3 (fresh_for_seconds). This stays as a cheap
# defensive backstop against a wedged/replayed Prediction. Incidentally equal to
# MIN_INTERVAL_SECONDS today; the coupling is not load-bearing (separate knobs).
FRESH_SECONDS = 300

# The only warrant-bearing axis in v1 (YAGNI): a social-context transition is the
# single salient signal that justifies waking speech. The gate is shaped so more
# fresh high-confidence axis changes can be added as further PASS branches later.
WARRANT_AXIS = "audio_social_context"

# Waking moment kind on interject — a COMPANION_KINDS value; matches the
# ComposerRenderer default moment_kind and the speak-arc fixture.
CONTENT_KIND = "conversation_tease"


class DefaultPolicy:
    """Hold-unless-warranted Companion-mode policy. Default action is 'hold'."""

    name = "default"

    def __init__(self) -> None:
        # Minimal deterministic state, keyed by user_id (single-user today, but
        # keep it keyed — cheap, correct). All datetimes tz-aware UTC. No DB.
        self._last_category: dict[str, str] = {}
        self._last_interjection_at: dict[str, datetime] = {}

    # --- gates (instance methods so they can read remembered state) ---------
    def _gate_meta_context(self, ctx: DecisionContext) -> GateResult:
        """Only speak when awake (companion posture, #5/#14); fail-safe otherwise."""
        passed = ctx.meta_context == MetaContext.WAKING
        detail = (
            "waking — companion posture"
            if passed
            else f"meta_context {ctx.meta_context.value} — not waking; holding (fail-safe)"
        )
        return GateResult("meta-context", passed=passed, detail=detail)

    def _gate_salient_fresh_signal(self, ctx: DecisionContext) -> GateResult:
        """PASS iff the inbound Prediction is a fresh, salient social TRANSITION."""
        pred = ctx.prediction
        if pred.axis != WARRANT_AXIS:
            return GateResult(
                "salient-fresh-signal", passed=False,
                detail=f"axis not warrant-bearing: {pred.axis}",
            )

        category = (pred.distribution.get("carried_value") or {}).get("category")
        if not category:
            return GateResult(
                "salient-fresh-signal", passed=False,
                detail="no social category in prediction",
            )

        # Defensive freshness check on the Prediction OBJECT (not the underlying
        # reading — L4 restamps made_at; see FRESH_SECONDS note). Backstop against a
        # wedged/replayed Prediction; a fresh axis Prediction passes trivially.
        age = (ctx.now - pred.made_at).total_seconds()
        if age > FRESH_SECONDS:
            return GateResult(
                "salient-fresh-signal", passed=False,
                detail=f"stale prediction object: {age:.0f}s > {FRESH_SECONDS}s",
            )

        prior = self._last_category.get(ctx.user_id)
        if prior is None:
            return GateResult(
                "salient-fresh-signal", passed=False,
                detail=f"first observation ({category}), no transition to remark on; "
                       "establishing baseline",
            )
        if category == prior:
            return GateResult(
                "salient-fresh-signal", passed=False,
                detail=f"no transition: still {category} (age {age:.0f}s)",
            )
        return GateResult(
            "salient-fresh-signal", passed=True,
            detail=f"transition {prior}→{category} (age {age:.0f}s)",
        )

    def _gate_rate_limit(self, ctx: DecisionContext) -> GateResult:
        """Don't be chatty: at most one interjection per MIN_INTERVAL_SECONDS."""
        last = self._last_interjection_at.get(ctx.user_id)
        if last is None:
            return GateResult("rate-limit", passed=True, detail="no prior interjection")
        elapsed = (ctx.now - last).total_seconds()
        if elapsed < MIN_INTERVAL_SECONDS:
            return GateResult(
                "rate-limit", passed=False,
                detail=f"cooldown active ({elapsed:.0f}s < {MIN_INTERVAL_SECONDS}s since last)",
            )
        return GateResult(
            "rate-limit", passed=True,
            detail=f"cooldown clear ({elapsed:.0f}s >= {MIN_INTERVAL_SECONDS}s since last)",
        )

    # --- decision -----------------------------------------------------------
    def decide(self, ctx: DecisionContext) -> ActionDecision:
        # Evaluate ALL gates (no short-circuit) so the trace records every verdict.
        meta_gate = self._gate_meta_context(ctx)
        results = [
            meta_gate,
            self._gate_salient_fresh_signal(ctx),
            self._gate_rate_limit(ctx),
        ]
        trace = gate_trace_dict(results, policy=self.name)

        # The single warrant boolean — the seam a learned_decider (#13) replaces.
        cleared = trace["all_passed"]

        # State update (deterministic ordering, §2.4):
        #  - _last_category: the waking baseline. Recorded ONLY when the meta-context
        #    gate passes (the policy is the active WAKING authority). A social
        #    observation seen under UNKNOWN/SLEEP routes here too (intent_dispatch),
        #    but it must NOT establish/overwrite the waking baseline — otherwise a
        #    leaked cross-context category would fabricate a "transition" on the
        #    first true waking window. So "transition" means "differs from the
        #    previous social observation *seen while waking*". Computed AFTER the
        #    gate verdict (which compares against the prior).
        #  - _last_interjection_at: armed ONLY when the decision interjects.
        observed_category = self._observed_category(ctx)
        if meta_gate.passed and observed_category is not None:
            self._last_category[ctx.user_id] = observed_category
        if cleared:
            self._last_interjection_at[ctx.user_id] = ctx.now

        return ActionDecision(
            user_id=ctx.user_id,
            decided_at=ctx.now,
            action="interject" if cleared else "hold",
            rationale=self._rationale(cleared, results),
            mode="companion",
            content_kind=CONTENT_KIND if cleared else None,
            gate_trace=trace,
            i_model_id=ctx.i_model_id,
        )

    # --- helpers ------------------------------------------------------------
    def _observed_category(self, ctx: DecisionContext) -> str | None:
        """The social category carried by this Prediction, if it's a readable
        social observation; else None (non-social axes never touch state)."""
        pred = ctx.prediction
        if pred.axis != WARRANT_AXIS:
            return None
        category = (pred.distribution.get("carried_value") or {}).get("category")
        return category or None

    def _rationale(self, cleared: bool, results: list[GateResult]) -> str:
        """Explain WHY: the transition on interject, the first failing gate on hold."""
        if cleared:
            salient = next(r for r in results if r.name == "salient-fresh-signal")
            return (
                f"{salient.detail}; waking + cooldown clear — remarking (companion)"
            )
        first_fail = next((r for r in results if not r.passed), None)
        reason = first_fail.detail if first_fail else "no warrant"
        return f"holding: {reason}"
