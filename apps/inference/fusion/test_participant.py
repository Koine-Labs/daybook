"""L3 fusion participant smoke test — in-process, no DB/network.

Drives FusionParticipant over a real MessageBus with stub axis combiners:
publish a FeaturePacket envelope on TOPIC_FEATURE → assert a BeliefState
envelope lands on TOPIC_BELIEF with the same trace_id and >=1 AxisEstimate.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from core.bus.bus import TOPIC_BELIEF, TOPIC_FEATURE, MessageBus  # noqa: E402
from core.protocol.enums import MetaContext, NodeRole, PayloadType  # noqa: E402
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import FeatureSnapshot  # noqa: E402

from fusion import participant as P  # noqa: E402
from fusion.belief_state import AxisEstimate, BeliefState  # noqa: E402

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _packet(now: datetime) -> FeatureSnapshot:
    return FeatureSnapshot(
        user_id=USER,
        timestamp=now,
        modality="mac",
        source="mac.app_activity",
        payload={"active_app": "Cursor", "idle_seconds": 3},
        intent="continuous",
        confidence=0.9,
    )


def _inbound(now: datetime) -> MessageEnvelope:
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.FEATURE,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=now,
        meta_context=MetaContext.WAKING,
        consent_scope="continuous_sensing",
        trace_id=str(uuid.uuid4()),
        payload=_packet(now),
        i_model_id=None,
    )


def _stub_registry(now: datetime) -> dict[str, P.AxisCombiner]:
    """One axis returns a real estimate; one returns None (→ OFFLINE sentinel)."""

    def meta(_packet: FeatureSnapshot, _now: datetime) -> AxisEstimate:
        return AxisEstimate(
            axis="meta_context",
            value={"category": "waking/focused", "reason": "stub"},
            timestamp=now,
            confidence=0.65,
            source="L3.fusion.meta_context.stub",
            meta_context="waking/focused",
        )

    def offline(_packet: FeatureSnapshot, _now: datetime) -> None:
        return None

    return {"meta_context": meta, "sleep_stage": offline}


def test_feature_in_belief_out_same_trace():
    now = datetime.now(timezone.utc)
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_BELIEF, captured.append)

    P.register(bus, participant=P.FusionParticipant(registry=_stub_registry(now)))

    inbound = _inbound(now)
    bus.publish(TOPIC_FEATURE, inbound)

    assert len(captured) == 1
    out = captured[0]
    assert out.type == PayloadType.BELIEF
    assert out.trace_id == inbound.trace_id
    assert out.source_role == NodeRole.DESKTOP_COMPUTE
    assert out.meta_context == inbound.meta_context
    assert out.consent_scope == inbound.consent_scope

    belief = out.payload
    assert isinstance(belief, BeliefState)
    assert belief.user_id == USER
    assert len(belief.estimates) >= 1

    # Live axis estimate present and fresh-readable.
    meta = belief.get("meta_context", now=now)
    assert meta is not None and meta.value["category"] == "waking/focused"

    # OFFLINE axis recorded as a well-formed sentinel, not fabricated confidence.
    off = belief.estimates["sleep_stage"]
    assert off.confidence is None
    assert off.value["category"] == "offline"
    assert belief.get("sleep_stage", now=now) is None  # OFFLINE never fresh.

    # Envelope serializes cleanly (proves it is wire-ready).
    d = out.to_dict()
    assert d["trace_id"] == inbound.trace_id
    assert "meta_context" in d["payload"]["estimates"]


def test_default_registry_references_eight_live_axes():
    assert set(P.AXIS_REGISTRY) == {
        "meta_context", "sleep_stage", "audio_social_context", "cognitive_load",
        "visual_context", "arousal_inferred", "affect_prosody", "state_declared",
    }


def test_belief_state_persists_across_packets():
    now = datetime.now(timezone.utc)
    part = P.FusionParticipant(registry=_stub_registry(now))
    b1 = part.fuse(_packet(now), now=now)
    b2 = part.fuse(_packet(now), now=now)
    assert b1 is b2  # same per-user BeliefState reused, not rebuilt.


def _audio_feature_env(now: datetime) -> MessageEnvelope:
    snap = FeatureSnapshot(
        user_id=USER,
        timestamp=now,
        modality="audio",
        source="mic_listener_v1",
        payload={"kind": "audio_social_context",
                 "social_category": "with_other", "speaker": "both"},
        intent="continuous",
        confidence=0.8,
    )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.FEATURE,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=now,
        meta_context=MetaContext.WAKING,
        consent_scope="mic_continuous_v1",
        trace_id=str(uuid.uuid4()),
        payload=snap,
        i_model_id=None,
    )


def test_live_audio_packet_fuses_social_belief_no_db():
    """Full L3 arc with the DEFAULT registry and NO DB: fuse_from_feature wins,
    fuse_recent (DB) is never reached, so no get_conn / no monkeypatch needed."""
    now = datetime.now(timezone.utc)
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_BELIEF, captured.append)

    P.register(bus)  # real AXIS_REGISTRY incl. _audio_combiner

    bus.publish(TOPIC_FEATURE, _audio_feature_env(now))

    assert len(captured) == 1
    belief = captured[0].payload
    assert isinstance(belief, BeliefState)
    est = belief.get("audio_social_context", now=now)
    assert est is not None and est.value == {"category": "with_other"}
    # The DB-backed axes degrade to OFFLINE for an audio packet (expected).
    assert belief.get("meta_context", now=now) is None
    assert belief.get("sleep_stage", now=now) is None
    # cognitive_load (live-only, EEG-kind only) is OFFLINE for a non-EEG packet.
    assert belief.get("cognitive_load", now=now) is None


def _biometric_feature_env(now: datetime) -> MessageEnvelope:
    snap = FeatureSnapshot(
        user_id=USER,
        timestamp=now,
        modality="biometric",
        source="watch.hr_30s",
        payload={"kind": "biometric_window",
                 "features": {"hr_mean": 100, "hrv_mean": 25}},
        intent="continuous",
        confidence=0.8,
    )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.FEATURE,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=now,
        meta_context=MetaContext.SLEEP,
        consent_scope="apple_health_v1",
        trace_id=str(uuid.uuid4()),
        payload=snap,
        i_model_id=None,
    )


def test_live_biometric_packet_fuses_arousal_belief_no_db():
    """Full L3 arc with the DEFAULT registry and NO DB: a biometric_window packet
    fires arousal_inferred via fuse_from_feature; the belief envelope inherits the
    inbound SLEEP frame + apple_health_v1 consent, while the arousal estimate itself
    honestly tags meta_context=None (#14 deferral). All other axes go OFFLINE."""
    now = datetime.now(timezone.utc)
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_BELIEF, captured.append)

    P.register(bus)  # real AXIS_REGISTRY incl. _arousal_inferred_combiner

    inbound = _biometric_feature_env(now)
    bus.publish(TOPIC_FEATURE, inbound)

    assert len(captured) == 1
    out = captured[0]
    # Belief-envelope propagation: trace / frame / consent / role inherited.
    assert out.trace_id == inbound.trace_id
    assert out.meta_context == MetaContext.SLEEP
    assert out.consent_scope == "apple_health_v1"
    assert out.source_role == P.role_for("L3.fusion")

    belief = out.payload
    assert isinstance(belief, BeliefState)
    est = belief.get("arousal_inferred", now=now)
    assert est is not None
    assert "arousal" in est.value and "band" in est.value and "hr_mean" in est.value
    # The axis cannot tell SLEEP from WAKING from the packet alone (#14): None tag.
    assert est.meta_context is None

    # The same biometric packet leaves every other live axis OFFLINE.
    assert belief.get("affect_prosody", now=now) is None
    assert belief.get("visual_context", now=now) is None
    assert belief.get("cognitive_load", now=now) is None
    assert belief.get("audio_social_context", now=now) is None
