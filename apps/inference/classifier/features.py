from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

try:
    from .data import SessionBundle
except ImportError:
    from data import SessionBundle  # type: ignore[no-redef]


def expand_labels_to_epochs(
    labels: pd.DataFrame,
    session_end: pd.Timestamp,
    epoch_seconds: int = 30,
) -> pd.DataFrame:
    if labels.empty:
        return pd.DataFrame(columns=["epoch_start_at", "epoch_end_at", "stage"])

    labels = labels.sort_values("epoch_start_at").reset_index(drop=True)
    segment_starts = labels["epoch_start_at"].tolist()
    stages = labels["stage"].tolist()
    segment_ends = segment_starts[1:] + [session_end]

    step = pd.Timedelta(seconds=epoch_seconds)
    rows: list[dict[str, Any]] = []
    for seg_start, seg_end, stage in zip(segment_starts, segment_ends, stages):
        if seg_end <= seg_start:
            continue
        t = seg_start
        while t < seg_end:
            rows.append(
                {
                    "epoch_start_at": t,
                    "epoch_end_at": t + step,
                    "stage": stage,
                }
            )
            t = t + step
    out = pd.DataFrame(rows, columns=["epoch_start_at", "epoch_end_at", "stage"])
    if not out.empty:
        out["epoch_start_at"] = pd.to_datetime(out["epoch_start_at"], utc=True)
        out["epoch_end_at"] = pd.to_datetime(out["epoch_end_at"], utc=True)
    return out


def _kind_arrays(sensors: pd.DataFrame, kind: str) -> tuple[np.ndarray, np.ndarray]:
    sub = sensors[sensors["kind"] == kind]
    if sub.empty:
        return np.empty(0, dtype="int64"), np.empty(0, dtype="float64")
    sub = sub.sort_values("recorded_at")
    ts = sub["recorded_at"].to_numpy(dtype="datetime64[ns]").astype("int64")
    vals = sub["value"].to_numpy(dtype="float64")
    return ts, vals


def _window_slice(
    ts_ns: np.ndarray, vals: np.ndarray, lo_ns: int, hi_ns: int
) -> np.ndarray:
    if ts_ns.size == 0:
        return np.empty(0, dtype="float64")
    lo = np.searchsorted(ts_ns, lo_ns, side="left")
    hi = np.searchsorted(ts_ns, hi_ns, side="left")
    return vals[lo:hi]


def _window_with_ts(
    ts_ns: np.ndarray, vals: np.ndarray, lo_ns: int, hi_ns: int
) -> tuple[np.ndarray, np.ndarray]:
    if ts_ns.size == 0:
        return np.empty(0, dtype="int64"), np.empty(0, dtype="float64")
    lo = np.searchsorted(ts_ns, lo_ns, side="left")
    hi = np.searchsorted(ts_ns, hi_ns, side="left")
    return ts_ns[lo:hi], vals[lo:hi]


def _safe(fn, arr: np.ndarray) -> float:
    if arr.size == 0:
        return float("nan")
    return float(fn(arr))


def _slope(ts_ns: np.ndarray, vals: np.ndarray) -> float:
    n = vals.size
    if n < 2:
        return float("nan")
    t_sec = (ts_ns - ts_ns[0]).astype("float64") / 1e9
    if t_sec[-1] == t_sec[0]:
        return float("nan")
    t_mean = t_sec.mean()
    v_mean = vals.mean()
    num = ((t_sec - t_mean) * (vals - v_mean)).sum()
    den = ((t_sec - t_mean) ** 2).sum()
    if den == 0:
        return float("nan")
    return float(num / den)


def compute_session_features(
    bundle: SessionBundle,
    epoch_seconds: int = 30,
    context_seconds: int = 300,
) -> pd.DataFrame:
    epochs = expand_labels_to_epochs(bundle.labels, bundle.ended_at, epoch_seconds)
    if epochs.empty:
        return pd.DataFrame()

    hr_ts, hr_vals = _kind_arrays(bundle.sensors, "heart_rate")
    hrv_ts, hrv_vals = _kind_arrays(bundle.sensors, "hrv")
    resp_ts, resp_vals = _kind_arrays(bundle.sensors, "respiratory_rate")
    spo2_ts, spo2_vals = _kind_arrays(bundle.sensors, "spo2")

    hr_session_median = float(np.median(hr_vals)) if hr_vals.size else float("nan")

    session_start_ns = int(
        np.datetime64(bundle.started_at.tz_convert("UTC").to_datetime64()).astype(
            "int64"
        )
    )
    session_end_ns = int(
        np.datetime64(bundle.ended_at.tz_convert("UTC").to_datetime64()).astype(
            "int64"
        )
    )
    session_span_ns = max(1, session_end_ns - session_start_ns)

    epoch_start_ns = (
        epochs["epoch_start_at"]
        .to_numpy(dtype="datetime64[ns]")
        .astype("int64")
    )
    context_ns = int(context_seconds) * 1_000_000_000
    epoch_ns = int(epoch_seconds) * 1_000_000_000

    rows: list[dict[str, Any]] = []
    hr_means_history: list[float] = []

    for i, e_ns in enumerate(epoch_start_ns):
        lo = e_ns - context_ns
        hi = e_ns + epoch_ns

        hr_w_ts, hr_w = _window_with_ts(hr_ts, hr_vals, lo, hi)
        hrv_w = _window_slice(hrv_ts, hrv_vals, lo, hi)
        resp_w = _window_slice(resp_ts, resp_vals, lo, hi)
        spo2_w = _window_slice(spo2_ts, spo2_vals, lo, hi)

        if hr_w.size:
            hr_mean = float(hr_w.mean())
            hr_std = float(hr_w.std(ddof=0)) if hr_w.size > 1 else float("nan")
            hr_min = float(hr_w.min())
            hr_max = float(hr_w.max())
            hr_range = hr_max - hr_min
            hr_median = float(np.median(hr_w))
            hr_slope = _slope(hr_w_ts, hr_w)
            hr_n = int(hr_w.size)
            if not np.isnan(hr_session_median):
                hr_pct_above_baseline = float((hr_w > hr_session_median).mean())
            else:
                hr_pct_above_baseline = float("nan")
        else:
            hr_mean = hr_std = hr_min = hr_max = hr_range = hr_median = hr_slope = (
                float("nan")
            )
            hr_n = 0
            hr_pct_above_baseline = float("nan")

        time_of_night_frac = float((e_ns - session_start_ns) / session_span_ns)
        ts_local = epochs["epoch_start_at"].iloc[i]
        hour = ts_local.hour + ts_local.minute / 60.0
        hour_of_day_sin = float(np.sin(2 * np.pi * hour / 24.0))
        hour_of_day_cos = float(np.cos(2 * np.pi * hour / 24.0))
        day_of_week = int(ts_local.dayofweek)
        is_weekend = int(day_of_week >= 5)

        def lag(k: int) -> float:
            idx = i - k
            if idx < 0:
                return float("nan")
            return hr_means_history[idx]

        rows.append(
            {
                "session_id": bundle.session_id,
                "epoch_start_at": epochs["epoch_start_at"].iloc[i],
                "stage": epochs["stage"].iloc[i],
                "hr_mean": hr_mean,
                "hr_std": hr_std,
                "hr_min": hr_min,
                "hr_max": hr_max,
                "hr_range": hr_range,
                "hr_median": hr_median,
                "hr_slope": hr_slope,
                "hr_n": hr_n,
                "hr_pct_above_baseline": hr_pct_above_baseline,
                "hrv_mean": _safe(np.mean, hrv_w),
                "hrv_std": float(hrv_w.std(ddof=0)) if hrv_w.size > 1 else float("nan"),
                "hrv_min": _safe(np.min, hrv_w),
                "hrv_max": _safe(np.max, hrv_w),
                "hrv_n": int(hrv_w.size),
                "resp_mean": _safe(np.mean, resp_w),
                "resp_std": float(resp_w.std(ddof=0)) if resp_w.size > 1 else float("nan"),
                "resp_n": int(resp_w.size),
                "spo2_mean": _safe(np.mean, spo2_w),
                "spo2_std": float(spo2_w.std(ddof=0)) if spo2_w.size > 1 else float("nan"),
                "spo2_min": _safe(np.min, spo2_w),
                "spo2_n": int(spo2_w.size),
                "time_of_night_frac": time_of_night_frac,
                "hour_of_day_sin": hour_of_day_sin,
                "hour_of_day_cos": hour_of_day_cos,
                "day_of_week": day_of_week,
                "is_weekend": is_weekend,
                "hr_lag1_mean": lag(1),
                "hr_lag3_mean": lag(3),
                "hr_lag5_mean": lag(5),
            }
        )
        hr_means_history.append(hr_mean)

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out[out["stage"] != "UNKNOWN"].reset_index(drop=True)
    return out


def compute_all_features(
    bundles: list[SessionBundle],
    epoch_seconds: int = 30,
    context_seconds: int = 300,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    total = len(bundles)
    for i, b in enumerate(bundles, 1):
        t0 = time.monotonic()
        df = compute_session_features(b, epoch_seconds, context_seconds)
        dt = time.monotonic() - t0
        print(f"[{i}/{total}] {b.session_id} epochs={len(df)} in {dt:.2f}s")
        parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


if __name__ == "__main__":
    try:
        from .data import list_sessions, load_session
    except ImportError:
        from data import list_sessions, load_session  # type: ignore[no-redef]

    print("=== Listing eligible sessions ===")
    sessions = list_sessions()
    print(f"Eligible sessions: {len(sessions)}")
    print(sessions.head())

    print("\n=== Loading top session by stage segments ===")
    top = sessions.sort_values("n_stage_segments", ascending=False).iloc[0]
    print(
        f"session_id={top['id']}  duration={top['duration_seconds']/3600:.1f}h"
        f"  segs={top['n_stage_segments']}  hr={top['n_hr_readings']}"
    )
    bundle = load_session(top["id"])
    print(f"  sensors df shape: {bundle.sensors.shape}")
    print(f"  sensors kinds: {bundle.sensors['kind'].value_counts().to_dict()}")
    print(f"  labels df shape: {bundle.labels.shape}")

    print("\n=== Expanding labels to epochs ===")
    epochs = expand_labels_to_epochs(bundle.labels, bundle.ended_at)
    print(f"  epochs shape: {epochs.shape}")
    print(f"  stage counts: {epochs['stage'].value_counts().to_dict()}")

    print("\n=== Computing features for top session ===")
    t0 = time.monotonic()
    feats = compute_session_features(bundle)
    dt = time.monotonic() - t0
    print(f"  features shape: {feats.shape} in {dt:.2f}s")
    print(f"  columns: {list(feats.columns)}")
    print(
        f"  stage label distribution after dropping UNKNOWN:"
        f" {feats['stage'].value_counts().to_dict()}"
    )
    print(f"  highest-NaN-rate features (top 10):")
    print(
        (feats.isnull().mean() * 100)
        .sort_values(ascending=False)
        .head(10)
        .round(1)
        .to_string()
    )
