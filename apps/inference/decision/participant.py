# apps/inference/decision/participant.py
"""L5 Decision bus participant: TOPIC_PREDICTION -> TOPIC_ACTION.

Reads a Prediction envelope, lifts a DecisionContext, dispatches by intent/
meta-context to a policy, and publishes the resulting ActionDecision (default
action='hold') with a populated gate_trace. Runs as NodeRole.DESKTOP_COMPUTE.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.bus.bus import TOPIC_ACTION, TOPIC_PREDICTION, MessageBus
from core.layer import forward_envelope
from core.nodes import role_for
from core.protocol.enums import PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import Prediction

from decision.policy import DecisionContext
from decision.registry import select_policy

SOURCE_ROLE = role_for("L5.decision")


def _context_from(env: MessageEnvelope) -> DecisionContext:
    """Lift a DecisionContext off an inbound Prediction envelope."""
    pred = env.payload  # Prediction
    return DecisionContext(
        user_id=pred.user_id,
        prediction=pred,
        meta_context=env.meta_context,
        consent_scope=env.consent_scope,
        now=datetime.now(timezone.utc),
        i_model_id=env.i_model_id,
    )


def decide(env: MessageEnvelope) -> MessageEnvelope:
    """Pure transform: Prediction envelope -> ActionDecision envelope."""
    ctx = _context_from(env)
    policy = select_policy(ctx)
    decision = policy.decide(ctx)
    return forward_envelope(env, ptype=PayloadType.ACTION, payload=decision,
                            source_role=SOURCE_ROLE)


def register(bus: MessageBus) -> None:
    """Subscribe the L5 decision handler to the prediction topic."""

    def _handler(env: MessageEnvelope) -> None:
        if not isinstance(env.payload, Prediction):
            return  # not ours; degrade, never crash the bus
        bus.publish(TOPIC_ACTION, decide(env))

    bus.subscribe(TOPIC_PREDICTION, _handler)
