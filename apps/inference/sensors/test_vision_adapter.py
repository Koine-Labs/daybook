"""L1 vision producer + synthetic generator — no DB, no network, no model.

The synthetic frame is already a semantic dict (no pixels exist in CI). Tests
assert no raw image bytes ride the bus (#11), determinism by index, and the
consent fix is proven through the real sensors.participant.emit path.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pytest

from core.bus.bus import TOPIC_SIGNAL, MessageBus
from core.protocol.enums import MetaContext
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import SignalPacket
from sensors.contract import DEFAULT_USER_ID
from sensors.vision_adapter import VisionBusSink, synthesize_vision_frame
from vision.perception import KIND_VISUAL_SCENE, SETTINGS, VISION_SOURCE

USER = DEFAULT_USER_ID

_SCENE_KEYS = {"setting", "people_present", "salient_objects", "text_present", "model"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_synthesize_returns_well_formed_semantic_dict():
    s = synthesize_vision_frame(index=0)
    assert set(s) == _SCENE_KEYS
    assert s["setting"] in SETTINGS
    assert isinstance(s["people_present"], int) and s["people_present"] >= 0
    assert isinstance(s["salient_objects"], list)
    assert all(isinstance(o, str) for o in s["salient_objects"])
    assert isinstance(s["text_present"], bool)
    assert s["model"] == "synthetic"


def test_synthesize_is_deterministic_by_index():
    assert synthesize_vision_frame(index=3) == synthesize_vision_frame(index=3)
    assert synthesize_vision_frame(index=0) != synthesize_vision_frame(index=1)


def test_synthesize_varies_setting_and_people_across_indices():
    settings = {synthesize_vision_frame(index=i)["setting"] for i in range(8)}
    people = {synthesize_vision_frame(index=i)["people_present"] for i in range(8)}
    assert len(settings) > 1
    assert len(people) > 1


def test_synthesize_never_carries_pixels():
    s = synthesize_vision_frame(index=2)
    for forbidden in ("image", "image_bytes", "pixels", "raw", "frame", "jpeg", "png"):
        assert forbidden not in s
    assert not any(isinstance(v, (bytes, bytearray)) for v in s.values())


def _capture_one(sink_fn) -> MessageEnvelope:
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_SIGNAL, captured.append)
    sink_fn(bus, captured)
    assert len(captured) == 1
    env = captured[0]
    assert isinstance(env.payload, SignalPacket)
    return env


def test_emit_scene_produces_well_formed_vision_signal():
    def run(bus, captured):
        sink = VisionBusSink(bus, meta_context=MetaContext.WAKING)
        sink.emit_scene(synthesize_vision_frame(index=1), timestamp=_now(), user_id=USER)

    env = _capture_one(run)
    pkt = env.payload
    assert pkt.modality == "vision"
    assert pkt.intent == "continuous"
    assert pkt.kind == KIND_VISUAL_SCENE == "visual_scene"
    assert pkt.source == VISION_SOURCE == "camera.visual_scene"
    assert set(pkt.payload) == _SCENE_KEYS


def test_emit_scene_rides_under_vision_consent_scope():
    def run(bus, captured):
        sink = VisionBusSink(bus)
        sink.emit_scene(synthesize_vision_frame(index=0), timestamp=_now())

    env = _capture_one(run)
    assert env.consent_scope == "camera_continuous_v1"
    assert env.consent_scope != "unscoped_v0"


def test_emit_scene_carries_only_semantic_keys_no_pixels():
    forbidden = ("image", "image_bytes", "pixels", "raw", "frame", "jpeg", "png", "bytes")
    poisoned = dict(synthesize_vision_frame(index=4))
    poisoned["image_bytes"] = b"\xff\xd8\xff"  # a JPEG header — must NOT ride the bus

    def run(bus, captured):
        sink = VisionBusSink(bus)
        sink.emit_scene(poisoned, timestamp=_now())

    env = _capture_one(run)
    pkt = env.payload
    assert set(pkt.payload) == _SCENE_KEYS
    for key in forbidden:
        assert key not in pkt.payload
    assert not any(isinstance(v, (bytes, bytearray)) for v in pkt.payload.values())


def test_emit_scene_returns_envelope_and_propagates_i_model_id():
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_SIGNAL, captured.append)
    sink = VisionBusSink(bus, meta_context=MetaContext.WAKING)
    imid = "11111111-1111-1111-1111-111111111111"
    env = sink.emit_scene(synthesize_vision_frame(index=0), timestamp=_now(), i_model_id=imid)
    assert isinstance(env, MessageEnvelope)
    assert env.i_model_id == imid
    assert env.meta_context == MetaContext.WAKING
    assert captured[0] is env


def test_vision_reading_consent_scope_is_vision_not_unscoped():
    from sensors.contract import IntentTaggedReading
    from sensors.participant import consent_scope_for

    reading = IntentTaggedReading(
        modality="vision", intent="continuous", kind="visual_scene",
        payload={"setting": "outdoor"}, source="camera.visual_scene",
        timestamp=_now(), user_id=USER,
    )
    assert consent_scope_for(reading) == "camera_continuous_v1"
    assert consent_scope_for(reading) != "unscoped_v0"


def test_emit_scene_rejects_bytes_under_a_known_scene_key():
    # Projection strips UNKNOWN keys; this guards the OTHER path — raw bytes
    # smuggled under a LEGITIMATE scene key must be rejected, never published (#11).
    poisoned = dict(synthesize_vision_frame(index=1))
    poisoned["model"] = b"\xff\xd8\xff"  # a JPEG header hidden under a real key
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_SIGNAL, captured.append)
    sink = VisionBusSink(bus)
    with pytest.raises(ValueError, match="raw bytes"):
        sink.emit_scene(poisoned, timestamp=_now())
    assert captured == []  # the invariant held: nothing rode the bus


def test_adapter_and_perception_import_clean_with_no_model():
    importlib.import_module("vision.perception")
    importlib.import_module("sensors.vision_adapter")
