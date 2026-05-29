"""CI-safe contract tests for the vision edge — no model, no DB, no network.

The real detector (`extract_semantics`) needs the off-CI `[vision]` model, so CI
proves only the schema, constants, and import-cleanliness — exactly as the BCI
lane proves band-power plumbing on synthetic EEG. The end-to-end bus plumbing is
exercised in sensors/test_vision_adapter.py against synthetic semantics.
"""
from __future__ import annotations

import importlib

from vision.perception import (
    KIND_VISUAL_SCENE,
    SETTINGS,
    VISION_SOURCE,
    extract_semantics,
)

_SCENE_KEYS = {"setting", "people_present", "salient_objects", "text_present", "model"}


def test_constants_are_frozen_for_downstream_stages():
    assert KIND_VISUAL_SCENE == "visual_scene"
    assert VISION_SOURCE == "camera.visual_scene"
    assert set(SETTINGS) == {"outdoor", "indoor", "transit", "screen", "unknown"}


def test_perception_imports_clean_without_vision_model():
    importlib.import_module("vision.perception")


def test_extract_semantics_is_callable_lazy_seam():
    assert callable(extract_semantics)


def test_synthetic_frame_matches_the_frozen_scene_schema():
    from sensors.vision_adapter import synthesize_vision_frame

    s = synthesize_vision_frame(index=0)
    assert set(s) == _SCENE_KEYS
    assert s["setting"] in SETTINGS
