"""Full vision lane arc — synthetic scene -> L1 -> L2 -> L3 visual_context belief.

The headline integration test, mirroring bci/test_bci_lane_arc.py: DEFAULT
registry, NO DB, NO network, NO model. The synthetic frame is already a semantic
dict (no pixels exist in CI); only the visual_scene semantic packet rides the bus
(#11). Asserts trace_id / meta_context(WAKING) / consent_scope / i_model_id
propagate L1 -> L3 (#1/#11/#14).
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.bus.bus import TOPIC_BELIEF, MessageBus
from core.protocol.enums import MetaContext
from core.protocol.envelope import MessageEnvelope
from features import participant as features_participant
from fusion import participant as fusion_participant
from fusion.belief_state import BeliefState
from sensors.vision_adapter import VisionBusSink, synthesize_vision_frame

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

_IMID = "33333333-3333-3333-3333-333333333333"


def _run_frame(index: int) -> tuple[list[MessageEnvelope], MessageEnvelope, datetime]:
    now = datetime.now(timezone.utc)
    bus = MessageBus()
    beliefs: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_BELIEF, beliefs.append)

    features_participant.register(bus)          # L2: real EXTRACTORS incl. vision_scene.extract
    fusion_participant.register(bus)            # L3: real AXIS_REGISTRY incl. visual_context
    sink = VisionBusSink(bus, meta_context=MetaContext.WAKING)  # L1

    l1 = sink.emit_scene(synthesize_vision_frame(index=index), timestamp=now, i_model_id=_IMID)
    return beliefs, l1, now


def test_scene_yields_visual_context_belief_no_db():
    beliefs, _l1, now = _run_frame(index=1)  # index 1 -> indoor, 1 person
    assert beliefs, "no belief published"
    belief = beliefs[-1].payload
    assert isinstance(belief, BeliefState)

    est = belief.get("visual_context", now=now)
    assert est is not None
    assert est.value["setting"] in ("outdoor", "indoor", "transit", "screen", "unknown")
    assert est.value["category"] in {"alone", "with_people"}
    assert est.value["scaffold"] is True
    assert est.source.endswith("v1_heuristic")
    assert est.meta_context == "waking"

    # A scene with a person maps to with_people; index 1 carries 1 person.
    assert est.value["people_present"] is True
    assert est.value["category"] == "with_people"

    # DB-backed axes degrade to OFFLINE for a vision packet (no DB touched).
    assert belief.get("meta_context", now=now) is None
    assert belief.get("sleep_stage", now=now) is None
    assert belief.get("audio_social_context", now=now) is None
    assert belief.get("cognitive_load", now=now) is None

    # Trace preserved end-to-end; envelope serializes (NetworkTransport-safe).
    assert beliefs[-1].to_dict()


def test_alone_scene_yields_alone_category():
    # index 0 -> outdoor, 0 people -> alone.
    beliefs, _l1, now = _run_frame(index=0)
    est = beliefs[-1].payload.get("visual_context", now=now)
    assert est.value["people_present"] is False
    assert est.value["category"] == "alone"


def test_trace_meta_consent_imodel_propagate_l1_to_l3():
    beliefs, l1, _now = _run_frame(index=1)
    l3 = beliefs[-1]
    assert l3.trace_id == l1.trace_id
    assert l3.meta_context == MetaContext.WAKING
    assert l3.consent_scope == "camera_continuous_v1"
    assert l3.consent_scope != "unscoped_v0"
    assert l3.i_model_id == _IMID


def test_no_raw_pixels_ride_the_bus():
    beliefs, _l1, _now = _run_frame(index=4)
    import json
    blob = json.dumps(beliefs[-1].to_dict(), default=str)
    for forbidden in ('"image_bytes"', '"pixels"', '"raw"', '"frame"', '"jpeg"', '"png"'):
        assert forbidden not in blob
