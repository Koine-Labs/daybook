# apps/inference/decision/policies/sleep_cue.py
"""Sleep-cue policy (Witness mode): the most trust-critical decision Regis makes.

This is the skeleton of the v0 `cue_decision.py` gates (recovered from tag
v0-pre-rebuild), reshaped as pure predicates over a DecisionContext. Each gate
is a PLACEHOLDER that currently defaults to HOLD (safe) — none of the live
session state (elapsed time, cooldown, speaker identity, axis freshness) is
wired yet, so every gate blocks until its fill spec lands. The whole pipeline
must never speak during sleep on stub state alone.

Gates (mirror the five v0 safety gates):
  deep-sleep-suppression : never speak during deep/core sleep
  min-interval           : enforce cooldown since the last cue
  max-per-night          : cap cues per session
  stale-axis             : refuse to act on stale state
  unknown-speaker        : refuse if the speaker isn't confirmed to be the user
"""
from __future__ import annotations

from core.protocol.payloads import ActionDecision

from decision.policy import (DecisionContext, Gate, GateResult, gate_trace_dict,
                             run_gates)

# Sentinel reason for the placeholder phase: gate cannot yet be evaluated, so HOLD.
_PLACEHOLDER = "placeholder: gate not yet wired — default HOLD (safe)"


def gate_deep_sleep_suppression(ctx: DecisionContext) -> GateResult:
    """Never speak during deep/core sleep. Placeholder: HOLD."""
    return GateResult("deep-sleep-suppression", passed=False, detail=_PLACEHOLDER)


def gate_min_interval(ctx: DecisionContext) -> GateResult:
    """Enforce a cooldown since the last cue. Placeholder: HOLD."""
    return GateResult("min-interval", passed=False, detail=_PLACEHOLDER)


def gate_max_per_night(ctx: DecisionContext) -> GateResult:
    """Cap cues per sleep session. Placeholder: HOLD."""
    return GateResult("max-per-night", passed=False, detail=_PLACEHOLDER)


def gate_stale_axis(ctx: DecisionContext) -> GateResult:
    """Refuse to act on stale state (mirrors L3 freshness). Placeholder: HOLD."""
    return GateResult("stale-axis", passed=False, detail=_PLACEHOLDER)


def gate_unknown_speaker(ctx: DecisionContext) -> GateResult:
    """Refuse unless the speaker is confirmed to be the user. Placeholder: HOLD."""
    return GateResult("unknown-speaker", passed=False, detail=_PLACEHOLDER)


SLEEP_CUE_GATES: list[Gate] = [
    gate_deep_sleep_suppression,
    gate_min_interval,
    gate_max_per_night,
    gate_stale_axis,
    gate_unknown_speaker,
]


class SleepCuePolicy:
    """Witness-mode cue policy: interject only if ALL gates clear; else HOLD."""

    name = "sleep_cue"

    def decide(self, ctx: DecisionContext) -> ActionDecision:
        results = run_gates(SLEEP_CUE_GATES, ctx)
        trace = gate_trace_dict(results, policy=self.name)
        cleared = trace["all_passed"]
        return ActionDecision(
            user_id=ctx.user_id,
            decided_at=ctx.now,
            action="interject" if cleared else "hold",
            rationale=("all sleep-cue gates cleared" if cleared
                       else "blocked by sleep-cue safety gates (placeholder phase)"),
            mode="witness",
            content_kind="rem_whisper" if cleared else None,
            gate_trace=trace,
            i_model_id=ctx.i_model_id,
        )
