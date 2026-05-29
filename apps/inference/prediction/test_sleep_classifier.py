"""Regression guard for the wrapped binary-REM predictor + participant test.

The headline guard reproduces the validated model EXACTLY: cached feature rows
run through SleepClassifierPredictor.score_features must equal the production
model's own predict_proba to float tolerance. That proves the wrap (model load,
the exact feature_cols ordering, NaN-native missing handling) faithfully recovers
v0's inference rather than silently drifting.

It ALSO sanity-checks against the recorded binary_rem_preds.parquet. Those
recorded probabilities are LOSO out-of-fold predictions (each session scored by a
model trained on the OTHER sessions; see classifier/train.py), NOT the production
model trained on all data — so they are intentionally NOT bit-exact. The guard
asserts strong agreement (Pearson corr + threshold-decision agreement) so a
mis-ordered feature vector or wrong model would still be caught, without falsely
demanding equality between two different models.

Run: python -m prediction.test_sleep_classifier   (or pytest this file)
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
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
    _INFER_DIR
    / "classifier"
    / "runs"
    / "20260517_v2_pure_bio"
    / "binary_rem_preds.parquet"
)

_KEY = ["session_id", "epoch_start_at"]
_SAMPLE_N = 3000  # enough to bound corr tightly; fast to score
_SEED = 0  # representative random sample (head() biases to a single session)


def _load_aligned_sample() -> pd.DataFrame:
    feats = pd.read_parquet(_FEATURES_CACHE)
    recorded = pd.read_parquet(_RECORDED_PREDS)
    merged = feats.merge(recorded, on=_KEY, how="inner")
    assert len(merged) == len(recorded), "feature cache and preds must align 1:1 on keys"
    return (
        merged.sample(n=min(_SAMPLE_N, len(merged)), random_state=_SEED)
        .reset_index(drop=True)
    )


def test_wrapper_reproduces_production_model_exactly():
    """score_features over cached rows == production model.predict_proba (atol=1e-4)."""
    import xgboost as xgb  # local import keeps the BLOCKED check honest

    sample = _load_aligned_sample()
    pred = SleepClassifierPredictor()
    cols = pred.feature_cols
    assert len(cols) == 24, "frozen model has exactly 24 feature columns"

    # Ground truth: the production model scored directly as a batch.
    model = xgb.XGBClassifier()
    model.load_model(str(pred._model_dir / "production_binary_rem.json"))
    direct = model.predict_proba(sample[cols].to_numpy(dtype=np.float64))[:, 1]

    # Wrapper path: row-by-row dicts through score_features (the live call shape).
    wrapped = np.array(
        [pred.score_features({c: row[c] for c in cols}) for _, row in sample.iterrows()]
    )

    assert np.allclose(wrapped, direct, atol=1e-4, rtol=0.0), (
        f"wrapper drifted from production model: max abs diff "
        f"{np.abs(wrapped - direct).max():.3e}"
    )


def test_wrapper_agrees_with_recorded_loso_preds():
    """Sanity: wrapped probs strongly track recorded LOSO probs (not bit-exact)."""
    sample = _load_aligned_sample()
    pred = SleepClassifierPredictor()
    cols = pred.feature_cols

    wrapped = np.array(
        [pred.score_features({c: row[c] for c in cols}) for _, row in sample.iterrows()]
    )
    recorded = sample["y_proba"].to_numpy(dtype=np.float64)

    # Bounds reflect production-vs-LOSO reality (full set: corr 0.90, agree 0.74),
    # not equality between two different models. A mis-ordered feature vector or
    # wrong model collapses the correlation well below these floors.
    corr = float(np.corrcoef(wrapped, recorded)[0, 1])
    assert corr >= 0.85, f"production vs LOSO probs should track closely; corr={corr:.3f}"

    # Threshold-decision agreement against the recorded y_pred binary labels.
    thr = pred.threshold
    assert thr == pytest.approx(0.23)
    wrapped_bin = (wrapped >= thr).astype(int)
    recorded_bin = sample["y_pred"].to_numpy(dtype=int)
    agree = float((wrapped_bin == recorded_bin).mean())
    assert agree >= 0.68, f"REM-call agreement with recorded preds too low: {agree:.3f}"


def test_predict_rem_emits_well_formed_prediction():
    """A single epoch -> a "rem" Prediction with the locked-down shape."""
    sample = _load_aligned_sample()
    pred = SleepClassifierPredictor()
    cols = pred.feature_cols
    row = sample.iloc[0]
    feats = {c: row[c] for c in cols}
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
    sample = _load_aligned_sample()
    cols = SleepClassifierPredictor().feature_cols
    feats = {c: float(sample.iloc[0][c]) if pd.notna(sample.iloc[0][c]) else None for c in cols}

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
