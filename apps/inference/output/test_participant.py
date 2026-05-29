# apps/inference/output/test_participant.py
"""L6 Output participant smoke test — drives TOPIC_ACTION → TOPIC_OUTPUT in-process.

No network/LLM: the participant runs with the default StubRenderer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.bus.bus import TOPIC_ACTION, TOPIC_OUTPUT, MessageBus
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import ActionDecision, OutputDirective

from output.channels import CHANNEL_SILENT, select_channel
from output.participant import register


def _action_envelope(
    *, action: str, meta: MetaContext, gate_trace: dict | None = None
) -> MessageEnvelope:
    decision = ActionDecision(
        user_id="u1",
        decided_at=datetime.now(timezone.utc),
        action=action,  # type: ignore[arg-type]
        rationale="smoke",
        mode="companion",
        content_kind="conversation_tease",
        gate_trace=gate_trace or {},
    )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.ACTION,
        source_role=NodeRole.DESKTOP_COMPUTE,
        occurred_at=datetime.now(timezone.utc),
        meta_context=meta,
        consent_scope="default",
        trace_id=str(uuid.uuid4()),
        payload=decision,
    )


def _capture(bus: MessageBus) -> list[MessageEnvelope]:
    received: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_OUTPUT, received.append)
    return received


def test_interject_waking_emits_voice_directive_same_trace():
    bus = MessageBus()
    register(bus)
    out = _capture(bus)

    env = _action_envelope(action="interject", meta=MetaContext.WAKING)
    bus.publish(TOPIC_ACTION, env)

    assert len(out) == 1
    directive = out[0].payload
    assert isinstance(directive, OutputDirective)
    assert directive.channel == "voice"
    assert directive.text  # stub renderer produced placeholder text
    assert out[0].trace_id == env.trace_id
    assert out[0].type == PayloadType.OUTPUT
    assert out[0].source_role == NodeRole.WISP_EDGE
    # consent + meta_context inherited from inbound
    assert out[0].consent_scope == env.consent_scope
    assert out[0].meta_context == env.meta_context


def test_deep_sleep_suppresses_voice():
    bus = MessageBus()
    register(bus)
    out = _capture(bus)

    env = _action_envelope(
        action="interject", meta=MetaContext.SLEEP, gate_trace={"sub_state": "deep"}
    )
    bus.publish(TOPIC_ACTION, env)

    assert len(out) == 1
    directive = out[0].payload
    assert isinstance(directive, OutputDirective)
    assert directive.channel != "voice"
    assert directive.text is None
    assert directive.delivery.get("silent") is True
    assert out[0].trace_id == env.trace_id  # trace still followable to L6


def test_hold_emits_no_directive():
    bus = MessageBus()
    register(bus)
    out = _capture(bus)

    env = _action_envelope(action="hold", meta=MetaContext.WAKING)
    bus.publish(TOPIC_ACTION, env)

    assert out == []


def test_channel_registry_directly():
    # waking → voice (primary, #3)
    assert select_channel(MetaContext.WAKING).channel == "voice"
    # deep sleep → silent sentinel (#14)
    assert select_channel(MetaContext.SLEEP, sub_state="deep").channel == CHANNEL_SILENT
    # light/awake-in-bed sleep → reverent voice whisper permitted
    light = select_channel(MetaContext.SLEEP, sub_state="awake-in-bed")
    assert light.channel == "voice"
    assert light.delivery.get("pacing") == "whisper"
    # unknown context → fail-safe silence
    assert select_channel(MetaContext.UNKNOWN).channel == CHANNEL_SILENT
