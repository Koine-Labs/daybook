# apps/inference/output/test_speaker.py
"""L6 TTS sink smoke test — drives TOPIC_OUTPUT into a recorder speak-callable.

No audio / no network: register_speaker takes an injected `speak` that just
collects strings. A real-TTS / real-composer path here would be a failure.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.bus.bus import TOPIC_OUTPUT, MessageBus
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import OutputDirective

from output.speaker import register_speaker


def _output_envelope(directive: OutputDirective) -> MessageEnvelope:
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.OUTPUT,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=datetime.now(timezone.utc),
        meta_context=MetaContext.WAKING,
        consent_scope="default",
        trace_id=str(uuid.uuid4()),
        payload=directive,
    )


def _voice_directive(text: str | None) -> OutputDirective:
    return OutputDirective(
        user_id="u1",
        created_at=datetime.now(timezone.utc),
        channel="voice",
        mode="companion",
        text=text,
        delivery={"pacing": "conversational"},
    )


def _silent_directive() -> OutputDirective:
    return OutputDirective(
        user_id="u1",
        created_at=datetime.now(timezone.utc),
        channel="visual",
        mode="witness",
        text=None,
        delivery={"silent": True},
    )


def test_voice_directive_is_spoken():
    bus = MessageBus()
    spoken: list[str] = []
    register_speaker(bus, speak=spoken.append)

    bus.publish(TOPIC_OUTPUT, _output_envelope(_voice_directive("Hey, you.")))

    assert spoken == ["Hey, you."]


def test_silent_visual_directive_not_spoken():
    bus = MessageBus()
    spoken: list[str] = []
    register_speaker(bus, speak=spoken.append)

    # visual / no-text (deep sleep, #14) — must never be spoken.
    bus.publish(TOPIC_OUTPUT, _output_envelope(_silent_directive()))
    # a voice directive with empty text is also nothing to say.
    bus.publish(TOPIC_OUTPUT, _output_envelope(_voice_directive("")))

    assert spoken == []


def test_foreign_payload_does_not_crash():
    bus = MessageBus()
    spoken: list[str] = []
    register_speaker(bus, speak=spoken.append)

    foreign = MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.ACTION,  # wrong payload type on the topic
        source_role=NodeRole.DESKTOP_COMPUTE,
        occurred_at=datetime.now(timezone.utc),
        meta_context=MetaContext.WAKING,
        consent_scope="default",
        trace_id=str(uuid.uuid4()),
        payload="not a directive",  # type: ignore[arg-type]
    )
    bus.publish(TOPIC_OUTPUT, foreign)  # must not raise

    assert spoken == []
