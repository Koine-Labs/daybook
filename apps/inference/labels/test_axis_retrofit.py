"""Each of the 7 live L3 axes' emitted `source` resolves to a valid tier (spec §6)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fusion.axes import (
    affect_prosody,
    arousal_inferred,
    audio_social_context,
    cognitive_load,
    visual_context,
)
from labels.provenance import LabelSource, classify_source

# Exact source strings the live axes stamp on their AxisEstimate. The five
# scaffold/derived axes expose a SOURCE constant; meta_context + sleep_stage
# hardcode their string in fuse_recent (read from the files).
META_CONTEXT_SOURCE = "L3.fusion.meta_context.v1_heuristic"
SLEEP_STAGE_SOURCE = "apple_health_sleep_stage"

LIVE_AXIS_SOURCES = {
    "meta_context": META_CONTEXT_SOURCE,
    "sleep_stage": SLEEP_STAGE_SOURCE,
    "audio_social_context": audio_social_context.SOURCE,
    "cognitive_load": cognitive_load.SOURCE,
    "visual_context": visual_context.SOURCE,
    "arousal_inferred": arousal_inferred.SOURCE,
    "affect_prosody": affect_prosody.SOURCE,
}

# arousal_inferred has literature grounding (HR/HRV); the rest are heuristic (§6).
EXPECTED_TIER = {
    "meta_context": LabelSource.HEURISTIC,
    "sleep_stage": LabelSource.HEURISTIC,
    "audio_social_context": LabelSource.HEURISTIC,
    "cognitive_load": LabelSource.HEURISTIC,
    "visual_context": LabelSource.HEURISTIC,
    "arousal_inferred": LabelSource.LITERATURE_PRIOR,
    "affect_prosody": LabelSource.HEURISTIC,
}


def test_all_seven_live_axes_present():
    assert len(LIVE_AXIS_SOURCES) == 7


@pytest.mark.parametrize("axis,source", sorted(LIVE_AXIS_SOURCES.items()))
def test_each_live_axis_source_resolves_to_a_valid_tier(axis, source):
    tier = classify_source(source)
    assert isinstance(tier, LabelSource)
    assert tier == EXPECTED_TIER[axis]


def test_audio_social_context_live_variant_resolves():
    # fuse_from_feature stamps SOURCE + ".live"; it must still resolve.
    assert classify_source(audio_social_context.SOURCE + ".live") is LabelSource.HEURISTIC
