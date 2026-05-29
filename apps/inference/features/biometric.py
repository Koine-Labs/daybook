# apps/inference/features/biometric.py
"""L2 biometric feature extractor — SignalPacket window -> the 24 REM feature_cols.

This is the L2 half of the REM nowcast pipeline. It consumes a biometric
SignalPacket carrying a *window* of already-derived watch readings (heart_rate,
hrv, respiratory_rate, spo2) and produces a FeatureSnapshot whose payload holds
the EXACT 24 features the frozen `production_binary_rem` model expects, in the
order the model's sidecar declares (`FEATURE_COLS`).

The feature math is NOT reimplemented here. We build a one-epoch SessionBundle
from the window and call `classifier.features.compute_session_features`, the
canonical extractor that produced the training parquet. Reusing it is what keeps
L2 output bit-identical to what the model was trained on — the same guarantee
the v0 `RealtimeClassifier` upheld by mirroring that file.

HR lag features (hr_lag1/3/5_mean) reference prior epochs' hr_mean and cannot be
computed from a single epoch's readings. They are filled from an optional
`hr_mean_history` carried in the payload (oldest-first, the immediately preceding
epoch hr_means), mirroring the v0 RealtimeClassifier `_hr_mean_history` deque.
When history is short or absent, the missing lags are NaN — honest, and exactly
what XGBoost saw at session start during training. No value is ever fabricated.

Expected SignalPacket.payload shape (semantic-first, #11 — derived values only,
never raw waveform):

    {
      "epoch_start_at": "<ISO-8601 tz-aware>",        # required
      "readings": [                                    # required; the context+epoch window
        {"recorded_at": "<ISO>", "kind": "heart_rate", "value": 61.0},
        {"recorded_at": "<ISO>", "kind": "hrv", "value": 42.0},
        ...
      ],
      "session_started_at": "<ISO>",                  # optional; defaults to window start
      "hr_mean_history": [60.1, 61.4, ...]            # optional; prior-epoch hr_means, oldest-first
    }

`epoch_start_at` / `readings[*].recorded_at` may instead be datetime objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from classifier.data import SessionBundle
from classifier.features import compute_session_features
from core.protocol.enums import Intent
from core.protocol.payloads import SignalPacket
from features.snapshot import FeatureSnapshot

_INTENT_VALUES = {i.value for i in Intent}
_DEFAULT_INTENT = Intent.CONTINUOUS.value

# The exact 24 features the frozen production_binary_rem model consumes, in the
# order its sidecar (production_binary_rem.meta.json) declares them.
FEATURE_COLS: tuple[str, ...] = (
    "hr_mean", "hr_std", "hr_min", "hr_max", "hr_range", "hr_median",
    "hr_slope", "hr_n", "hr_pct_above_baseline",
    "hrv_mean", "hrv_std", "hrv_min", "hrv_max", "hrv_n",
    "resp_mean", "resp_std", "resp_n",
    "spo2_mean", "spo2_std", "spo2_min", "spo2_n",
    "hr_lag1_mean", "hr_lag3_mean", "hr_lag5_mean",
)

# HR-lag features are computed from prior-epoch history, not the current window.
_LAG_COLS: tuple[tuple[str, int], ...] = (
    ("hr_lag1_mean", 1),
    ("hr_lag3_mean", 3),
    ("hr_lag5_mean", 5),
)

_BIOMETRIC_KINDS = ("heart_rate", "hrv", "respiratory_rate", "spo2")

EPOCH_SECONDS = 30
CONTEXT_SECONDS = 300

EXTRACTOR_TAG = "biometric_rem_features.v1"
SOURCE = "watch.biometric_window"


@dataclass
class _Window:
    epoch_start_at: datetime
    session_started_at: datetime
    sensors: pd.DataFrame
    hr_mean_history: list[float]


def _to_utc(value: Any) -> datetime:
    """Coerce an ISO string or datetime into a tz-aware UTC datetime."""
    if isinstance(value, datetime):
        ts = value
    else:
        ts = datetime.fromisoformat(str(value))
    if ts.tzinfo is None:
        raise ValueError("biometric window timestamps must be tz-aware UTC")
    return ts.astimezone(timezone.utc)


def _parse_window(payload: dict[str, Any]) -> _Window:
    """Validate + normalize the SignalPacket payload into a usable window."""
    if "epoch_start_at" not in payload:
        raise ValueError("biometric payload missing 'epoch_start_at'")
    epoch_start_at = _to_utc(payload["epoch_start_at"])

    raw_readings = payload.get("readings") or []
    rows: list[dict[str, Any]] = []
    for r in raw_readings:
        kind = r.get("kind")
        if kind not in _BIOMETRIC_KINDS:
            continue
        try:
            val = float(r["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if val != val:  # NaN
            continue
        rows.append(
            {"recorded_at": _to_utc(r["recorded_at"]), "kind": kind, "value": val}
        )

    sensors = pd.DataFrame(rows, columns=["recorded_at", "kind", "value"])
    if not sensors.empty:
        sensors["recorded_at"] = pd.to_datetime(sensors["recorded_at"], utc=True)
        sensors = sensors.sort_values("recorded_at").reset_index(drop=True)

    if "session_started_at" in payload and payload["session_started_at"] is not None:
        session_started_at = _to_utc(payload["session_started_at"])
    elif not sensors.empty:
        session_started_at = sensors["recorded_at"].iloc[0].to_pydatetime()
    else:
        session_started_at = epoch_start_at

    history_raw = payload.get("hr_mean_history") or []
    hr_mean_history = [float(h) for h in history_raw]

    return _Window(
        epoch_start_at=epoch_start_at,
        session_started_at=session_started_at,
        sensors=sensors,
        hr_mean_history=hr_mean_history,
    )


def _lag_value(history: list[float], k: int) -> float:
    """Prior-epoch hr_mean k steps back (oldest-first history); NaN if unavailable."""
    if len(history) < k:
        return float("nan")
    return history[-k]


def compute_biometric_features(payload: dict[str, Any]) -> dict[str, float]:
    """Run the canonical extractor over one biometric window -> 24-feature dict.

    Reuses classifier.features.compute_session_features for the in-window math;
    the 3 HR-lag features come from the supplied prior-epoch history.
    """
    win = _parse_window(payload)

    # The session median (hr_pct_above_baseline) is computed by the canonical
    # extractor over the bundle's sensors. Feeding the context+epoch window means
    # the baseline is the window's HR median — the best standalone estimate and
    # what a live per-epoch reading sees before a full night accumulates.
    epoch_end = win.epoch_start_at + pd.Timedelta(seconds=EPOCH_SECONDS)
    bundle = SessionBundle(
        session_id="biometric_nowcast",
        user_id="",
        started_at=pd.Timestamp(win.session_started_at),
        ended_at=pd.Timestamp(epoch_end),
        duration_seconds=int(
            (epoch_end - win.session_started_at).total_seconds()
        ),
        sensors=win.sensors,
        labels=pd.DataFrame(
            [{"epoch_start_at": pd.Timestamp(win.epoch_start_at), "stage": "REM"}]
        ),
    )

    feats: dict[str, float] = {c: float("nan") for c in FEATURE_COLS}

    computed = compute_session_features(
        bundle, epoch_seconds=EPOCH_SECONDS, context_seconds=CONTEXT_SECONDS
    )
    if not computed.empty:
        row = computed.iloc[0]
        for c in FEATURE_COLS:
            if c.endswith("_n"):
                feats[c] = float(row[c])
            elif c in row:
                feats[c] = float(row[c])

    # HR-lag features: carried from prior epochs, not the current window.
    for col, k in _LAG_COLS:
        feats[col] = _lag_value(win.hr_mean_history, k)

    return feats


def extract(sig: SignalPacket) -> FeatureSnapshot:
    """L2 biometric extractor: SignalPacket window -> FeatureSnapshot of 24 feats.

    Registered for Modality.BIOMETRIC. The output payload carries the 24
    feature_cols (keyed by name) plus the ordered vector and provenance tags, so
    L4's REM predictor can read the model's feature vector straight off the
    snapshot.
    """
    features = compute_biometric_features(sig.payload)
    vector = [features[c] for c in FEATURE_COLS]
    return FeatureSnapshot(
        user_id=sig.user_id,
        timestamp=sig.timestamp,
        modality=sig.modality,
        source=sig.source or SOURCE,
        payload={
            "kind": sig.kind,
            "extractor": EXTRACTOR_TAG,
            "feature_cols": list(FEATURE_COLS),
            "features": features,
            "vector": vector,
            "epoch_seconds": EPOCH_SECONDS,
            "context_seconds": CONTEXT_SECONDS,
        },
        intent=sig.intent if sig.intent in _INTENT_VALUES else _DEFAULT_INTENT,
        confidence=sig.confidence,
        i_model_id=sig.i_model_id,
    )
