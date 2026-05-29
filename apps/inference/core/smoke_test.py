"""End-to-end reflex arc through the bus — proves the nerves carry a full L1->L6
trace. Run: python -m core.smoke_test (from apps/inference)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.bus.bus import (TOPIC_ACTION, TOPIC_BELIEF, TOPIC_FEATURE, TOPIC_OUTPUT,
                          TOPIC_PREDICTION, TOPIC_SIGNAL, MessageBus)
from core.protocol.enums import (Intent, MetaContext, Modality, NodeRole, PayloadType)
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import (ActionDecision, FeatureSnapshot, OutputDirective,
                                     Prediction, SignalPacket)
from fusion.belief_state import AxisEstimate, BeliefState

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _utc():
    return datetime.now(timezone.utc)


def _env(ptype, payload, trace, role):
    return MessageEnvelope(id=str(uuid.uuid4()), type=ptype, source_role=role,
                           occurred_at=_utc(), meta_context=MetaContext.WAKING,
                           consent_scope="mic_continuous_v1", trace_id=trace,
                           payload=payload)


def run_reflex_arc() -> MessageEnvelope:
    bus = MessageBus()
    received: list[MessageEnvelope] = []

    def l2(env):  # L1 signal -> L2 feature
        sig = env.payload
        snap = FeatureSnapshot(user_id=sig.user_id, timestamp=sig.timestamp,
                               modality=sig.modality, source=sig.source,
                               payload={"echo": sig.payload}, intent=sig.intent)
        bus.publish(TOPIC_FEATURE, _env(PayloadType.FEATURE, snap, env.trace_id,
                                        NodeRole.WISP_EDGE))

    def l3(env):  # L2 feature -> L3 belief
        snap = env.payload
        bs = BeliefState(user_id=snap.user_id)
        bs.update(AxisEstimate(axis="arousal_inferred", value={"label": "calm"},
                               timestamp=snap.timestamp, confidence=0.5, source="L3.stub"))
        bus.publish(TOPIC_BELIEF, _env(PayloadType.BELIEF, bs, env.trace_id,
                                       NodeRole.DESKTOP_COMPUTE))

    def l4(env):  # L3 belief -> L4 prediction
        bs = env.payload
        pred = Prediction(user_id=bs.user_id, axis="arousal_inferred", made_at=_utc(),
                          horizon_seconds=1800, distribution={"calm": 0.7, "tense": 0.3},
                          model_id="stub.v0")
        bus.publish(TOPIC_PREDICTION, _env(PayloadType.PREDICTION, pred, env.trace_id,
                                           NodeRole.DESKTOP_COMPUTE))

    def l5(env):  # L4 prediction -> L5 action
        pred = env.payload
        dec = ActionDecision(user_id=pred.user_id, decided_at=_utc(), action="hold",
                             rationale="stub: nothing worth saying",
                             gate_trace={"novelty": "below_threshold"})
        bus.publish(TOPIC_ACTION, _env(PayloadType.ACTION, dec, env.trace_id,
                                       NodeRole.DESKTOP_COMPUTE))

    def l6(env):  # L5 action -> L6 output
        dec = env.payload
        out = OutputDirective(user_id=dec.user_id, created_at=_utc(), channel="voice",
                              mode="companion",
                              text=None if dec.action == "hold" else "…")
        bus.publish(TOPIC_OUTPUT, _env(PayloadType.OUTPUT, out, env.trace_id,
                                       NodeRole.WISP_EDGE))

    bus.subscribe(TOPIC_SIGNAL, l2)
    bus.subscribe(TOPIC_FEATURE, l3)
    bus.subscribe(TOPIC_BELIEF, l4)
    bus.subscribe(TOPIC_PREDICTION, l5)
    bus.subscribe(TOPIC_ACTION, l6)
    bus.subscribe(TOPIC_OUTPUT, received.append)

    trace = str(uuid.uuid4())
    sig = SignalPacket(user_id=USER, timestamp=_utc(), modality=Modality.AUDIO.value,
                       intent=Intent.CONTINUOUS.value, kind="speech_final",
                       payload={"text": "mm"}, source="mac.mic")
    bus.publish(TOPIC_SIGNAL, _env(PayloadType.SIGNAL, sig, trace, NodeRole.WISP_EDGE))

    assert len(received) == 1, f"expected 1 output, got {len(received)}"
    assert received[0].trace_id == trace, "trace_id not preserved across the arc"
    return received[0]


def test_reflex_arc_preserves_trace_and_reaches_l6():
    out = run_reflex_arc()
    assert out.type == PayloadType.OUTPUT
    assert isinstance(out.payload, OutputDirective)
    assert out.payload.channel == "voice"


if __name__ == "__main__":
    env = run_reflex_arc()
    print(f"reflex arc OK — trace {env.trace_id} reached L6 "
          f"({env.payload.channel}, mode={env.payload.mode})")
