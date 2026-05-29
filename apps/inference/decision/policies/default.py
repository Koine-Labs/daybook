# apps/inference/decision/policies/default.py
"""Default policy: hold unless clearly warranted (Companion-mode fallback).

Used for waking/unknown contexts where no specialized policy applies. Like the
sleep-cue policy, it defaults to silence; a single "clearly warranted" gate
gates any interjection and currently HOLDs (placeholder).
"""
from __future__ import annotations

from core.protocol.payloads import ActionDecision

from decision.policy import (DecisionContext, Gate, GateResult, gate_trace_dict,
                             run_gates)

_PLACEHOLDER = "placeholder: warrant signal not yet wired — default HOLD (safe)"


def gate_clearly_warranted(ctx: DecisionContext) -> GateResult:
    """Only speak when interjection is clearly warranted. Placeholder: HOLD."""
    return GateResult("clearly-warranted", passed=False, detail=_PLACEHOLDER)


DEFAULT_GATES: list[Gate] = [gate_clearly_warranted]


class DefaultPolicy:
    """Hold-unless-warranted Companion-mode policy. Default action is 'hold'."""

    name = "default"

    def decide(self, ctx: DecisionContext) -> ActionDecision:
        results = run_gates(DEFAULT_GATES, ctx)
        trace = gate_trace_dict(results, policy=self.name)
        cleared = trace["all_passed"]
        return ActionDecision(
            user_id=ctx.user_id,
            decided_at=ctx.now,
            action="interject" if cleared else "hold",
            rationale=("interjection clearly warranted" if cleared
                       else "no clear warrant to speak — holding (placeholder phase)"),
            mode="companion",
            content_kind=None,
            gate_trace=trace,
            i_model_id=ctx.i_model_id,
        )
