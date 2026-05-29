from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from core.bus.bus import TOPIC_FEATURE, TOPIC_SIGNAL, MessageBus
from core.protocol.enums import Intent, MetaContext, Modality, NodeRole, PayloadType
from core.protocol.payloads import SignalPacket
from sensors import emit
from sensors.contract import DEFAULT_USER_ID, IntentTaggedReading, to_signal_packet
from sensors.participant import DEFAULT_CONSENT_SCOPE, build_signal_envelope, consent_scope_for


def _reading(**overrides) -> IntentTaggedReading:
    base = dict(
        modality=Modality.GESTURE.value,
        intent=Intent.CONTINUOUS.value,
        kind="mac_activity",
        payload={"active_app": "Terminal", "idle_seconds": 3.2},
        source="mac.app_activity",
        timestamp=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return IntentTaggedReading(**base)


def test_reading_to_signal_packet_carries_modality_and_intent():
    sig = _reading().to_signal_packet()
    assert isinstance(sig, SignalPacket)
    assert sig.modality == Modality.GESTURE.value
    assert sig.intent == Intent.CONTINUOUS.value
    assert sig.kind == "mac_activity"
    assert sig.user_id == DEFAULT_USER_ID
    assert to_signal_packet(_reading()).source == "mac.app_activity"


def test_reading_rejects_naive_timestamp():
    with pytest.raises(ValueError):
        _reading(timestamp=datetime.now())


def test_reading_rejects_unknown_modality():
    with pytest.raises(ValueError):
        _reading(modality="telepathy")


def test_reading_rejects_unknown_intent():
    with pytest.raises(ValueError):
        _reading(intent="loud")


def test_emit_publishes_signal_envelope_on_topic_signal():
    bus = MessageBus()
    got: list = []
    bus.subscribe(TOPIC_SIGNAL, got.append)

    reading = _reading()
    env = emit(bus, reading)

    assert len(got) == 1
    landed = got[0]
    assert landed is env
    assert landed.type == PayloadType.SIGNAL
    assert landed.source_role == NodeRole.WISP_EDGE
    assert landed.occurred_at.tzinfo is not None
    # The envelope carries the reading's modality + intent (commitment #10).
    assert landed.payload.modality == reading.modality
    assert landed.payload.intent == reading.intent
    assert landed.payload.kind == "mac_activity"


def test_emit_uses_fresh_trace_id_and_is_serializable():
    bus = MessageBus()
    got: list = []
    bus.subscribe(TOPIC_SIGNAL, got.append)
    env = emit(bus, _reading())
    uuid.UUID(env.trace_id)   # raises if not a valid uuid
    uuid.UUID(env.id)
    d = env.to_dict()          # exercises the codec / JSON-readiness
    assert d["type"] == PayloadType.SIGNAL.value
    assert d["payload"]["modality"] == Modality.GESTURE.value


def test_emit_does_not_leak_onto_other_topics():
    bus = MessageBus()
    other: list = []
    bus.subscribe(TOPIC_FEATURE, other.append)
    emit(bus, _reading())
    assert other == []


def test_default_meta_context_is_unknown_and_overridable():
    assert build_signal_envelope(_reading()).meta_context == MetaContext.UNKNOWN
    waking = build_signal_envelope(_reading(), meta_context=MetaContext.WAKING)
    assert waking.meta_context == MetaContext.WAKING


def test_consent_scope_selected_per_source_and_modality():
    assert consent_scope_for(_reading(source="mac.app_activity")) == "mac_activity_v1"
    assert consent_scope_for(_reading(modality=Modality.BIOMETRIC.value, source="watch.hr_30s")) == "apple_health_v1"
    assert consent_scope_for(_reading(modality=Modality.VOICE.value, source="mac.mic")) == "mac_activity_v1"
    # BCI rides under its own opt-in scope now (no longer the unscoped fallback).
    assert consent_scope_for(_reading(modality=Modality.BCI.value, source="exg.eeg")) == "eeg_continuous_v1"
    # A still-unmapped modality (vision) keeps exercising the DEFAULT fallback.
    assert consent_scope_for(_reading(modality=Modality.VISION.value, source="cam.front")) == DEFAULT_CONSENT_SCOPE


def test_mac_adapter_wraps_capture_once(monkeypatch):
    from features.snapshot import FeatureSnapshot
    import sensors.mac_adapter as mac_adapter

    fake = FeatureSnapshot(
        user_id=DEFAULT_USER_ID,
        timestamp=datetime.now(timezone.utc),
        modality="mac",
        source="mac.app_activity",
        payload={"active_app": "Xcode", "idle_seconds": 0.0},
        meta_context_hint="waking",
    )
    monkeypatch.setattr(mac_adapter, "capture_once", lambda user_id=DEFAULT_USER_ID: fake)

    reading = mac_adapter.capture_mac_reading()
    assert reading.modality == Modality.GESTURE.value
    assert reading.intent == Intent.CONTINUOUS.value
    assert reading.kind == "mac_activity"
    assert reading.source == "mac.app_activity"
    assert reading.payload["active_app"] == "Xcode"

    # And it flows through emit cleanly.
    bus = MessageBus()
    got: list = []
    bus.subscribe(TOPIC_SIGNAL, got.append)
    emit(bus, reading)
    assert got[0].payload.modality == Modality.GESTURE.value
