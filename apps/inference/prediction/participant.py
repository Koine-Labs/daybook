# apps/inference/prediction/participant.py
"""L4 bus participant — BeliefState (TOPIC_BELIEF) -> Prediction (TOPIC_PREDICTION).

For each fresh axis in the inbound BeliefState, selects a predictor by
(axis, meta_context) and emits one Prediction envelope. Unpredictable axes
emit PREDICTION_OFFLINE — never a crash. Every outbound envelope inherits
trace_id / meta_context / consent_scope / i_model_id via core/layer.py so one
stimulus stays followable L1->L6 (#14/#11/#1).
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.bus.bus import TOPIC_BELIEF, TOPIC_PREDICTION, MessageBus
from core.layer import forward_envelope
from core.nodes import role_for
from core.protocol.enums import PayloadType
from core.protocol.envelope import MessageEnvelope
from fusion.belief_state import BeliefState

from . import registry
from .interface import predict

# Default forecast horizon for the skeleton; fill specs will make this per-axis.
DEFAULT_HORIZON_SECONDS = 300

SOURCE_ROLE = role_for("L4.prediction")


def _predict_axis(
    bs: BeliefState,
    axis: str,
    meta_context: str,
    *,
    horizon_seconds: int,
    now: datetime,
    i_model_id: str | None,
):
    """Forecast a single fresh axis, falling back to PREDICTION_OFFLINE."""
    est = bs.get(axis, now=now)
    predictor = registry.select(axis, meta_context)
    pred = predict(
        user_id=bs.user_id,
        axis=axis,
        estimate=est,
        horizon_seconds=horizon_seconds,
        predictor=predictor,
        now=now,
        i_model_id=i_model_id,
    )
    # AxisEstimate carries no user_id; the BeliefState owns it. Stamp it so a
    # standalone StubPredictor result reflects the real user.
    pred.user_id = bs.user_id
    return pred


def handle_belief(bus: MessageBus, inbound: MessageEnvelope) -> list[MessageEnvelope]:
    """Process one BeliefState envelope, publishing one Prediction per fresh axis."""
    if not isinstance(inbound.payload, BeliefState):
        return []  # not ours; degrade, never crash the bus
    bs: BeliefState = inbound.payload
    now = datetime.now(timezone.utc)
    meta_context = inbound.meta_context.value

    published: list[MessageEnvelope] = []
    fresh_axes = sorted(ax for ax in bs.estimates if bs.get(ax, now=now) is not None)
    for axis in fresh_axes:
        pred = _predict_axis(
            bs,
            axis,
            meta_context,
            horizon_seconds=DEFAULT_HORIZON_SECONDS,
            now=now,
            i_model_id=inbound.i_model_id,
        )
        out = forward_envelope(
            inbound,
            ptype=PayloadType.PREDICTION,
            payload=pred,
            source_role=SOURCE_ROLE,
        )
        bus.publish(TOPIC_PREDICTION, out)
        published.append(out)
    return published


def register(bus: MessageBus) -> None:
    """Subscribe the L4 participant to TOPIC_BELIEF."""

    def _on_belief(env: MessageEnvelope) -> None:
        handle_belief(bus, env)

    bus.subscribe(TOPIC_BELIEF, _on_belief)
