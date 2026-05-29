# apps/inference/decision/intent_dispatch.py
"""Intent dispatch: which policy applies for a given decision context.

Commitment #10 says L5 routes by *intent* (explicit vs continuous communication-
intent). At the decision boundary the active meta-context is the proxy for that
posture (commitment #14): Sleep context => continuous/Witness cueing (the
sleep-cue policy); Waking/Unknown context => the hold-unless-warranted default
(Companion posture). This is the single mapping point — add policies here, not
in the participant.
"""
from __future__ import annotations

from core.protocol.enums import MetaContext

from decision.policy import DecisionContext

# meta-context -> policy name (registry key). Sleep is the only specialized route today.
_POLICY_FOR_META: dict[MetaContext, str] = {
    MetaContext.SLEEP: "sleep_cue",
    MetaContext.WAKING: "default",
    MetaContext.UNKNOWN: "default",
}

DEFAULT_POLICY_NAME = "default"


def policy_name_for(ctx: DecisionContext) -> str:
    """Return the registry key of the policy that applies to this context."""
    return _POLICY_FOR_META.get(ctx.meta_context, DEFAULT_POLICY_NAME)
