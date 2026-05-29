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


def test_default_registry_references_three_live_axes():
    assert set(P.AXIS_REGISTRY) == {
        "meta_context", "sleep_stage", "audio_social_context"
    }


def test_belief_state_persists_across_packets():
    now = datetime.now(timezone.utc)
    part = P.FusionParticipant(registry=_stub_registry(now))
    b1 = part.fuse(_packet(now), now=now)
    b2 = part.fuse(_packet(now), now=now)
    assert b1 is b2  # same per-user BeliefState reused, not rebuilt.
