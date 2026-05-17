from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402


DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

CACHE_DIR = Path(__file__).parent / "cache"

_PAYLOAD_FIELD = {
    "heart_rate": "bpm",
    "hrv": "rmssdMs",
    "respiratory_rate": "breathsPerMinute",
    "spo2": "percent",
}


@dataclass
class SessionBundle:
    session_id: str
    user_id: str
    started_at: pd.Timestamp
    ended_at: pd.Timestamp
    duration_seconds: int
    sensors: pd.DataFrame
    labels: pd.DataFrame


def list_sessions(
    user_id: str = DEFAULT_USER_ID,
    min_duration_seconds: int = 4 * 3600,
    min_stage_segments: int = 6,
    min_hr_readings: int = 30,
) -> pd.DataFrame:
    sql = """
    WITH base AS (
        SELECT
            s.id,
            s.user_id,
            s.started_at,
            s.ended_at,
            s.duration_seconds,
            (
                SELECT COUNT(*) FROM sleep_stage_classifications c
                WHERE c.session_id = s.id
            ) AS n_stage_segments,
            (
                SELECT COUNT(*) FROM sensor_readings sr
                WHERE sr.user_id = s.user_id
                  AND sr.kind = 'heart_rate'
                  AND sr.recorded_at >= s.started_at
                  AND sr.recorded_at <  s.ended_at
            ) AS n_hr_readings
        FROM sleep_sessions s
        WHERE s.user_id = %s
          AND s.duration_seconds >= %s
    )
    SELECT id, user_id, started_at, ended_at, duration_seconds,
           n_stage_segments, n_hr_readings
    FROM base
    WHERE n_stage_segments >= %s
      AND n_hr_readings   >= %s
    ORDER BY started_at;
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            sql,
            (user_id, min_duration_seconds, min_stage_segments, min_hr_readings),
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]

    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        df["id"] = df["id"].astype(str)
        df["user_id"] = df["user_id"].astype(str)
    return df


def _extract_value(kind: str, payload: dict[str, Any]) -> float | None:
    field = _PAYLOAD_FIELD.get(kind)
    if field is None or payload is None:
        return None
    val = payload.get(field)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fetch_session_row(session_id: str) -> dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_id, started_at, ended_at, duration_seconds
            FROM sleep_sessions WHERE id = %s
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"session_id not found: {session_id}")
        cols = [d.name for d in cur.description]
    return dict(zip(cols, row))


def _fetch_sensors(
    user_id: str, started_at: pd.Timestamp, ended_at: pd.Timestamp
) -> pd.DataFrame:
    sql = """
    SELECT recorded_at, kind, payload
    FROM sensor_readings
    WHERE user_id = %s
      AND kind IN ('heart_rate', 'hrv', 'respiratory_rate', 'spo2')
      AND recorded_at >= %s
      AND recorded_at <  %s
    ORDER BY recorded_at
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, (user_id, started_at, ended_at))
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["recorded_at", "kind", "value"])
    df = pd.DataFrame(rows, columns=["recorded_at", "kind", "payload"])
    df["value"] = [
        _extract_value(k, p) for k, p in zip(df["kind"], df["payload"])
    ]
    df = df.drop(columns=["payload"])
    df = df.dropna(subset=["value"]).reset_index(drop=True)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
    return df


def _fetch_labels(session_id: str) -> pd.DataFrame:
    sql = """
    SELECT epoch_start_at, stage
    FROM sleep_stage_classifications
    WHERE session_id = %s
    ORDER BY epoch_start_at
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, (session_id,))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["epoch_start_at", "stage"])
    if not df.empty:
        df["epoch_start_at"] = pd.to_datetime(df["epoch_start_at"], utc=True)
        df["stage"] = df["stage"].astype(str)
    return df


def load_session(session_id: str) -> SessionBundle:
    meta = _fetch_session_row(session_id)
    started_at = pd.Timestamp(meta["started_at"]).tz_convert("UTC")
    ended_at = pd.Timestamp(meta["ended_at"]).tz_convert("UTC")
    sensors = _fetch_sensors(str(meta["user_id"]), started_at, ended_at)
    labels = _fetch_labels(session_id)
    return SessionBundle(
        session_id=str(meta["id"]),
        user_id=str(meta["user_id"]),
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=int(meta["duration_seconds"]),
        sensors=sensors,
        labels=labels,
    )


def _cache_paths(session_id: str) -> tuple[Path, Path, Path]:
    base = CACHE_DIR / session_id
    return base / "meta.parquet", base / "sensors.parquet", base / "labels.parquet"


def _save_cache(bundle: SessionBundle) -> None:
    meta_p, sensors_p, labels_p = _cache_paths(bundle.session_id)
    meta_p.parent.mkdir(parents=True, exist_ok=True)
    meta_df = pd.DataFrame(
        [{
            "session_id": bundle.session_id,
            "user_id": bundle.user_id,
            "started_at": bundle.started_at,
            "ended_at": bundle.ended_at,
            "duration_seconds": bundle.duration_seconds,
        }]
    )
    meta_df.to_parquet(meta_p, index=False)
    bundle.sensors.to_parquet(sensors_p, index=False)
    bundle.labels.to_parquet(labels_p, index=False)


def _load_cache(session_id: str) -> SessionBundle | None:
    meta_p, sensors_p, labels_p = _cache_paths(session_id)
    if not (meta_p.exists() and sensors_p.exists() and labels_p.exists()):
        return None
    meta = pd.read_parquet(meta_p).iloc[0].to_dict()
    sensors = pd.read_parquet(sensors_p)
    labels = pd.read_parquet(labels_p)
    if not sensors.empty:
        sensors["recorded_at"] = pd.to_datetime(sensors["recorded_at"], utc=True)
    if not labels.empty:
        labels["epoch_start_at"] = pd.to_datetime(labels["epoch_start_at"], utc=True)
    return SessionBundle(
        session_id=str(meta["session_id"]),
        user_id=str(meta["user_id"]),
        started_at=pd.Timestamp(meta["started_at"]).tz_convert("UTC"),
        ended_at=pd.Timestamp(meta["ended_at"]).tz_convert("UTC"),
        duration_seconds=int(meta["duration_seconds"]),
        sensors=sensors,
        labels=labels,
    )


def load_sessions(session_ids: list[str], use_cache: bool = True) -> list[SessionBundle]:
    out: list[SessionBundle] = []
    for sid in session_ids:
        bundle: SessionBundle | None = None
        if use_cache:
            bundle = _load_cache(sid)
        if bundle is None:
            bundle = load_session(sid)
            if use_cache:
                _save_cache(bundle)
        out.append(bundle)
    return out
