"""Tests for FeatureSnapshot envelope."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from features.snapshot import FeatureSnapshot


def test_basic_construction():
    snap = FeatureSnapshot(
        user_id="61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
        timestamp=datetime(2026, 5, 27, 15, 0, tzinfo=timezone.utc),
        modality="biometric",
        source="watch.hr_30s",
        payload={"hr_mean": 68.2, "hr_std": 3.1},
    )
    assert snap.modality == "biometric"
    assert snap.payload["hr_mean"] == pytest.approx(68.2)
    assert snap.confidence is None
    assert snap.meta_context_hint is None


def test_to_dict_roundtrip():
    snap = FeatureSnapshot(
        user_id="61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
        timestamp=datetime(2026, 5, 27, 15, 0, tzinfo=timezone.utc),
        modality="mac",
        source="mac.app_activity",
        payload={"active_app": "Cursor", "keystrokes_per_min": 42},
        confidence=0.9,
        meta_context_hint="waking",
    )
    d = snap.to_dict()
    assert d["modality"] == "mac"
    assert d["confidence"] == 0.9
    assert d["meta_context_hint"] == "waking"
    assert d["timestamp"].endswith("+00:00")  # tz-aware ISO


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="tz-aware"):
        FeatureSnapshot(
            user_id="61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
            timestamp=datetime(2026, 5, 27, 15, 0),  # naive — should raise
            modality="biometric",
            source="watch.hr_30s",
            payload={},
        )
