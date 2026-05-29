"""L2 vision feature extractor — visual_scene SignalPacket -> FeatureSnapshot.

Registered for Modality.VISION in features/participant (replacing the passthrough
stub). Mirrors features/bci.py: a structured payload + EXTRACTOR_TAG over a
semantic packet whose raw pixels were already discarded at the edge (#11). The
scene dict ({setting, people_present, salient_objects, text_present, model}) is
already semantic at L1, so L2 derives the higher-order, L3-consumable features
(crowd_size band, people_present bool, object_count).

`compute_derived` is the single source of truth for those derived features (the
analog of bci.compute_derived) and is what the L3 visual_context axis reads — the
axis does NOT re-derive from the raw scene dict.
"""
from __future__ import annotations

from typing import Any

from core.protocol.enums import Intent
from core.protocol.payloads import SignalPacket
from features.snapshot import FeatureSnapshot

EXTRACTOR_TAG = "vision_scene_features.v1"
_INTENT_VALUES = {i.value for i in Intent}
_DEFAULT_INTENT = Intent.CONTINUOUS.value


def _crowd_size(people_present: int) -> str:
    """Band the person count into a coarse crowd label (honest v1; #16 flywheel)."""
    if people_present <= 0:
        return "none"
    if people_present == 1:
        return "one"
    if people_present <= 4:
        return "few"
    return "many"


def compute_derived(semantics: dict[str, Any]) -> dict[str, Any]:
    """Derive the L3-consumable features from a visual_scene semantic dict.

    `setting` passes through unchanged (already semantic at L1); the rest are
    higher-order bands/booleans/counts the axis consumes without re-deriving.
    """
    people_present = int(semantics.get("people_present") or 0)
    salient_objects = semantics.get("salient_objects") or []
    return {
        "people_present": people_present > 0,        # bool: any person detected
        "crowd_size": _crowd_size(people_present),    # "none"|"one"|"few"|"many"
        "setting": semantics.get("setting", "unknown"),  # passthrough (already semantic)
        "has_text": bool(semantics.get("text_present")),  # OCR found text
        "object_count": len(salient_objects),         # number of salient classes
    }


def extract(sig: SignalPacket) -> FeatureSnapshot:
    """visual_scene SignalPacket -> FeatureSnapshot with the scene + derived features."""
    semantics = dict(sig.payload)
    derived = compute_derived(semantics)
    return FeatureSnapshot(
        user_id=sig.user_id,
        timestamp=sig.timestamp,
        modality=sig.modality,
        source=sig.source,
        payload={
            "kind": sig.kind,
            "extractor": EXTRACTOR_TAG,
            "semantics": semantics,
            "features": derived,
        },
        intent=sig.intent if sig.intent in _INTENT_VALUES else _DEFAULT_INTENT,
        confidence=sig.confidence,
        i_model_id=sig.i_model_id,
    )
