"""Translate recent HealthKit sensor_readings into a user_state_estimate row.

Reads the last `window_minutes` of `heart_rate`, `hrv`, `sleep_stage` rows
from sensor_readings and computes a transparent heuristic state estimate
(arousal, presence, stage_proba, confidence). v1 is deliberately simple
+ readable — the entry point to fusion, not the fusion itself.

The substrate's existing 1-hour freshness gate filters stale rows
automatically, so writing every 5 min keeps current_user_state live for
Regis throughout the day.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402

logger = logging.getLogger(__name__)

SOURCE_TAG = "body_bridge"
SLEEP_STAGE_VALUES = {"AWAKE", "IN_BED", "CORE", "DEEP", "REM", "UNKNOWN"}
ASLEEP_STAGES = {"CORE", "DEEP", "REM"}
DEFAULT_WINDOW_MINUTES = 15


def estimate_current_state(
    user_id: str,
    *,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    persist: bool = True,
) -> dict[str, Any] | None:
    """Pull recent HealthKit sensor_readings and compute a user_state_estimate.

    Returns the row dict if data was found and a row was written (or would be
    when persist=False); returns None if no recent data exists so the
    substrate's freshness gate gracefully falls back to "no state".
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_minutes)

    try:
        readings = _fetch_readings(user_id=user_id, cutoff=cutoff)
    except Exception as e:
        logger.warning("body_bridge: DB read failed: %s", e)
        return None

    hr_values, hr_latest_at = readings["heart_rate"]
    hrv_values, hrv_latest_at = readings["hrv"]
    sleep_rows, sleep_latest_at = readings["sleep_stage"]

    if not hr_values and not hrv_values and not sleep_rows:
        return None

    latest_at = _max_dt(hr_latest_at, hrv_latest_at, sleep_latest_at) or now
    age_seconds = max(0.0, (now - latest_at).total_seconds())

    arousal = _compute_arousal(hr_values, hrv_values)
    presence = _compute_presence(age_seconds)
    stage_proba = _compute_stage_proba(sleep_rows)
    confidence = _compute_confidence(
        n_hr=len(hr_values),
        n_hrv=len(hrv_values),
        n_sleep=len(sleep_rows),
        age_seconds=age_seconds,
    )

    features = {
        "n_hr": len(hr_values),
        "n_hrv": len(hrv_values),
        "n_sleep": len(sleep_rows),
        "window_minutes": window_minutes,
        "age_seconds": round(age_seconds, 1),
    }
    if hr_values:
        features["hr_mean"] = round(sum(hr_values) / len(hr_values), 2)
        features["hr_min"] = min(hr_values)
        features["hr_max"] = max(hr_values)
    if hrv_values:
        features["hrv_mean"] = round(sum(hrv_values) / len(hrv_values), 2)
    if sleep_rows:
        features["latest_stage"] = sleep_rows[-1]["stage"]

    row = {
        "user_id": user_id,
        "estimated_at": now,
        "stage_proba": stage_proba,
        "arousal": arousal,
        "valence": None,
        "presence": presence,
        "confidence": confidence,
        "source": SOURCE_TAG,
        "features": features,
    }

    if persist:
        try:
            _persist(row)
        except Exception as e:
            logger.warning("body_bridge: persist failed: %s", e)
            return None

    return row


def _fetch_readings(
    *, user_id: str, cutoff: datetime
) -> dict[str, tuple[Any, datetime | None]]:
    """Pull HK-sourced sensor_readings since cutoff.

    Returns a dict keyed by kind. For heart_rate / hrv: (list[float], latest_at).
    For sleep_stage: (list[{stage,start_at,end_at,recorded_at}], latest_at).
    """
    hr_values: list[float] = []
    hr_latest: datetime | None = None
    hrv_values: list[float] = []
    hrv_latest: datetime | None = None
    sleep_rows: list[dict[str, Any]] = []
    sleep_latest: datetime | None = None

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT recorded_at, kind, payload
            FROM sensor_readings
            WHERE user_id = %s
              AND kind IN ('heart_rate', 'hrv', 'sleep_stage')
              AND recorded_at >= %s
            ORDER BY recorded_at ASC
            """,
            (user_id, cutoff),
        )
        for recorded_at, kind, payload in cur.fetchall():
            if not isinstance(payload, dict):
                continue
            if kind == "heart_rate":
                bpm = _coerce_float(payload.get("bpm"))
                if bpm is None:
                    bpm = _coerce_float(payload.get("value"))
                if bpm is not None and bpm > 0:
                    hr_values.append(bpm)
                    hr_latest = recorded_at
            elif kind == "hrv":
                ms = _coerce_float(payload.get("rmssdMs"))
                if ms is None:
                    ms = _coerce_float(payload.get("ms"))
                if ms is None:
                    ms = _coerce_float(payload.get("value"))
                if ms is not None and ms > 0:
                    hrv_values.append(ms)
                    hrv_latest = recorded_at
            elif kind == "sleep_stage":
                stage = str(payload.get("stage") or "").upper()
                if stage in SLEEP_STAGE_VALUES:
                    sleep_rows.append(
                        {
                            "stage": stage,
                            "start_at": payload.get("startAt"),
                            "end_at": payload.get("endAt"),
                            "recorded_at": recorded_at,
                        }
                    )
                    sleep_latest = recorded_at

    return {
        "heart_rate": (hr_values, hr_latest),
        "hrv": (hrv_values, hrv_latest),
        "sleep_stage": (sleep_rows, sleep_latest),
    }


def _compute_arousal(hr_values: list[float], hrv_values: list[float]) -> float | None:
    """Combine HR + HRV into a 0..1 arousal proxy.

    Formula (v1, deliberately transparent):
      hr_norm  = clamp01((hr_mean  - 50) / 50)    # 50 bpm → 0, 100 bpm → 1
      hrv_norm = clamp01((hrv_mean - 20) / 60)    # 20 ms → 0, 80 ms → 1 (higher HRV = calmer)
      arousal  = clamp01(0.5 * hr_norm + 0.5 * (1 - hrv_norm))

    Higher HR pushes arousal up. Higher HRV pulls arousal down (parasympathetic
    tone). When only one signal is present, that side carries full weight.
    Returns None if neither HR nor HRV is available.
    """
    has_hr = bool(hr_values)
    has_hrv = bool(hrv_values)
    if not has_hr and not has_hrv:
        return None

    if has_hr:
        hr_mean = sum(hr_values) / len(hr_values)
        hr_norm = _clamp01((hr_mean - 50.0) / 50.0)
    else:
        hr_norm = None

    if has_hrv:
        hrv_mean = sum(hrv_values) / len(hrv_values)
        hrv_norm = _clamp01((hrv_mean - 20.0) / 60.0)
    else:
        hrv_norm = None

    if hr_norm is not None and hrv_norm is not None:
        arousal = 0.5 * hr_norm + 0.5 * (1.0 - hrv_norm)
    elif hr_norm is not None:
        arousal = hr_norm
    else:
        arousal = 1.0 - (hrv_norm or 0.0)

    return round(_clamp01(arousal), 3)


def _compute_presence(age_seconds: float) -> float:
    """Liveness proxy: how fresh is the most-recent reading?

    1.0 if within 5 min, 0.5 if 5-15 min, 0.0 otherwise.
    """
    if age_seconds <= 5 * 60:
        return 1.0
    if age_seconds <= 15 * 60:
        return 0.5
    return 0.0


def _compute_stage_proba(sleep_rows: list[dict[str, Any]]) -> dict[str, float]:
    """Convert recent sleep_stage rows into a stage probability dict.

    HealthKit uploads sleep_stage events retrospectively — recorded_at reflects
    upload time, but the actual sleep interval lives in payload.startAt/endAt.
    So we only treat a stage as "current" if its endAt is within the last
    30 min; older stages are night-history, not present state.

    If no current sleep_stage rows OR the latest current stage is AWAKE/IN_BED
    → {"awake": 1.0}. Otherwise per-stage proba weighted by row count.
    """
    if not sleep_rows:
        return {"awake": 1.0}

    now = datetime.now(timezone.utc)
    recency_cutoff = now - timedelta(minutes=30)

    current_rows: list[dict[str, Any]] = []
    for r in sleep_rows:
        end_at = _parse_iso_dt(r.get("end_at"))
        if end_at is None or end_at >= recency_cutoff:
            current_rows.append(r)

    if not current_rows:
        return {"awake": 1.0}

    latest_stage = current_rows[-1]["stage"]
    if latest_stage in {"AWAKE", "IN_BED", "UNKNOWN"}:
        return {"awake": 1.0}

    counts: dict[str, int] = {}
    for r in current_rows:
        s = r["stage"]
        if s in ASLEEP_STAGES:
            counts[s.lower()] = counts.get(s.lower(), 0) + 1

    if not counts:
        return {"awake": 1.0}

    total = sum(counts.values())
    proba: dict[str, float] = {
        stage: round(0.9 * (n / total), 3) for stage, n in counts.items()
    }
    proba["awake"] = round(1.0 - sum(proba.values()), 3)
    if proba["awake"] < 0.0:
        proba["awake"] = 0.0
    return proba


def _compute_confidence(
    *, n_hr: int, n_hrv: int, n_sleep: int, age_seconds: float
) -> float:
    """Heuristic confidence: more readings + fresher data → higher.

    Floor of 0.1 when any data at all; full 0.9 ceiling when we have ≥3 HR
    readings + ≥1 HRV + fresh (<5 min). Stale data (>15 min) caps at 0.3.
    """
    if n_hr == 0 and n_hrv == 0 and n_sleep == 0:
        return 0.0

    if age_seconds > 15 * 60:
        return 0.3

    score = 0.2
    if n_hr >= 1:
        score += 0.2
    if n_hr >= 3:
        score += 0.2
    if n_hrv >= 1:
        score += 0.2
    if n_sleep >= 1:
        score += 0.1
    if age_seconds <= 5 * 60:
        score += 0.1

    return round(min(0.9, score), 3)


def _persist(row: dict[str, Any]) -> None:
    """INSERT one user_state_estimate row. Caller handles exceptions."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_state_estimate
                (user_id, session_id, estimated_at, stage_proba,
                 arousal, valence, presence, confidence, source, features)
            VALUES (%s, NULL, %s, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                row["user_id"],
                row["estimated_at"],
                json.dumps(row["stage_proba"]) if row["stage_proba"] is not None else None,
                row["arousal"],
                row["valence"],
                row["presence"],
                row["confidence"],
                row["source"],
                json.dumps(row["features"]),
            ),
        )
        conn.commit()


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _coerce_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _max_dt(*values: datetime | None) -> datetime | None:
    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


def _parse_iso_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="body_bridge.estimator",
        description="Translate recent HealthKit sensor_readings into a user_state_estimate row.",
    )
    parser.add_argument(
        "--user-id",
        default="61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
        help="user_id to compute state for (default: Aakash)",
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=DEFAULT_WINDOW_MINUTES,
        help=f"lookback window in minutes (default: {DEFAULT_WINDOW_MINUTES})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute state but don't write to user_state_estimate",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    row = estimate_current_state(
        user_id=args.user_id,
        window_minutes=args.window_minutes,
        persist=not args.dry_run,
    )
    if row is None:
        print("body_bridge: no recent sensor_readings — no row written.")
        return 0

    printable = {**row, "estimated_at": row["estimated_at"].isoformat()}
    print(json.dumps(printable, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
