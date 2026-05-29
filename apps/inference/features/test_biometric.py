# apps/inference/features/test_biometric.py
"""Unit test for the L2 biometric feature extractor.

Feeds a representative biometric window through the extractor and asserts the
FeatureSnapshot payload carries all 24 model feature_cols with finite values,
and that the extractor is wired into the participant registry for
Modality.BIOMETRIC. Run:

    cd apps/inference && source .venv/bin/activate && python -m features.test_biometric
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from core.protocol.enums import Modality
from core.protocol.payloads import SignalPacket
from features.biometric import (
    CONTEXT_SECONDS,
    EPOCH_SECONDS,
    FEATURE_COLS,
    EXTRACTOR_TAG,
    extract,
)
from features.participant import EXTRACTORS, select_extractor
from features.snapshot import FeatureSnapshot

USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _synthetic_window() -> dict[str, Any]:
    """A representative 300s-context + 30s-epoch biometric window for all 4 kinds."""
    t0 = datetime(2026, 5, 28, 3, 0, 0, tzinfo=timezone.utc)
    epoch_start = t0 + timedelta(seconds=CONTEXT_SECONDS)
    rng = np.random.default_rng(7)
    readings: list[dict[str, Any]] = []
    span = CONTEXT_SECONDS + EPOCH_SECONDS
    for s in range(0, span, 5):
        ts = (t0 + timedelta(seconds=s)).isoformat()
        readings.append(
            {"recorded_at": ts, "kind": "heart_rate",
             "value": 60.0 + 5.0 * math.sin(s / 40.0) + float(rng.normal(0, 1))}
        )
    for s in range(0, span, 60):
        ts = (t0 + timedelta(seconds=s)).isoformat()
        readings.append({"recorded_at": ts, "kind": "hrv", "value": 40.0 + float(rng.normal(0, 3))})
        readings.append({"recorded_at": ts, "kind": "respiratory_rate", "value": 14.0 + float(rng.normal(0, 0.5))})
        readings.append({"recorded_at": ts, "kind": "spo2", "value": 97.0 + float(rng.normal(0, 0.5))})
    return {
        "epoch_start_at": epoch_start.isoformat(),
        "session_started_at": t0.isoformat(),
        "readings": readings,
        # 5 prior epochs of hr_mean so all three lag features resolve to finite.
        "hr_mean_history": [60.2, 60.8, 61.1, 60.5, 61.4],
    }


def _signal(payload: dict[str, Any]) -> SignalPacket:
    return SignalPacket(
        user_id=USER_ID,
        timestamp=datetime.now(timezone.utc),
        modality=Modality.BIOMETRIC.value,
        intent="continuous",
        kind="hr_30s",
        payload=payload,
        source="watch.hr_30s",
        confidence=None,
    )


def _is_finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


def test_all_24_features_present_and_finite() -> None:
    snap = extract(_signal(_synthetic_window()))
    assert isinstance(snap, FeatureSnapshot)
    assert snap.modality == Modality.BIOMETRIC.value
    assert snap.payload["extractor"] == EXTRACTOR_TAG

    features = snap.payload["features"]
    # Exactly the 24 model columns, no more, no fewer.
    assert set(features.keys()) == set(FEATURE_COLS), (
        f"feature key mismatch: {set(features) ^ set(FEATURE_COLS)}"
    )
    assert len(FEATURE_COLS) == 24
    assert snap.payload["feature_cols"] == list(FEATURE_COLS)

    for col in FEATURE_COLS:
        assert _is_finite(features[col]), f"{col} not finite: {features[col]!r}"

    # The ordered vector matches the keyed dict in declared order.
    vector = snap.payload["vector"]
    assert len(vector) == 24
    assert vector == [features[c] for c in FEATURE_COLS]

    # Sanity on a couple of derived values.
    assert features["hr_n"] > 0
    assert 0.0 <= features["hr_pct_above_baseline"] <= 1.0
    print("[1/3] 24 features present + finite + ordered vector OK")


def test_lags_nan_without_history() -> None:
    """Honest behavior: with no prior history, the 3 lag features are NaN, not faked."""
    payload = _synthetic_window()
    payload.pop("hr_mean_history")
    snap = extract(_signal(payload))
    features = snap.payload["features"]
    for col in ("hr_lag1_mean", "hr_lag3_mean", "hr_lag5_mean"):
        assert math.isnan(features[col]), f"{col} should be NaN without history"
    # In-window features remain finite even with no lag history.
    assert _is_finite(features["hr_mean"])
    assert _is_finite(features["spo2_mean"])
    print("[2/3] missing-history lags are NaN (not fabricated); window feats still finite")


def test_registered_for_biometric_modality() -> None:
    """The extractor is wired into the participant registry for Modality.BIOMETRIC."""
    assert EXTRACTORS[Modality.BIOMETRIC.value] is extract
    assert select_extractor(Modality.BIOMETRIC.value) is extract
    print("[3/3] extractor registered for Modality.BIOMETRIC")


if __name__ == "__main__":
    test_all_24_features_present_and_finite()
    test_lags_nan_without_history()
    test_registered_for_biometric_modality()
    print("\nfeatures.test_biometric: all passed.")
