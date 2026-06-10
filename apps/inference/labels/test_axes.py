"""Tests for the canonical-axis join (#5)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels import DECLARED_TO_CANONICAL, canonical_axis


def test_arousal_maps_to_inferred_counterpart():
    assert canonical_axis("arousal") == "arousal_inferred"


def test_axes_without_inferred_counterpart_are_unchanged():
    # Conservative mapping: only arousal has a same-concept inferred axis today.
    for axis in ("fatigue", "focus", "valence", "stress", "mood"):
        assert canonical_axis(axis) == axis


def test_mapping_table_is_conservative():
    assert DECLARED_TO_CANONICAL == {"arousal": "arousal_inferred"}
