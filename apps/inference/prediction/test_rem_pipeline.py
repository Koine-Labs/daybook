"""End-to-end integration test: the real L2 biometric -> L4 REM arc over the bus.

This is the *whole pipeline*, not a unit slice. It wires a real MessageBus with
the L2 features participant (features/participant.py) and the L4 feature-based
REM participant (prediction/feature_participant.py), publishes a biometric
SignalPacket on TOPIC_SIGNAL, and asserts a "rem" Prediction lands on
TOPIC_PREDICTION carrying the frozen model's real probability for that input.

No stubs, no network: L2 runs the canonical classifier.features extractor over a
raw readings window (Modality.BIOMETRIC is registered to the real
features.biometric.extract, not the passthrough), and L4 scores it with the
actual production_binary_rem XGBoost. The arc proves the seam everything else
rides on: SignalPacket -> FeatureSnapshot(24 feats) -> Prediction, with trace_id
/ meta_context / consent_scope / i_model_id inherited unbroken (#1/#11/#14).

KNOWN ANSWER. The window's L2-extracted 24-feature vector is the model's actual
input, so the expected REM probability is the production model's own score on
that exact vector (computed in-test, deterministic). We assert the bus output
equals it to float tolerance — a guard that the wired path reproduces the
validated model rather than silently drifting. The recorded LOSO predictions in
binary_rem_preds.parquet are a *different* model (out-of-fold; see
test_sleep_classifier.py), so they anchor the realistic input/ballpark, not a
bit-exact target.

Run: python -m pytest prediction/test_rem_pipeline.py -v
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bus.bus import (  # noqa: E402
    TOPIC_PREDICTION,
    TOPIC_SIGNAL,
    MessageBus,
)
from core.protocol.enums import (  # noqa: E402
    Intent,
    MetaContext,
    Modality,
    NodeRole,
    PayloadType,
)
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import Prediction, SignalPacket  # noqa: E402
from features.biometric import (  # noqa: E402
    CONTEXT_SECONDS,
    EPOCH_SECONDS,
    FEATURE_COLS,
    extract as biometric_extract,
)
from features import participant as l2_features  # noqa: E402
from prediction import feature_participant as l4_rem  # noqa: E402
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

# A fixed clock so the reconstructed window is deterministic.
_T0 = datetime(2026, 5, 28, 3, 0, 0, tzinfo=timezone.utc)
_EPOCH_START = _T0 + timedelta(seconds=CONTEXT_SECONDS)


# --------------------------------------------------------------------------- #
# Building biometric SignalPackets from a raw readings window (the L1 shape).  #
# --------------------------------------------------------------------------- #


def _signal_packet(payload: dict[str, Any]) -> SignalPacket:
    return SignalPacket(
        user_id=USER,
        timestamp=datetime.now(timezone.utc),
        modality=Modality.BIOMETRIC.value,
        intent=Intent.CONTINUOUS.value,
        kind="hr_30s",
        payload=payload,
        source="watch.hr_30s",
    )


def _signal_envelope(sig: SignalPacket, *, trace_id: str) -> MessageEnvelope:
    """Wrap a SignalPacket as the L1 capture node would put it on TOPIC_SIGNAL."""
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.SIGNAL,
        source_role=NodeRole.WISP_EDGE,  # role_for("L1.capture")
        occurred_at=datetime.now(timezone.utc),
        meta_context=MetaContext.SLEEP,
        consent_scope="sleep_session_v1",
        trace_id=trace_id,
        payload=sig,
        i_model_id="im-bio-1",
    )


def _constant_hr_window() -> dict[str, Any]:
    """A fully deterministic HR-only epoch: 30 samples at a constant rate.

    Constant HR makes the in-window features hand-derivable (mean=min=max=median,
    std=range=slope=0, pct_above_baseline=0); HRV/resp/spo2 are absent (NaN, the
    realistic Apple-Watch shape the model trained on); lags come from history.
    """
    readings = [
        {
            "recorded_at": (_EPOCH_START + timedelta(seconds=i)).isoformat(),
            "kind": "heart_rate",
            "value": 66.0,
        }
        for i in range(EPOCH_SECONDS)
    ]
    return {
        "epoch_start_at": _EPOCH_START.isoformat(),
        "session_started_at": _T0.isoformat(),
        "readings": readings,
        "hr_mean_history": [64.0, 65.0, 66.0, 67.0, 68.0],  # oldest-first
    }


def _window_from_cached_row(row: pd.Series) -> dict[str, Any]:
    """Reconstruct a raw HR readings window spanning the real row's HR range.

    The exact cached row can't be round-tripped (sparse HRV/resp/spo2 and the
    unrecoverable session-median baseline / raw sample times), so this is a
    *representative* dense-HR window over the real [hr_min, hr_max] span. Its
    purpose is to drive the real extractor over a realistic biometric epoch; the
    expected probability is read back from the L2 output, not assumed equal to
    the recorded LOSO proba.
    """
    hr_n = int(row["hr_n"])
    span = CONTEXT_SECONDS + EPOCH_SECONDS
    values = np.linspace(float(row["hr_min"]), float(row["hr_max"]), hr_n)
    readings = [
        {
            "recorded_at": (_T0 + timedelta(seconds=i * span / hr_n)).isoformat(),
            "kind": "heart_rate",
            "value": float(values[i]),
        }
        for i in range(hr_n)
    ]
    return {
        "epoch_start_at": _EPOCH_START.isoformat(),
        "session_started_at": _T0.isoformat(),
        "readings": readings,
        "hr_mean_history": [
            float(row["hr_lag5_mean"]),
            0.0,
            0.0,
            float(row["hr_lag3_mean"]),
            float(row["hr_lag1_mean"]),
        ],
    }


def _representative_cached_row() -> pd.Series:
    """A REM-positive, HR-dense cached row with finite lags (a real input shape)."""
    feats = pd.read_parquet(_FEATURES_CACHE)
    recorded = pd.read_parquet(_RECORDED_PREDS)
    merged = feats.merge(recorded, on=_KEY, how="inner")
    sub = merged[merged["hr_n"] >= 30].dropna(
        subset=["hr_lag1_mean", "hr_lag3_mean", "hr_lag5_mean"]
    )
    rem = sub[sub["y_true"] == 1]
    chosen = (rem if len(rem) else sub).sort_values("hr_n", ascending=False)
    assert len(chosen), "no HR-dense cached row with finite lags found"
    return chosen.iloc[0]


# --------------------------------------------------------------------------- #
# The bus harness: register L2 + L4, publish a SignalPacket, capture L4 out.   #
# --------------------------------------------------------------------------- #


def _drive_pipeline(env: MessageEnvelope) -> list[MessageEnvelope]:
    """Wire the real L2 + L4 participants and run one SignalPacket through."""
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_PREDICTION, captured.append)
    l2_features.register(bus)  # TOPIC_SIGNAL -> TOPIC_FEATURE (real biometric extractor)
    l4_rem.register(bus)       # TOPIC_FEATURE -> TOPIC_PREDICTION (real REM model)
    bus.publish(TOPIC_SIGNAL, env)
    return captured


def _expected_proba(sig: SignalPacket) -> float:
    """The frozen model's own score on the L2 output for this window (known answer)."""
    snapshot = biometric_extract(sig)
    feats = {c: snapshot.payload["features"][c] for c in FEATURE_COLS}
    return SleepClassifierPredictor().score_features(feats)


# --------------------------------------------------------------------------- #
# Tests.                                                                       #
# --------------------------------------------------------------------------- #


def test_biometric_signal_to_rem_prediction_full_arc():
    """SignalPacket -> (L2 real extractor) -> (L4 real model) -> rem Prediction.

    The two required assertions: (1) a single "rem" Prediction arrives with the
    SAME trace_id, and (2) distribution["rem"] matches the frozen model's score
    on the actual L2-derived input within float tolerance.
    """
    trace_id = str(uuid.uuid4())
    sig = _signal_packet(_window_from_cached_row(_representative_cached_row()))
    expected = _expected_proba(sig)

    inbound = _signal_envelope(sig, trace_id=trace_id)
    out = _drive_pipeline(inbound)

    assert len(out) == 1, "one biometric epoch must yield exactly one rem prediction"
    env = out[0]

    # (1) a "rem" Prediction on TOPIC_PREDICTION with the same trace_id.
    assert env.type == PayloadType.PREDICTION
    assert env.trace_id == trace_id
    pred = env.payload
    assert isinstance(pred, Prediction)
    assert pred.axis == REM_AXIS == "rem"

    # (2) its rem probability is the real model's score on the L2-derived input.
    assert pred.distribution["rem"] == pytest.approx(expected, abs=1e-9)
    assert pred.distribution["non_rem"] == pytest.approx(1.0 - expected, abs=1e-9)
    assert 0.0 <= pred.distribution["rem"] <= 1.0


def test_full_arc_preserves_envelope_context_and_provenance():
    """Trace + meta_context + consent + i_model inherit L1->L4; shape is locked."""
    trace_id = str(uuid.uuid4())
    sig = _signal_packet(_constant_hr_window())
    inbound = _signal_envelope(sig, trace_id=trace_id)

    out = _drive_pipeline(inbound)
    assert len(out) == 1
    env = out[0]

    # Envelope context threaded through both layers unchanged (#1/#11/#14).
    assert env.trace_id == inbound.trace_id
    assert env.meta_context == inbound.meta_context == MetaContext.SLEEP
    assert env.consent_scope == inbound.consent_scope == "sleep_session_v1"
    assert env.i_model_id == inbound.i_model_id == "im-bio-1"
    assert env.source_role == NodeRole.DESKTOP_COMPUTE  # role_for("L4.prediction")

    pred = env.payload
    assert pred.model_id == MODEL_ID == "production_binary_rem"
    assert pred.horizon_seconds == HORIZON_SECONDS == 0  # nowcast, not a forecast
    assert pred.provenance == "placeholder"
    assert pred.cold_start is False
    assert pred.user_id == USER
    assert pred.i_model_id == "im-bio-1"
    assert pred.confidence == pytest.approx(pred.distribution["rem"])


def test_full_arc_known_answer_on_deterministic_window():
    """A hand-derivable constant-HR epoch: bus rem proba == direct model score.

    The constant-HR window's 24-feature vector is fully deterministic, so the
    known answer is the production model's score on it. Asserting the bus path
    equals that proves the SignalPacket->FeatureSnapshot->Prediction arc routes
    the real model output end-to-end (no stub, no network).
    """
    sig = _signal_packet(_constant_hr_window())
    expected = _expected_proba(sig)

    out = _drive_pipeline(_signal_envelope(sig, trace_id="trace-const"))
    assert len(out) == 1
    pred = out[0].payload

    assert pred.distribution["rem"] == pytest.approx(expected, abs=1e-12)
    # Threshold call is consistent with the frozen decision threshold (0.23).
    threshold = SleepClassifierPredictor().threshold
    assert threshold == pytest.approx(0.23)
    is_rem = pred.distribution["rem"] >= threshold
    assert isinstance(is_rem, (bool, np.bool_))


def test_full_arc_tracks_recorded_loso_predictions():
    """Sanity anchor: the wired path tracks the recorded preds across real rows.

    The recorded probabilities are LOSO out-of-fold (a different model than
    production), so this asserts strong correlation over a batch of real cached
    rows pushed through the bus — a guard that the arc carries genuine model
    signal, not a mis-ordered or constant vector.
    """
    feats = pd.read_parquet(_FEATURES_CACHE)
    recorded = pd.read_parquet(_RECORDED_PREDS)
    merged = feats.merge(recorded, on=_KEY, how="inner")
    sub = (
        merged[merged["hr_n"] >= 30]
        .dropna(subset=["hr_lag1_mean", "hr_lag3_mean", "hr_lag5_mean"])
        .sort_values("hr_n", ascending=False)
        .head(80)
        .reset_index(drop=True)
    )
    assert len(sub) >= 30, "need a batch of HR-dense rows to bound correlation"

    bus_probs: list[float] = []
    loso_probs: list[float] = []
    for _, row in sub.iterrows():
        sig = _signal_packet(_window_from_cached_row(row))
        out = _drive_pipeline(_signal_envelope(sig, trace_id=str(uuid.uuid4())))
        assert len(out) == 1
        bus_probs.append(out[0].payload.distribution["rem"])
        loso_probs.append(float(row["y_proba"]))

    corr = float(np.corrcoef(bus_probs, loso_probs)[0, 1])
    assert corr >= 0.5, f"wired path should track recorded LOSO probs; corr={corr:.3f}"


def test_non_biometric_signal_yields_no_rem_prediction():
    """A non-biometric SignalPacket flows through L2 but L4 must not fire REM."""
    sig = SignalPacket(
        user_id=USER,
        timestamp=datetime.now(timezone.utc),
        modality=Modality.AUDIO.value,
        intent=Intent.CONTINUOUS.value,
        kind="speech_final",
        payload={"text": "still awake"},
        source="mac.mic",
    )
    env = MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.SIGNAL,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=datetime.now(timezone.utc),
        meta_context=MetaContext.WAKING,
        consent_scope="mic_continuous_v1",
        trace_id=str(uuid.uuid4()),
        payload=sig,
    )
    out = _drive_pipeline(env)
    assert out == [], "non-biometric modality must not produce a rem prediction"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
