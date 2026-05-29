# apps/inference/decision/registry.py
"""Policy registry + selection, with an OFFLINE sentinel for 'no answer'.

Mirrors L3's freshness/OFFLINE pattern and L4's PREDICTION_OFFLINE: when no
policy can be resolved, selection returns the DECISION_OFFLINE policy, which
HOLDs and records why — never a crash, never a fabricated interject.
"""
from __future__ import annotations

from core.protocol.payloads import ActionDecision

from decision.intent_dispatch import policy_name_for
from decision.policies.default import DefaultPolicy
from decision.policies.sleep_cue import SleepCuePolicy
from decision.policy import DecisionContext, Policy, gate_trace_dict


class _OfflinePolicy:
    """Sentinel policy: the layer has no answer, so HOLD and say so."""

    name = "decision_offline"

    def decide(self, ctx: DecisionContext) -> ActionDecision:
        trace = gate_trace_dict([], policy=self.name)
        trace["offline"] = True
        return ActionDecision(
            user_id=ctx.user_id,
            decided_at=ctx.now,
            action="hold",
            rationale="decision layer offline — no applicable policy; holding (safe)",
            mode=None,
            content_kind=None,
            gate_trace=trace,
            i_model_id=ctx.i_model_id,
        )


DECISION_OFFLINE: Policy = _OfflinePolicy()

_REGISTRY: dict[str, Policy] = {
    SleepCuePolicy.name: SleepCuePolicy(),
    DefaultPolicy.name: DefaultPolicy(),
    DECISION_OFFLINE.name: DECISION_OFFLINE,
}


def get_policy(name: str) -> Policy:
    """Look up a policy by name; OFFLINE sentinel if unknown."""
    return _REGISTRY.get(name, DECISION_OFFLINE)


def select_policy(ctx: DecisionContext) -> Policy:
    """Resolve the applicable policy for a context (via intent dispatch)."""
    return get_policy(policy_name_for(ctx))
