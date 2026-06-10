"""L2 declaration extractor — state_declaration SignalPacket -> FeatureSnapshot.

Registered for Modality.TEXT in features/participant (replacing the passthrough
stub for 'text'). GUARDED on kind=='state_declaration': any other text packet
falls through to the original passthrough behaviour, so the registry change is
behaviour-preserving for non-declaration text.

Maps free text -> structured axis claims. Primary path is the LLM
(ChatClient.chat_structured into DeclaredState); a deterministic offline lexicon
keeps CI DB-free and LLM-free (DAYBOOK_DECLARE_OFFLINE=1, or whenever LLM auth is
unavailable). The chosen path is recorded HONESTLY as classifier="llm"|"quickpick"
in the snapshot (commitment #17 / spec §5, honesty over theater).
"""
from __future__ import annotations

import math
import os
from typing import Any

from pydantic import BaseModel, Field

from core.protocol.payloads import SignalPacket
from features.snapshot import FeatureSnapshot

KIND = "state_declaration"
EXTRACTOR_TAG = "declaration_claims.v1"

_SYSTEM = (
    "You read a short first-person statement about how someone feels right now and "
    "extract structured state claims. Each claim names an axis (one of: fatigue, "
    "arousal, valence, cognitive_load, stress), a value in 0..1, and a confidence "
    "in 0..1. Only emit claims the statement actually supports. Be conservative."
)


class Claim(BaseModel):
    """One declared axis value (scalar in 0..1, or a categorical string) (spec D5)."""

    axis: str
    value: float | str
    confidence: float = Field(ge=0.0, le=1.0)


class DeclaredState(BaseModel):
    """Structured parse of a state declaration."""

    claims: list[Claim]
    note: str = ""


# Deterministic offline lexicon: phrase substring -> [(axis, value, confidence)].
# value is a scalar in 0..1 OR a categorical string. First match per axis wins,
# so output is order-stable for a given input.
_LEXICON: tuple[tuple[str, tuple[tuple[str, float | str, float], ...]], ...] = (
    ("locked in", (("cognitive_load", 0.85, 0.8), ("arousal", 0.7, 0.7))),
    ("focused", (("cognitive_load", 0.8, 0.75),)),
    ("exhausted", (("fatigue", 0.9, 0.85),)),
    ("wiped", (("fatigue", 0.85, 0.8),)),
    ("drained", (("fatigue", 0.85, 0.8),)),
    ("tired", (("fatigue", 0.75, 0.75),)),
    ("beat", (("fatigue", 0.8, 0.75),)),
    ("wired", (("arousal", 0.8, 0.75),)),
    ("anxious", (("arousal", 0.8, 0.75), ("valence", 0.25, 0.7))),
    ("stressed", (("stress", 0.8, 0.75),)),
    ("calm", (("arousal", 0.2, 0.75), ("valence", 0.7, 0.7))),
    ("relaxed", (("arousal", 0.2, 0.75),)),
    ("happy", (("valence", 0.85, 0.8),)),
    ("good", (("valence", 0.7, 0.6),)),
    ("sad", (("valence", 0.2, 0.75),)),
    ("down", (("valence", 0.25, 0.7),)),
    # categorical claim: a sleepiness phrase maps to a string value, proving the
    # float|str round-trip end to end (spec D5).
    ("sleepy", (("sleepiness", "drowsy", 0.8),)),
)


def _quickpick_claims(text: str) -> list[dict[str, Any]]:
    """Deterministic lexicon -> axis claims, one per axis (first match wins)."""
    lowered = text.lower()
    by_axis: dict[str, dict[str, Any]] = {}
    for phrase, claims in _LEXICON:
        if phrase in lowered:
            for axis, value, confidence in claims:
                by_axis.setdefault(axis, {"axis": axis, "value": value, "confidence": confidence})
    return list(by_axis.values())


def _get_client():
    """Return a signed-in ChatClient, or None when the LLM path is unusable."""
    try:
        from llm import ChatClient

        client = ChatClient.auto()
        if getattr(client, "backend", None) != "codex":
            return None
        return client
    except Exception:
        return None


def _llm_claims(text: str) -> list[dict[str, Any]] | None:
    """LLM-structured claim extraction; None if the LLM path is unavailable."""
    client = _get_client()
    if client is None:
        return None
    try:
        result = client.chat_structured(system=_SYSTEM, user=text, schema=DeclaredState)
    except Exception:
        return None
    out: list[dict[str, Any]] = []
    for c in result.claims:
        conf = float(c.confidence)
        if not math.isfinite(conf):
            continue  # garbage confidence -> drop the claim entirely.
        conf = min(1.0, max(0.0, conf))  # clamp into [0,1].
        if isinstance(c.value, str):
            out.append({"axis": c.axis, "value": c.value, "confidence": conf})
            continue
        val = float(c.value)
        if not math.isfinite(val):
            continue  # NaN/inf scalar -> drop the claim.
        val = min(1.0, max(0.0, val))  # clamp scalar (e.g. value=85) into [0,1].
        out.append({"axis": c.axis, "value": val, "confidence": conf})
    return out


def extract(sig: SignalPacket) -> FeatureSnapshot:
    """state_declaration SignalPacket -> FeatureSnapshot of axis claims.

    Guarded: non-declaration text packets get a passthrough snapshot (the previous
    'text' extractor behaviour) so registering this on Modality.TEXT is safe.
    """
    if sig.kind != KIND:
        return _passthrough(sig)

    text = str(sig.payload.get("text", ""))
    offline = os.environ.get("DAYBOOK_DECLARE_OFFLINE") == "1"
    claims: list[dict[str, Any]] | None = None
    classifier = "quickpick"
    if not offline:
        claims = _llm_claims(text)
        if claims is not None:
            classifier = "llm"
    if claims is None:
        claims = _quickpick_claims(text)
        classifier = "quickpick"

    return FeatureSnapshot(
        user_id=sig.user_id,
        timestamp=sig.timestamp,
        modality=sig.modality,
        source=sig.source,
        payload={
            "kind": KIND,
            "extractor": EXTRACTOR_TAG,
            "features": {"claims": claims, "raw_text": text, "classifier": classifier},
        },
        intent=sig.intent if sig.intent in ("explicit", "continuous") else "explicit",
        confidence=sig.confidence,
        i_model_id=sig.i_model_id,
    )


def _passthrough(sig: SignalPacket) -> FeatureSnapshot:
    """Non-declaration text: wrap the signal payload as features, no transform."""
    return FeatureSnapshot(
        user_id=sig.user_id,
        timestamp=sig.timestamp,
        modality=sig.modality,
        source=sig.source,
        payload={"kind": sig.kind, "features": dict(sig.payload), "extractor": "stub_passthrough"},
        intent=sig.intent if sig.intent in ("explicit", "continuous") else "continuous",
        confidence=sig.confidence,
        i_model_id=sig.i_model_id,
    )
