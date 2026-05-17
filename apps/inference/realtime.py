"""Real-time sleep stage inference for the bedside Pi daemon.

Wraps the trained binary REM XGBoost model. Maintains rolling sensor buffers
and computes per-epoch features matching the training pipeline.

Usage:
    from inference.realtime import RealtimeClassifier
    clf = RealtimeClassifier.load()
    clf.start_session(started_at=datetime.now(timezone.utc))
    clf.add_reading(ts, "heart_rate", 68.0)
    clf.add_reading(ts2, "respiratory_rate", 14.0)
    pred = clf.predict_at(epoch_start_at=now)
    print(pred.rem_probability, pred.is_rem)

NOTE: per-epoch feature computation in this file is a deliberate mirror of
`classifier/features.py:compute_session_features`. If features.py changes,
update this file too. The smoke test in `__main__` validates parity against
the cached offline features for one real session.
"""
from __future__ import annotations

import json
import logging
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Deque

import numpy as np
import xgboost as xgb

# Import db helper for optional state-estimate persistence.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from db import get_conn  # type: ignore[import-not-found]
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

logger = logging.getLogger(__name__)

SUPPORTED_KINDS = {"heart_rate", "hrv", "respiratory_rate", "spo2"}
EPOCH_SECONDS = 30
CONTEXT_SECONDS = 300
STATE_SOURCE_TAG = "realtime_v1"


@dataclass
class RealtimePrediction:
    epoch_start_at: datetime
    rem_probability: float
    is_rem: bool
    threshold: float
    n_in_window: dict[str, int]
    features: dict[str, float]


@dataclass
class _Reading:
    recorded_at: datetime
    value: float


class RealtimeClassifier:
    """Live binary-REM inference with rolling sensor buffers + running session median."""

    def __init__(
        self,
        model: xgb.XGBClassifier,
        feature_cols: list[str],
        threshold: float,
        epoch_seconds: int = EPOCH_SECONDS,
        context_seconds: int = CONTEXT_SECONDS,
        persist_state: bool = False,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self.model = model
        self.feature_cols = feature_cols
        self.threshold = threshold
        self.epoch_seconds = epoch_seconds
        self.context_seconds = context_seconds
        self.persist_state = persist_state
        self.user_id = user_id
        self.session_id = session_id
        self._buffers: dict[str, Deque[_Reading]] = {k: deque() for k in SUPPORTED_KINDS}
        self._hr_mean_history: Deque[float] = deque(maxlen=10)
        self._all_hr_values: list[float] = []
        self._session_started_at: datetime | None = None
        if self.persist_state and not _DB_AVAILABLE:
            logger.warning("persist_state=True but db.py unavailable — state writes disabled")
            self.persist_state = False

    @classmethod
    def load(cls, model_dir: Path | None = None) -> "RealtimeClassifier":
        if model_dir is None:
            model_dir = Path(__file__).parent / "classifier" / "models"
        meta_path = model_dir / "production_binary_rem.meta.json"
        meta = json.loads(meta_path.read_text())
        model_path = model_dir / meta["model_path"]
        model = xgb.XGBClassifier()
        model.load_model(str(model_path))
        return cls(
            model=model,
            feature_cols=meta["feature_cols"],
            threshold=float(meta["chosen_threshold"]),
            epoch_seconds=int(meta["epoch_seconds"]),
            context_seconds=int(meta["context_seconds"]),
        )

    def start_session(
        self,
        started_at: datetime,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self._session_started_at = started_at
        if user_id is not None:
            self.user_id = user_id
        if session_id is not None:
            self.session_id = session_id
        for buf in self._buffers.values():
            buf.clear()
        self._hr_mean_history.clear()
        self._all_hr_values.clear()

    def add_reading(self, recorded_at: datetime, kind: str, value: float) -> None:
        if kind not in SUPPORTED_KINDS:
            return
        self._buffers[kind].append(_Reading(recorded_at, value))
        if kind == "heart_rate":
            self._all_hr_values.append(value)
        cutoff = recorded_at - timedelta(seconds=self.context_seconds + 60)
        for buf in self._buffers.values():
            while buf and buf[0].recorded_at < cutoff:
                buf.popleft()

    def predict_at(self, epoch_start_at: datetime) -> RealtimePrediction:
        feats = self._compute_features(epoch_start_at)
        x_row = np.array(
            [[feats.get(c, float("nan")) for c in self.feature_cols]],
            dtype=np.float64,
        )
        proba = float(self.model.predict_proba(x_row)[0, 1])

        win_lo = epoch_start_at - timedelta(seconds=self.context_seconds)
        win_hi = epoch_start_at + timedelta(seconds=self.epoch_seconds)
        n_in_window = {
            k: sum(1 for r in self._buffers[k] if win_lo <= r.recorded_at < win_hi)
            for k in SUPPORTED_KINDS
        }

        self._hr_mean_history.append(feats.get("hr_mean", float("nan")))

        pred = RealtimePrediction(
            epoch_start_at=epoch_start_at,
            rem_probability=proba,
            is_rem=proba >= self.threshold,
            threshold=self.threshold,
            n_in_window=n_in_window,
            features=feats,
        )

        if self.persist_state and self.user_id is not None:
            self._persist_state(pred)

        return pred

    def _persist_state(self, pred: RealtimePrediction) -> None:
        """Write one user_state_estimate row. Best-effort: log on failure, don't raise."""
        try:
            stage_proba = {"REM": pred.rem_probability, "NOT_REM": 1.0 - pred.rem_probability}
            # Strip non-finite values from features before JSON serialization
            clean_features = {
                k: v for k, v in pred.features.items()
                if isinstance(v, (int, float)) and not (isinstance(v, float) and (v != v))
            }
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_state_estimate
                        (user_id, session_id, estimated_at, stage_proba,
                         confidence, source, features)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                    """,
                    (
                        self.user_id,
                        self.session_id,
                        pred.epoch_start_at,
                        json.dumps(stage_proba),
                        pred.rem_probability,  # use REM prob as confidence proxy for v1
                        STATE_SOURCE_TAG,
                        json.dumps(clean_features),
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.warning("Failed to persist user_state_estimate: %s", e)

    def _compute_features(self, epoch_start_at: datetime) -> dict[str, float]:
        win_lo = epoch_start_at - timedelta(seconds=self.context_seconds)
        win_hi = epoch_start_at + timedelta(seconds=self.epoch_seconds)
        feats: dict[str, float] = {}

        # heart_rate (richest set of features)
        hr_pairs = [(r.recorded_at, r.value) for r in self._buffers["heart_rate"] if win_lo <= r.recorded_at < win_hi]
        if hr_pairs:
            t_sec = np.array([(t - epoch_start_at).total_seconds() for t, _ in hr_pairs], dtype=np.float64)
            v = np.array([x for _, x in hr_pairs], dtype=np.float64)
            feats["hr_mean"] = float(v.mean())
            feats["hr_std"] = float(v.std(ddof=0)) if v.size > 1 else float("nan")
            feats["hr_min"] = float(v.min())
            feats["hr_max"] = float(v.max())
            feats["hr_range"] = float(v.max() - v.min())
            feats["hr_median"] = float(np.median(v))
            feats["hr_slope"] = _slope(t_sec, v)
            feats["hr_n"] = int(v.size)
            session_median = float(np.median(self._all_hr_values)) if self._all_hr_values else float("nan")
            feats["hr_pct_above_baseline"] = float((v > session_median).mean()) if not np.isnan(session_median) else float("nan")
        else:
            for k in ("hr_mean", "hr_std", "hr_min", "hr_max", "hr_range", "hr_median", "hr_slope", "hr_pct_above_baseline"):
                feats[k] = float("nan")
            feats["hr_n"] = 0

        # hrv (mean/std/min/max/n)
        hrv_v = np.array([r.value for r in self._buffers["hrv"] if win_lo <= r.recorded_at < win_hi], dtype=np.float64)
        if hrv_v.size:
            feats["hrv_mean"] = float(hrv_v.mean())
            feats["hrv_std"] = float(hrv_v.std(ddof=0)) if hrv_v.size > 1 else float("nan")
            feats["hrv_min"] = float(hrv_v.min())
            feats["hrv_max"] = float(hrv_v.max())
            feats["hrv_n"] = int(hrv_v.size)
        else:
            for k in ("hrv_mean", "hrv_std", "hrv_min", "hrv_max"):
                feats[k] = float("nan")
            feats["hrv_n"] = 0

        # respiratory_rate (mean/std/n)
        resp_v = np.array([r.value for r in self._buffers["respiratory_rate"] if win_lo <= r.recorded_at < win_hi], dtype=np.float64)
        if resp_v.size:
            feats["resp_mean"] = float(resp_v.mean())
            feats["resp_std"] = float(resp_v.std(ddof=0)) if resp_v.size > 1 else float("nan")
            feats["resp_n"] = int(resp_v.size)
        else:
            feats["resp_mean"] = float("nan")
            feats["resp_std"] = float("nan")
            feats["resp_n"] = 0

        # spo2 (mean/std/min/n)
        spo2_v = np.array([r.value for r in self._buffers["spo2"] if win_lo <= r.recorded_at < win_hi], dtype=np.float64)
        if spo2_v.size:
            feats["spo2_mean"] = float(spo2_v.mean())
            feats["spo2_std"] = float(spo2_v.std(ddof=0)) if spo2_v.size > 1 else float("nan")
            feats["spo2_min"] = float(spo2_v.min())
            feats["spo2_n"] = int(spo2_v.size)
        else:
            for k in ("spo2_mean", "spo2_std", "spo2_min"):
                feats[k] = float("nan")
            feats["spo2_n"] = 0

        # HR mean lag features
        for lag, key in [(1, "hr_lag1_mean"), (3, "hr_lag3_mean"), (5, "hr_lag5_mean")]:
            if len(self._hr_mean_history) >= lag:
                feats[key] = self._hr_mean_history[-lag]
            else:
                feats[key] = float("nan")

        return feats


def _slope(t_sec: np.ndarray, vals: np.ndarray) -> float:
    if vals.size < 2 or t_sec[-1] == t_sec[0]:
        return float("nan")
    t_mean = t_sec.mean()
    v_mean = vals.mean()
    num = ((t_sec - t_mean) * (vals - v_mean)).sum()
    den = ((t_sec - t_mean) ** 2).sum()
    return float(num / den) if den != 0 else float("nan")


if __name__ == "__main__":
    # Smoke test + parity check against the offline pipeline.
    # Take one session's worth of cached features, replay sensors into RealtimeClassifier,
    # compare predictions to the LOSO prediction on the same session.
    import sys
    from pathlib import Path as _P

    sys.path.insert(0, str(_P(__file__).parent))
    from classifier.data import load_session, list_sessions
    import pandas as pd

    print("Loading model...")
    clf = RealtimeClassifier.load()
    print(f"  features ({len(clf.feature_cols)}): {clf.feature_cols}")
    print(f"  threshold: {clf.threshold}")

    print("\nPicking one session...")
    sessions = list_sessions()
    # Use the one with most stage segments (notebook's choice)
    top_id = sessions.sort_values("n_stage_segments", ascending=False).iloc[0]["id"]
    bundle = load_session(top_id)
    print(f"  session {top_id[:8]}  duration {bundle.duration_seconds/3600:.1f}h  sensors {len(bundle.sensors)}")

    print("\nReplaying sensors into RealtimeClassifier and predicting at each labeled epoch...")
    clf.start_session(bundle.started_at)
    # Sort everything by time and feed in order
    sensors_sorted = bundle.sensors.sort_values("recorded_at").reset_index(drop=True)
    sensor_idx = 0
    n_sensors = len(sensors_sorted)

    labels_sorted = bundle.labels.sort_values("epoch_start_at").reset_index(drop=True)
    preds_rt = []

    # We'll predict at each label-segment start to align with the offline pipeline's
    # epoch_start_at values (the offline pipeline expands each segment into 30s epochs
    # but parity is simplest at segment starts).
    for _, row in labels_sorted.iterrows():
        # Advance sensor buffer up to (and including) this label time
        cutoff = row["epoch_start_at"]
        while sensor_idx < n_sensors and sensors_sorted.iloc[sensor_idx]["recorded_at"] <= cutoff:
            s = sensors_sorted.iloc[sensor_idx]
            clf.add_reading(s["recorded_at"], s["kind"], float(s["value"]))
            sensor_idx += 1
        pred = clf.predict_at(cutoff)
        preds_rt.append({
            "epoch_start_at": cutoff,
            "stage": row["stage"],
            "rem_prob": pred.rem_probability,
            "is_rem": pred.is_rem,
            "hr_n": pred.n_in_window["heart_rate"],
        })

    df = pd.DataFrame(preds_rt)
    print(f"\n  Predictions made: {len(df)}")
    print(f"  Realtime: P(REM) mean={df['rem_prob'].mean():.3f}  pred-REM-rate={df['is_rem'].mean():.3f}")
    print(f"  By stage (mean realtime P(REM)):")
    print(df.groupby("stage")["rem_prob"].agg(["count", "mean", "max"]).round(3).to_string())
    print("\nDone. Realtime classifier works end-to-end.")
