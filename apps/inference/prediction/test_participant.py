from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bus.bus import TOPIC_BELIEF, TOPIC_PREDICTION, MessageBus  # noqa: E402
from core.protocol.codec import payload_to_dict  # noqa: E402
from core.protocol.enums import MetaContext, NodeRole, PayloadType  # noqa: E402
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from fusion.belief_state import AxisEstimate, BeliefState  # noqa: E402
from prediction import PREDICTION_OFFLINE  # noqa: E402
from prediction import participant as l4  # noqa: E402

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _belief_envelope(*, with_unregistered: bool = False) -> MessageEnvelope:
    now = datetime.now(timezone.utc)
    bs = BeliefState(user_id=USER)
    bs.update(
        AxisEstimate(
            axis="meta_context",
            value={"category": "waking/focused"},
            timestamp=now,
            confidence=0.8,
            source="L3.fusion.meta_context",
        )
    )
    if with_unregistered:
        bs.update(
            AxisEstimate(
                axis="valence",  # no predictor registered for this axis
                value={"label": "neutral"},
                timestamp=now,
                confidence=0.5,
                source="L3.fusion.valence",
            )
        )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.BELIEF,
        source_role=NodeRole.DESKTOP_COMPUTE,
        occurred_at=now,
        meta_context=MetaContext.WAKING,
        consent_scope="mic_continuous_v1",
        trace_id=str(uuid.uuid4()),
        payload=bs,
        i_model_id="im-abc-123",
    )


def _drive(inbound: MessageEnvelope) -> list[MessageEnvelope]:
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_PREDICTION, lambda env: captured.append(env))
    l4.register(bus)
    bus.publish(TOPIC_BELIEF, inbound)
    return captured


def test_belief_yields_prediction_with_same_trace_id():
    inbound = _belief_envelope()
    out = _drive(inbound)
    assert len(out) == 1
    pred_env = out[0]
    assert pred_env.type == PayloadType.PREDICTION
    assert pred_env.trace_id == inbound.trace_id
    assert pred_env.meta_context == inbound.meta_context
    assert pred_env.consent_scope == inbound.consent_scope
    assert pred_env.i_model_id == inbound.i_model_id
    assert pred_env.source_role == NodeRole.DESKTOP_COMPUTE
    assert pred_env.payload.axis == "meta_context"
    assert pred_env.payload.user_id == USER


def test_registered_axis_uses_stub_not_offline():
    out = _drive(_belief_envelope())
    pred = out[0].payload
    assert pred.model_id != PREDICTION_OFFLINE
    assert pred.provenance == "placeholder"
    assert pred.cold_start is True
    assert pred.confidence is None  # never fabricate confidence
    assert pred.distribution["informative"] is False


def test_unregistered_axis_yields_prediction_offline():
    out = _drive(_belief_envelope(with_unregistered=True))
    by_axis = {env.payload.axis: env.payload for env in out}
    assert "valence" in by_axis, "unregistered axis must still emit a packet"
    offline = by_axis["valence"]
    assert offline.model_id == PREDICTION_OFFLINE
    assert offline.confidence is None
    assert offline.cold_start is True
    assert offline.distribution["kind"] == "offline"
    # registered axis in the same belief still gets a real stub prediction
    assert by_axis["meta_context"].model_id != PREDICTION_OFFLINE


def test_prediction_payload_is_json_ready():
    out = _drive(_belief_envelope(with_unregistered=True))
    for env in out:
        d = payload_to_dict(PayloadType.PREDICTION, env.payload)
        assert d["axis"] == env.payload.axis
        assert isinstance(d["made_at"], str)
        # action seam present (#15/#16), null in the baseline path
        assert d["action"] is None
        assert d["horizon_seconds"] == l4.DEFAULT_HORIZON_SECONDS


def test_stale_axis_is_skipped():
    now = datetime.now(timezone.utc)
    stale = now.replace(year=now.year - 1)
    bs = BeliefState(user_id=USER)
    bs.update(
        AxisEstimate(
            axis="meta_context",
            value={"category": "waking/focused"},
            timestamp=stale,
            confidence=0.8,
            source="L3.fusion.meta_context",
            fresh_for_seconds=120,
        )
    )
    inbound = MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.BELIEF,
        source_role=NodeRole.DESKTOP_COMPUTE,
        occurred_at=now,
        meta_context=MetaContext.WAKING,
        consent_scope="mic_continuous_v1",
        trace_id=str(uuid.uuid4()),
        payload=bs,
    )
    out = _drive(inbound)
    assert out == [], "stale axes must not produce predictions"
