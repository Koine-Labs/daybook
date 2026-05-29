"""L1 vision producer: semantic visual_scene packets -> SignalPacket on the bus.

Mirrors sensors/eeg_adapter.py. Transport-agnostic: holds only a MessageBus, so
the SAME class works over InProcessTransport (synthetic on the Mac today) and
NetworkTransport (camera satellite later) with no change. Semantic-first (#11):
the edge runs a detector over a frame and DISCARDS the raw pixels — only the
semantic scene dict ({setting, people_present, salient_objects, text_present,
model}) ever becomes a payload. Raw image bytes never ride the bus; emit_scene
asserts this invariant before publishing.

`synthesize_vision_frame` is the deterministic CI/demo generator — a semantic
dict varying by an integer index, never random (mirrors synthesize_eeg_window).
There are no raw pixels anywhere in CI: the synthetic frame is already semantic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.bus.bus import MessageBus
from core.protocol.enums import Intent, MetaContext, Modality
from core.protocol.envelope import MessageEnvelope
from sensors.contract import DEFAULT_USER_ID, IntentTaggedReading
from sensors.participant import emit
from vision.perception import KIND_VISUAL_SCENE, SETTINGS, VISION_SOURCE

# The exact key set of a visual_scene payload (the frozen #11 invariant Stage 2
# builds against). emit_scene projects onto these keys so no raw-pixel key — even
# if an upstream caller leaks one — can ride the bus.
SCENE_KEYS: tuple[str, ...] = ("setting", "people_present", "salient_objects", "text_present", "model")

# Deterministic synthetic vocabulary (no model, no random) for CI + demo.
_SYNTH_SETTINGS: tuple[str, ...] = ("outdoor", "indoor", "transit", "screen")
_SYNTH_OBJECTS: tuple[str, ...] = ("person", "laptop", "car", "cup", "chair", "tv", "bicycle", "book")


def synthesize_vision_frame(index: int = 0) -> dict[str, Any]:
    """Deterministic synthetic visual_scene dict (no model, no random) for CI + demo.

    Mirrors sensors.eeg_adapter.synthesize_eeg_window: varies by an integer
    `index`, never random. Carries ONLY semantic keys (no pixels, #11); `model` is
    stamped "synthetic" so provenance is unambiguous.
    """
    setting = _SYNTH_SETTINGS[index % len(_SYNTH_SETTINGS)]
    people = index % 4
    n_objects = 1 + (index % 3)
    salient = [_SYNTH_OBJECTS[(index + k) % len(_SYNTH_OBJECTS)] for k in range(n_objects)]
    return {
        "setting": setting,
        "people_present": people,
        "salient_objects": salient,
        "text_present": bool(index % 2),
        "model": "synthetic",
    }


def _semantic_only(semantics: dict[str, Any]) -> dict[str, Any]:
    """Project onto the frozen scene keys so no raw-pixel bytes can ride the bus (#11)."""
    payload: dict[str, Any] = {}
    for key in SCENE_KEYS:
        if key not in semantics:
            raise ValueError(f"visual_scene semantics missing required key {key!r}")
        payload[key] = semantics[key]
    if any(isinstance(v, (bytes, bytearray)) for v in payload.values()):
        raise ValueError("visual_scene payload must not carry raw bytes (semantic-first, #11)")
    if payload["setting"] not in SETTINGS:
        raise ValueError(f"unknown setting {payload['setting']!r}; expected one of {SETTINGS}")
    return payload


def _to_utc(ts: datetime) -> datetime:
    """Coerce to tz-aware UTC; reject naive timestamps."""
    if ts.tzinfo is None:
        raise ValueError("visual_scene timestamp must be tz-aware UTC")
    return ts.astimezone(timezone.utc)


class VisionBusSink:
    """Emits visual_scene SignalPackets onto a MessageBus. Raw pixels never ride the bus.

    `meta_context` is the top-level context (#14) the emitted signals ride under;
    it defaults to UNKNOWN so callers/tests are unchanged. The waking runner passes
    WAKING so visual_context (a WAKING sub-context signal) lands in a waking frame.
    """

    def __init__(
        self,
        bus: MessageBus,
        *,
        user_id: str = DEFAULT_USER_ID,
        meta_context: MetaContext = MetaContext.UNKNOWN,
    ) -> None:
        self.bus = bus
        self.user_id = user_id
        self.meta_context = meta_context

    def emit_scene(
        self,
        semantics: dict[str, Any],
        *,
        timestamp: datetime,
        user_id: str | None = None,
        i_model_id: str | None = None,
    ) -> MessageEnvelope:
        """Wrap a visual_scene semantic dict in a SignalPacket and emit it.

        Projects `semantics` onto the frozen scene keys and asserts no raw-pixel
        bytes ride the payload (#11) before publishing. Returns the published
        envelope.
        """
        payload = _semantic_only(semantics)
        reading = IntentTaggedReading(
            modality=Modality.VISION.value,
            intent=Intent.CONTINUOUS.value,
            kind=KIND_VISUAL_SCENE,
            payload=payload,
            source=VISION_SOURCE,
            timestamp=_to_utc(timestamp),
            user_id=user_id or self.user_id,
            i_model_id=i_model_id,
        )
        return emit(self.bus, reading, meta_context=self.meta_context)
