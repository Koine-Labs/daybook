"""Tests for the L1 declaration adapter."""
from __future__ import annotations

from core.bus.bus import TOPIC_SIGNAL, MessageBus
from core.protocol.enums import Intent, Modality
from core.protocol.payloads import SignalPacket
from sensors.declare_adapter import (
    CONSENT_SCOPE,
    KIND_STATE_DECLARATION,
    DeclarationBusSink,
)


def _collect(bus: MessageBus) -> list:
    captured: list = []
    bus.subscribe(TOPIC_SIGNAL, lambda env: captured.append(env))
    return captured


def test_declare_publishes_explicit_text_signal():
    bus = MessageBus()
    captured = _collect(bus)
    sink = DeclarationBusSink(bus, user_id="u1")
    sink.declare("I'm locked in")

    assert len(captured) == 1
    packet = captured[0].payload
    assert isinstance(packet, SignalPacket)
    assert packet.modality == Modality.TEXT.value
    assert packet.intent == Intent.EXPLICIT.value
    assert packet.kind == KIND_STATE_DECLARATION
    assert packet.payload["text"] == "I'm locked in"
    assert packet.payload["consent_scope"] == CONSENT_SCOPE
    # the ENVELOPE itself carries the self-report scope (#11), not just the payload.
    assert captured[0].consent_scope == "self_report_v1"
    assert packet.user_id == "u1"


def test_declare_per_call_user_override():
    bus = MessageBus()
    captured = _collect(bus)
    DeclarationBusSink(bus, user_id="default").declare("wiped", user_id="other")
    assert captured[0].payload.user_id == "other"
