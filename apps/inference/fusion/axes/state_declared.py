"""L3 axis: state_declared — explicit self-report claims -> a high-confidence belief.

Unlike the inferred scaffolds (cognitive_load / arousal_inferred / affect_prosody,
all scaffold=True), an explicit self-report is HONEST ground truth, not a heuristic
guess: source=LabelSource.SELF_REPORT, scaffold=False (commitment #17 / spec §5 D3).
The value carries the structured claims the declaration speaks to; the per-claim
LabelRecords are written by the arc's belief-subscriber (state/declare.py), keeping
this axis pure and DB-free.

state_declared is a WAKING phenomenon (#14) and tags meta_context="waking" by
construction. Live-only: declarations ride the bus, there is no sensor-table
fallback. Pure, DB-free.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from ..belief_state import AxisEstimate

INF_DIR = Path(__file__).resolve().parent.parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelSource  # noqa: E402

AXIS = "state_declared"
SOURCE = LabelSource.SELF_REPORT.value
KIND = "state_declaration"
FRESH_SECONDS = 600  # a self-report stays meaningful for a while (longer than fast bio axes)


def fuse_from_feature(packet, *, now: datetime | None = None) -> AxisEstimate | None:
    """Build a state_declared estimate from an L2 declaration FeatureSnapshot, else None.

    Only fires for our own kind (state_declaration); other kinds/modalities return
    None so the participant records state_declared as OFFLINE. No DB.
    """
    feats = getattr(packet, "payload", {}) or {}
    if feats.get("kind") != KIND:
        return None
    derived = feats.get("features", {}) or {}
    if not derived.get("claims"):  # empty/garbled declaration -> OFFLINE, not a hollow belief
        return None
    value = {
        "claims": derived.get("claims", []),
        "raw_text": derived.get("raw_text", ""),
        "classifier": derived.get("classifier"),
        "scaffold": False,  # explicit self-report is ground truth, not a heuristic scaffold
    }
    return AxisEstimate(
        axis=AXIS,
        value=value,
        timestamp=getattr(packet, "timestamp", None) or now or datetime.now(timezone.utc),
        confidence=0.9,                              # high — an explicit self-report (#17 D3)
        source=SOURCE,
        meta_context="waking",                       # by-construction tag (#14)
        fresh_for_seconds=FRESH_SECONDS,
        i_model_id=getattr(packet, "i_model_id", None),  # carry-through (#1); None until clustering
    )
