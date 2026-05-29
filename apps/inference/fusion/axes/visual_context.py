"""L3 axis: visual_context — visual_scene derived features -> a scene-context estimate.

v1 heuristic scaffold (a direct mapping from the semantic scene dict to a coarse
{setting, people_present, category} context). NOT a trained scene classifier.
This axis exists to generate the data flywheel toward the JEPA-era latent world
model (commitment #16); it is a stand-alone per-axis scaffold per ARCHITECTURE
§2.16's v1 plan, designed to compose forward, not be thrown away.

visual_context is a WAKING sub-context signal (#14). Live-only: there is no
visual_scene sensor-table persistence path yet, so there is intentionally NO DB
fuse_recent fallback (a documented follow-on for when scenes are persisted to
sensor_readings). Pure, DB-free.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..belief_state import AxisEstimate

AXIS = "visual_context"
SOURCE = "L3.fusion.visual_context.v1_heuristic"
FRESH_SECONDS = 120  # scene context shifts fast; matches cognitive_load / meta_context's 120s.

KIND_VISUAL_SCENE = "visual_scene"


def _category(people_present: bool) -> str:
    """Coarse social category from the people-present flag (honest v1; #16 input)."""
    return "with_people" if people_present else "alone"


def fuse_from_feature(packet, *, now: datetime | None = None) -> AxisEstimate | None:
    """Build a live visual_context estimate from an L2 vision FeatureSnapshot, else None.

    Only fires for our own kind (visual_scene); other kinds/modalities return None
    so the participant records visual_context as OFFLINE. No DB.

    This axis does NOT itself gate on the active meta-context — it fires for any
    visual_scene frame. #14's channel gating (e.g. no scene inference downstream
    during deep sleep) is deferred to a later layer (L5/L6), not enforced here.
    """
    feats = getattr(packet, "payload", {}) or {}
    if feats.get("kind") != KIND_VISUAL_SCENE:
        return None
    semantics = feats.get("semantics", {}) or {}
    derived = feats.get("features", {}) or {}
    people_present = bool(derived.get("people_present"))
    return AxisEstimate(
        axis=AXIS,
        value={
            "setting": semantics.get("setting", "unknown"),
            "people_present": people_present,
            "salient_objects": list(semantics.get("salient_objects") or []),
            "category": _category(people_present),    # "alone" | "with_people"
            "method": "scene_mapping_v1",
            "scaffold": True,                          # explicit: not a trained model
        },
        timestamp=getattr(packet, "timestamp", None) or now or datetime.now(timezone.utc),
        confidence=0.5,                                # moderate — honest for an unfitted mapping
        source=SOURCE,
        meta_context="waking",                         # visual_context is a WAKING sub-context (#14)
        fresh_for_seconds=FRESH_SECONDS,
    )
