"""L2 audio extractor — audio SignalPacket -> FeatureSnapshot.

Registered for Modality.AUDIO in features/participant. Consumes the privacy-gated
semantic packets the mic producer emits (kinds: audio_social_context / audio_prosody
/ audio_ambient) and shapes a FeatureSnapshot L3's audio_social_context axis can fuse
live. Semantic-first (#11): inputs are already derived values, never raw audio.
"""
from __future__ import annotations

from core.protocol.enums import Intent
from core.protocol.payloads import SignalPacket
from features.snapshot import FeatureSnapshot

EXTRACTOR_TAG = "audio_social.v1"
_INTENT_VALUES = {i.value for i in Intent}
_DEFAULT_INTENT = Intent.CONTINUOUS.value


def social_category(speaker: str) -> str:
    """speaker -> coarse social category (single source of truth for the map)."""
    return "with_other" if speaker in ("other", "both") else "alone"


def extract(sig: SignalPacket) -> FeatureSnapshot:
    """Audio SignalPacket -> FeatureSnapshot, shaped per semantic kind."""
    p = dict(sig.payload)
    features: dict = {"kind": sig.kind, "extractor": EXTRACTOR_TAG}

    if sig.kind == "audio_social_context":
        speaker = p.get("speaker", "none")
        features.update({
            "speaker": speaker,
            "social_category": social_category(speaker),
            "num_speakers": p.get("num_speakers", 0),
            "vad_active": bool(p.get("vad_active", False)),
        })
    elif sig.kind == "audio_prosody":
        features["prosody"] = p
    elif sig.kind == "audio_ambient":
        features["ambient"] = p.get("top_classes", [])
    else:
        features["features"] = p  # unknown audio kind: passthrough, honest

    return FeatureSnapshot(
        user_id=sig.user_id,
        timestamp=sig.timestamp,
        modality=sig.modality,
        source=sig.source,
        payload=features,
        intent=sig.intent if sig.intent in _INTENT_VALUES else _DEFAULT_INTENT,
        confidence=sig.confidence,
        i_model_id=sig.i_model_id,
    )
