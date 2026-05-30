"""L3 fusion bus-participant — FeaturePacket in, BeliefState out.

Subscribes TOPIC_FEATURE, drives the registered axis combiners against the
inbound packet's user, updates a per-user BeliefState (reusing belief_state.py),
and publishes the result on TOPIC_BELIEF via core/layer.py's forward_envelope so
trace_id / meta_context / consent_scope / i_model_id are inherited.

NodeRole: DESKTOP_COMPUTE (per core/nodes.py "L3.fusion").
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from core.bus.bus import TOPIC_BELIEF, TOPIC_FEATURE, MessageBus  # noqa: E402
from core.layer import forward_envelope  # noqa: E402
from core.nodes import role_for  # noqa: E402
from core.protocol.enums import PayloadType  # noqa: E402
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import FeatureSnapshot  # noqa: E402

from .axes import (  # noqa: E402
    affect_prosody,
    arousal_inferred,
    audio_social_context,
    cognitive_load,
    meta_context,
    sleep_stage,
    state_declared,
    visual_context,
)
from .belief_state import AxisEstimate, BeliefState  # noqa: E402

# An axis combiner takes the inbound packet + a determinism `now` and returns
# its current best AxisEstimate, or None when it has no fresh answer (OFFLINE).
AxisCombiner = Callable[[FeatureSnapshot, datetime], "AxisEstimate | None"]

OFFLINE_CONFIDENCE = None  # never fabricate confidence for an OFFLINE estimate.


def _offline_estimate(axis: str, *, now: datetime, reason: str) -> AxisEstimate:
    """The L3 degraded sentinel: a well-formed 'no answer' for one axis."""
    return AxisEstimate(
        axis=axis,
        value={"category": "offline", "reason": reason},
        timestamp=now,
        confidence=OFFLINE_CONFIDENCE,
        source=f"L3.fusion.{axis}.offline",
        meta_context=None,
        fresh_for_seconds=-1,  # OFFLINE is never fresh: any elapsed time fails <= -1.
    )


def _wrap_fuse_recent(
    axis: str, fuse_recent: Callable[..., "AxisEstimate | None"]
) -> AxisCombiner:
    """Adapt an axis module's DB-backed fuse_recent into a crash-safe combiner.

    Axes read sensor_readings, not the single FeaturePacket, so the packet only
    supplies user_id + now. Any DB/inputs gap yields an OFFLINE estimate rather
    than a crash, per the skeleton contract.
    """

    def combiner(packet: FeatureSnapshot, now: datetime) -> AxisEstimate | None:
        try:
            return fuse_recent(user_id=packet.user_id, now=now)
        except Exception as exc:  # noqa: BLE001 — skeleton must never crash the bus.
            return _offline_estimate(axis, now=now, reason=f"axis error: {exc!r}")

    return combiner


def _audio_combiner(packet: FeatureSnapshot, now: datetime) -> "AxisEstimate | None":
    """Live-first audio_social_context: fuse the inbound packet, else DB-fallback.

    When an audio_social_context FeatureSnapshot rides the bus, fuse it live with
    zero DB access; for any other inbound packet, fuse_from_feature returns None
    and the existing DB fuse_recent runs exactly as before. Same crash-safety
    contract as _wrap_fuse_recent: any error degrades to OFFLINE, never crashes.
    """
    try:
        live = audio_social_context.fuse_from_feature(packet, now=now)
        if live is not None:
            return live
        return audio_social_context.fuse_recent(user_id=packet.user_id, now=now)
    except Exception as exc:  # noqa: BLE001 — skeleton must never crash the bus.
        return _offline_estimate("audio_social_context", now=now, reason=f"axis error: {exc!r}")


def _cognitive_load_combiner(packet: FeatureSnapshot, now: datetime) -> "AxisEstimate | None":
    """Live-only cognitive_load: fuse the inbound BCI packet; None -> OFFLINE upstream.

    No DB fallback (there is no eeg_bandpower sensor table yet — see the axis
    docstring). For a non-EEG packet, fuse_from_feature returns None and the
    participant records cognitive_load as OFFLINE, exactly how meta_context /
    sleep_stage degrade for an audio packet. Any error degrades to OFFLINE, never
    crashes the bus.
    """
    try:
        return cognitive_load.fuse_from_feature(packet, now=now)
    except Exception as exc:  # noqa: BLE001 — skeleton must never crash the bus.
        return _offline_estimate("cognitive_load", now=now, reason=f"axis error: {exc!r}")


def _visual_combiner(packet: FeatureSnapshot, now: datetime) -> "AxisEstimate | None":
    """Live-only visual_context: fuse the inbound vision packet; None -> OFFLINE upstream.

    No DB fallback (there is no visual_scene sensor table yet — see the axis
    docstring). For a non-vision packet, fuse_from_feature returns None and the
    participant records visual_context as OFFLINE, exactly how cognitive_load
    degrades for a non-EEG packet. Any error degrades to OFFLINE, never crashes
    the bus.
    """
    try:
        return visual_context.fuse_from_feature(packet, now=now)
    except Exception as exc:  # noqa: BLE001 — skeleton must never crash the bus.
        return _offline_estimate("visual_context", now=now, reason=f"axis error: {exc!r}")


def _arousal_inferred_combiner(packet: FeatureSnapshot, now: datetime) -> "AxisEstimate | None":
    """Live-only arousal_inferred: fuse the inbound biometric packet; None -> OFFLINE upstream.

    No DB fallback (there is no biometric-window-as-axis sensor table yet — see the
    axis docstring). For a non-biometric packet, fuse_from_feature returns None and
    the participant records arousal_inferred as OFFLINE, exactly how cognitive_load
    degrades for a non-EEG packet. Any error degrades to OFFLINE, never crashes the
    bus.
    """
    try:
        return arousal_inferred.fuse_from_feature(packet, now=now)
    except Exception as exc:  # noqa: BLE001 — skeleton must never crash the bus.
        return _offline_estimate("arousal_inferred", now=now, reason=f"axis error: {exc!r}")


def _affect_prosody_combiner(packet: FeatureSnapshot, now: datetime) -> "AxisEstimate | None":
    """Live-only affect_prosody: fuse the inbound prosody packet; None -> OFFLINE upstream.

    No DB fallback (there is no audio_prosody sensor table yet — see the axis
    docstring). For a non-prosody packet, fuse_from_feature returns None and the
    participant records affect_prosody as OFFLINE, exactly how cognitive_load
    degrades for a non-EEG packet. Any error degrades to OFFLINE, never crashes the
    bus.
    """
    try:
        return affect_prosody.fuse_from_feature(packet, now=now)
    except Exception as exc:  # noqa: BLE001 — skeleton must never crash the bus.
        return _offline_estimate("affect_prosody", now=now, reason=f"axis error: {exc!r}")


def _state_declared_combiner(packet: FeatureSnapshot, now: datetime) -> "AxisEstimate | None":
    """Live-only state_declared: fuse the inbound declaration packet; None -> OFFLINE upstream.

    No DB fallback (declarations ride the bus, there is no sensor table). For a
    non-declaration packet, fuse_from_feature returns None and the participant
    records state_declared as OFFLINE, exactly how cognitive_load degrades for a
    non-EEG packet. Any error degrades to OFFLINE, never crashes the bus.
    """
    try:
        return state_declared.fuse_from_feature(packet, now=now)
    except Exception as exc:  # noqa: BLE001 — skeleton must never crash the bus.
        return _offline_estimate("state_declared", now=now, reason=f"axis error: {exc!r}")


# Registry of the live axes. Selection is content-agnostic: every registered axis
# is asked on each FeaturePacket; each returns its estimate or None (which the
# participant records as OFFLINE).
AXIS_REGISTRY: dict[str, AxisCombiner] = {
    "meta_context": _wrap_fuse_recent("meta_context", meta_context.fuse_recent),
    "sleep_stage": _wrap_fuse_recent("sleep_stage", sleep_stage.fuse_recent),
    "audio_social_context": _audio_combiner,
    "cognitive_load": _cognitive_load_combiner,
    "visual_context": _visual_combiner,
    arousal_inferred.AXIS: _arousal_inferred_combiner,
    affect_prosody.AXIS: _affect_prosody_combiner,
    state_declared.AXIS: _state_declared_combiner,
}


class FusionParticipant:
    """L3 organ: fuses inbound FeaturePackets into a per-user BeliefState."""

    registry: dict[str, AxisCombiner]
    _beliefs: dict[str, BeliefState]

    def __init__(self, registry: dict[str, AxisCombiner] | None = None) -> None:
        self.registry = registry if registry is not None else dict(AXIS_REGISTRY)
        self._beliefs = {}

    def belief_for(self, user_id: str) -> BeliefState:
        """Return (creating if needed) the persistent BeliefState for a user."""
        return self._beliefs.setdefault(user_id, BeliefState(user_id=user_id))

    def fuse(self, packet: FeatureSnapshot, *, now: datetime | None = None) -> BeliefState:
        """Run every registered axis against the packet, updating the BeliefState.

        Each axis contributes its estimate, or an OFFLINE sentinel when it has no
        fresh answer — so the returned BeliefState always carries one estimate
        per registered axis.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        belief = self.belief_for(packet.user_id)
        for axis, combiner in self.registry.items():
            est = combiner(packet, now)
            if est is None:
                est = _offline_estimate(axis, now=now, reason="no fresh data")
            belief.update(est)
        return belief

    def handle(self, inbound: MessageEnvelope, bus: MessageBus) -> None:
        """Bus handler: FeaturePacket envelope in → BeliefState envelope out."""
        packet = inbound.payload
        if not isinstance(packet, FeatureSnapshot):
            return  # not our payload; ignore rather than crash.
        belief = self.fuse(packet)
        outbound = forward_envelope(
            inbound,
            ptype=PayloadType.BELIEF,
            payload=belief,
            source_role=role_for("L3.fusion"),
        )
        bus.publish(TOPIC_BELIEF, outbound)


def register(bus: MessageBus, *, participant: FusionParticipant | None = None) -> FusionParticipant:
    """Subscribe an L3 FusionParticipant to TOPIC_FEATURE; return it for inspection."""
    part = participant or FusionParticipant()
    bus.subscribe(TOPIC_FEATURE, lambda env: part.handle(env, bus))
    return part
