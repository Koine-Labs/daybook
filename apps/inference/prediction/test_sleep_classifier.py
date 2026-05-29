"""Regression guard for the wrapped binary-REM predictor + participant test.

The headline guard reproduces the validated model EXACTLY: synthetic 24-feature
rows run through SleepClassifierPredictor.score_features must equal the production
model's own predict_proba to float tolerance. That proves the wrap (model load,
the exact feature_cols ordering, NaN-native missing handling) faithfully recovers
v0's inference rather than silently drifting. It needs only the committed model,
so it runs anywhere — including CI.

A separate sanity check compares against the recorded binary_rem_preds.parquet
(LOSO out-of-fold predictions — a DIFFERENT model than production, so not bit-
exact). That cache is gitignored (large, HK-derived), so the check SKIPS when
absent (CI) and runs locally where the cache exists.

Run: python -m prediction.test_sleep_classifier   (or pytest this file)
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bus.bus import TOPIC_FEATURE, TOPIC_PREDICTION, MessageBus  # noqa: E402
from core.protocol.enums import MetaContext, Modality, NodeRole, PayloadType  # noqa: E402
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from features.snapshot import FeatureSnapshot  # noqa: E402
from prediction import feature_participant as l4f  # noqa: E402
from prediction.predictors.sleep_classifier import (  # noqa: E402
    HORIZON_SECONDS,
    MODEL_ID,
    REM_AXIS,
    SleepClassifierPredictor,
)

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

_INFER_DIR = Path(__file__).resolve().parent.parent
_FEATURES_CACHE = _INFER_DIR / "classifier" / "runs" / "_features_cache.parquet"
_RECORDED_PREDS = (
    _INFER_DIR / "classifier" / "runs" / "20260517_v2_pure_bio" / "binary_rem_preds.parquet"
)
# Gitignored caches — tests needing them skip when absent (e.g. CI).
_PARQUET_AVAILABLE = _FEATURES_CACHE.exists() and _RECORDED_PREDS.exists()


def _synthetic_feature_rows() -> list[dict[str, float]]:
    """Deterministic 24-feature rows (all feature_cols present). Values are
    plausible but arbitrary — the exact-wrap guard only needs wrapper(row) to equal
    the model's own predict_proba(row), for which any inputs suffice. Includes a
    cold-start row with NaN HR-lags to exercise NaN-native handling."""
    base = {
        "hr_mean": 58.0, "hr_std": 4.2, "hr_min": 51.0, "hr_max": 70.0, "hr_range": 19.0,
        "hr_median": 57.0, "hr_slope": -0.3, "hr_n": 60.0, "hr_pct_above_baseline": 0.2,
        "hrv_mean": 45.0, "hrv_std": 12.0, "hrv_min": 20.0, "hrv_max": 80.0, "hrv_n": 2.0,
        "resp_mean": 14.0, "resp_std": 1.1, "resp_n": 2.0,
        "spo2_mean": 96.5, "spo2_std": 0.8, "spo2_min": 95.0, "spo2_n": 2.0,
        "hr_lag1_mean": 59.0, "hr_lag3_mean": 60.0, "hr_lag5_mean": 61.0,
    }
    elevated = {**base, "hr_mean": 68.0, "hr_median": 67.0, "hrv_mean": 30.0,
                "hr_pct_above_baseline": 0.85}
    cold_start = {**base, "hr_lag1_mean": float("nan"),
                  "hr_lag3_mean": float("nan"), "hr_lag5_mean": float("nan")}
    return [base, elevated, cold_start]


def test_wrapper_reproduces_production_model_exactly():
    """score_features == production model.predict_proba (atol=1e-4), synthetic rows."""
    import xgboost as xgb

    pred = SleepClassifierPredictor()
    cols = pred.feature_cols
    assert len(cols) == 24, "frozen model has exactly 24 feature columns"

    rows = _synthetic_feature_rows()
    matrix = np.array([[row[c] for c in cols] for row in rows], dtype=np.float64)

    # Ground truth: the production model scored directly as a batch.
    model = xgb.XGBClassifier()
    model.load_model(str(pred._model_dir / "production_binary_rem.json"))
    direct = model.predict_proba(matrix)[:, 1]

    # Wrapper path: row dicts through score_features (the live call shape).
    wrapped = np.array([pred.score_features(row) for row in rows])

    assert np.allclose(wrapped, direct, atol=1e-4, rtol=0.0), (
        f"wrapper drifted from production model: max abs diff "
        f"{np.abs(wrapped - direct).max():.3e}"
    )


@pytest.mark.skipif(not _PARQUET_AVAILABLE, reason="feature cache absent (gitignored; local-only)")
def test_wrapper_agrees_with_recorded_loso_preds():
    """Sanity: wrapped probs strongly track recorded LOSO probs (not bit-exact)."""
    import pandas as pd

    feats = pd.read_parquet(_FEATURES_CACHE)
    recorded = pd.read_parquet(_RECORDED_PREDS)
    merged = (
        feats.merge(recorded, on=["session_id", "epoch_start_at"], how="inner")
        .sample(n=min(3000, len(recorded)), random_state=0)
        .reset_index(drop=True)
    )

    pred = SleepClassifierPredictor()
    cols = pred.feature_cols
    wrapped = np.array(
        [pred.score_features({c: row[c] for c in cols}) for _, row in merged.iterrows()]
    )
    recorded_p = merged["y_proba"].to_numpy(dtype=np.float64)

    # Bounds reflect production-vs-LOSO reality (full set: corr 0.90, agree 0.74),
    # not equality between two different models. A mis-ordered feature vector or
    # wrong model collapses the correlation well below these floors.
    corr = float(np.corrcoef(wrapped, recorded_p)[0, 1])
    assert corr >= 0.85, f"production vs LOSO probs should track closely; corr={corr:.3f}"

    thr = pred.threshold
    assert thr == pytest.approx(0.23)
    wrapped_bin = (wrapped >= thr).astype(int)
    recorded_bin = merged["y_pred"].to_numpy(dtype=int)
    agree = float((wrapped_bin == recorded_bin).mean())
    assert agree >= 0.68, f"REM-call agreement with recorded preds too low: {agree:.3f}"


def test_predict_rem_emits_well_formed_prediction():
    """A single epoch -> a "rem" Prediction with the locked-down shape."""
    pred = SleepClassifierPredictor()
    feats = _synthetic_feature_rows()[0]
    proba = pred.score_features(feats)

    out = pred.predict_rem(user_id=USER, features=feats, i_model_id="im-rem-1")
    assert out.axis == REM_AXIS
    assert out.horizon_seconds == HORIZON_SECONDS == 0  # nowcast, not a forecast
    assert out.model_id == MODEL_ID == "production_binary_rem"
    assert out.provenance == "placeholder"
    assert out.cold_start is False
    assert out.confidence == pytest.approx(proba)
    assert out.distribution["rem"] == pytest.approx(proba)
    assert out.distribution["non_rem"] == pytest.approx(1.0 - proba)
    assert out.i_model_id == "im-rem-1"
    assert out.user_id == USER


# ----- participant: biometric FeatureSnapshot -> rem Prediction on bus --------


def _biometric_feature_envelope(features: dict) -> MessageEnvelope:
    now = datetime.now(timezone.utc)
    snap = FeatureSnapshot(
        user_id=USER,
        timestamp=now,
        modality=Modality.BIOMETRIC.value,
        source="watch.hr_30s",
        payload={"kind": "hr_epoch", "features": features, "extractor": "stub_passthrough"},
        i_model_id="im-bio-1",
    )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.FEATURE,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=now,
        meta_context=MetaContext.SLEEP,
        consent_scope="sleep_session_v1",
        trace_id=str(uuid.uuid4()),
        payload=snap,
        i_model_id="im-bio-1",
    )


def _non_biometric_envelope() -> MessageEnvelope:
    now = datetime.now(timezone.utc)
    snap = FeatureSnapshot(
        user_id=USER,
        timestamp=now,
        modality=Modality.AUDIO.value,
        source="mac.mic",
        payload={"kind": "speech_final", "features": {"text": "hi"}},
    )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.FEATURE,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=now,
        meta_context=MetaContext.WAKING,
        consent_scope="mic_continuous_v1",
        trace_id=str(uuid.uuid4()),
        payload=snap,
    )


def _drive(inbound: MessageEnvelope) -> list[MessageEnvelope]:
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_PREDICTION, lambda env: captured.append(env))
    l4f.register(bus)
    bus.publish(TOPIC_FEATURE, inbound)
    return captured


def test_participant_biometric_yields_rem_prediction_same_trace():
    feats = _synthetic_feature_rows()[0]
    inbound = _biometric_feature_envelope(feats)
    out = _drive(inbound)

    assert len(out) == 1, "one biometric feature epoch -> one rem prediction"
    env = out[0]
    assert env.type == PayloadType.PREDICTION
    assert env.trace_id == inbound.trace_id
    assert env.meta_context == inbound.meta_context
    assert env.consent_scope == inbound.consent_scope
    assert env.i_model_id == inbound.i_model_id
    assert env.source_role == NodeRole.DESKTOP_COMPUTE  # role_for("L4.prediction")
    p = env.payload
    assert p.axis == REM_AXIS
    assert p.model_id == "production_binary_rem"
    assert p.horizon_seconds == 0
    assert p.confidence is not None and 0.0 <= p.confidence <= 1.0
    assert p.user_id == USER
    assert p.cold_start is False


def test_participant_skips_non_biometric():
    out = _drive(_non_biometric_envelope())
    assert out == [], "non-biometric snapshots must not produce a rem prediction"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
