"""L2 vision extractor — SignalPacket[vision] -> FeatureSnapshot. No DB, no network.

Feeds synthetic visual_scene SignalPackets (built from synthesize_vision_frame)
and asserts the structured payload, derived features, and registry wiring.
Mirrors features/test_bci.py's structured payload + EXTRACTOR_TAG.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.protocol.payloads import SignalPacket
from features import participant as P
from features import vision_scene as vs
from features.snapshot import FeatureSnapshot
from sensors.vision_adapter import synthesize_vision_frame

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _packet(semantics: dict, *, kind: str = "visual_scene") -> SignalPacket:
    return SignalPacket(
        user_id=USER,
        timestamp=datetime.now(timezone.utc),
        modality="vision",
        intent="continuous",
        kind=kind,
        payload=semantics,
        source="camera.visual_scene",
    )


def test_registry_wires_vision_to_real_extractor():
    assert P.select_extractor("vision") is vs.extract


def test_extract_produces_structured_snapshot():
    snap = vs.extract(_packet(synthesize_vision_frame(index=1)))
    assert isinstance(snap, FeatureSnapshot)
    assert snap.modality == "vision"
    p = snap.payload
    assert p["kind"] == "visual_scene"
    assert p["extractor"] == vs.EXTRACTOR_TAG
    assert set(p["semantics"]) == {"setting", "people_present", "salient_objects", "text_present", "model"}
    feats = p["features"]
    assert set(feats) == {"people_present", "crowd_size", "setting", "has_text", "object_count"}


def test_compute_derived_maps_people_and_crowd():
    none = vs.compute_derived({"people_present": 0, "salient_objects": []})
    assert none["people_present"] is False
    assert none["crowd_size"] == "none"
    assert none["object_count"] == 0

    one = vs.compute_derived({"people_present": 1, "salient_objects": ["person"]})
    assert one["people_present"] is True
    assert one["crowd_size"] == "one"

    few = vs.compute_derived({"people_present": 3, "salient_objects": ["person", "chair"]})
    assert few["crowd_size"] == "few"
    assert few["object_count"] == 2

    many = vs.compute_derived({"people_present": 9, "salient_objects": []})
    assert many["crowd_size"] == "many"


def test_compute_derived_setting_passthrough_and_has_text():
    d = vs.compute_derived({"setting": "outdoor", "text_present": True, "people_present": 0})
    assert d["setting"] == "outdoor"
    assert d["has_text"] is True


def test_compute_derived_missing_fields_no_crash():
    d = vs.compute_derived({})
    assert d["people_present"] is False
    assert d["crowd_size"] == "none"
    assert d["setting"] == "unknown"
    assert d["has_text"] is False
    assert d["object_count"] == 0


def test_extract_preserves_i_model_id():
    imid = "22222222-2222-2222-2222-222222222222"
    sig = _packet(synthesize_vision_frame(index=0))
    sig.i_model_id = imid
    snap = vs.extract(sig)
    assert snap.i_model_id == imid
