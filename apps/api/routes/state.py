"""State routes — iOS HealthKit ingest + body summary read-back (#13).

The phone reads HealthKit (HRV, HR, sleep, temperature), batches readings
and POSTs them to /state/sensor_readings. Now's BODY whisper + Self's
BodyAurora then pull from /state/body and /state/body/series respectively.

Notes:
- We append-only to the existing `sensor_readings` table (migration 0001).
  No schema change required for this issue.
- The whisper line is composed by a tiny rule-based function. We could
  later upgrade to a generative composer call, but keeping it
  deterministic for now means body-line behavior is predictable.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from json import dumps as json_dumps
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api import _paths  # noqa: F401 -- bootstraps sys.path before db import
from api.deps import current_user_id, get_db_conn
from api.schemas import (
    BodySeriesPoint,
    BodySeriesResponse,
    BodySummary,
    SensorIngestResponse,
    SensorReadingsBatch,
)

router = APIRouter(prefix="/state", tags=["state"])


# Server-side cap matching the iOS-side batch ceiling so a misbehaving
# client can't dump unbounded inserts in one call.
_MAX_BATCH = 200

# Kinds we know how to interpret. Anything else gets rejected silently
# (counted in `rejected`).
_KNOWN_KINDS = {"heart_rate", "hrv", "sleep_stage", "temperature"}


@router.post("/sensor_readings", response_model=SensorIngestResponse)
def ingest_readings(
    body: SensorReadingsBatch,
    user_id: str = Depends(current_user_id),
    conn=Depends(get_db_conn),
) -> SensorIngestResponse:
    """Insert a batch of HealthKit readings into `sensor_readings`."""
    if not body.readings:
        return SensorIngestResponse(inserted=0, rejected=0, last_recorded_at=None)

    if len(body.readings) > _MAX_BATCH:
        raise HTTPException(
            status_code=413,
            detail=f"Batch too large: {len(body.readings)} > {_MAX_BATCH}",
        )

    rows: list[tuple[str, datetime, str, str, str]] = []
    rejected = 0
    latest: datetime | None = None

    for r in body.readings:
        if r.kind not in _KNOWN_KINDS:
            rejected += 1
            continue
        if not isinstance(r.payload, dict) or not r.payload:
            rejected += 1
            continue
        rows.append((user_id, r.recorded_at, r.source, r.kind, json_dumps(r.payload)))
        if latest is None or r.recorded_at > latest:
            latest = r.recorded_at

    if not rows:
        return SensorIngestResponse(inserted=0, rejected=rejected, last_recorded_at=None)

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO sensor_readings (user_id, recorded_at, source, kind, payload)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            rows,
        )
    conn.commit()

    return SensorIngestResponse(
        inserted=len(rows),
        rejected=rejected,
        last_recorded_at=latest,
    )


@router.get("/body", response_model=BodySummary)
def body_summary(
    user_id: str = Depends(current_user_id),
    conn=Depends(get_db_conn),
) -> BodySummary:
    """One-shot body picture: HRV avg, resting HR, latest sleep, whisper line."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    hrv_avg: float | None = None
    hr_resting: int | None = None
    last_sleep_minutes: int | None = None
    last_sleep_ended: datetime | None = None
    readings_24h = 0

    with conn.cursor() as cur:
        # HRV avg (ms) over last 24h. Both rmssdMs (legacy HK import) and
        # value/ms keys are accepted to keep historical data usable.
        cur.execute(
            """
            SELECT AVG(COALESCE(
                (payload->>'rmssdMs')::float,
                (payload->>'ms')::float,
                (payload->>'value')::float
            ))
            FROM sensor_readings
            WHERE user_id = %s AND kind = 'hrv' AND recorded_at >= %s
            """,
            (user_id, cutoff),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            hrv_avg = float(row[0])

        # Resting HR proxy: 10th-percentile HR over the last 24h. Cheap
        # and decent without needing actual restingHeartRate samples.
        cur.execute(
            """
            SELECT percentile_cont(0.1) WITHIN GROUP (
                ORDER BY COALESCE(
                    (payload->>'bpm')::float,
                    (payload->>'value')::float
                )
            )
            FROM sensor_readings
            WHERE user_id = %s AND kind = 'heart_rate' AND recorded_at >= %s
              AND COALESCE(
                  (payload->>'bpm')::float,
                  (payload->>'value')::float
              ) IS NOT NULL
            """,
            (user_id, cutoff),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            hr_resting = int(round(float(row[0])))

        # Count of readings in window (gives a "we're awake" liveness hint).
        cur.execute(
            """
            SELECT COUNT(*)
            FROM sensor_readings
            WHERE user_id = %s AND recorded_at >= %s
            """,
            (user_id, cutoff),
        )
        row = cur.fetchone()
        readings_24h = int(row[0]) if row else 0

        # Last sleep — prefer the legacy `sleep_sessions` table (populated by
        # parse_apple_health.py), but fall back to rolling up recent
        # `sleep_stage` rows from `sensor_readings` so live HealthKit uploads
        # produce a sleep line too. Without this fallback the live pipeline
        # would silently never compose "you slept Xh Ym" once the historical
        # import ages out.
        cur.execute(
            """
            SELECT duration_seconds, ended_at
            FROM sleep_sessions
            WHERE user_id = %s
            ORDER BY ended_at DESC NULLS LAST, started_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            last_sleep_minutes = int(row[0]) // 60
            last_sleep_ended = row[1]
        else:
            # Live-data fallback: sum durations of recent non-awake sleep
            # stages. Window of 18h covers a normal night plus naps without
            # picking up the previous calendar day's session.
            cur.execute(
                """
                SELECT
                    SUM(EXTRACT(EPOCH FROM (
                        (payload->>'endAt')::timestamptz
                        - (payload->>'startAt')::timestamptz
                    ))) AS sleep_seconds,
                    MAX((payload->>'endAt')::timestamptz) AS latest_end
                FROM sensor_readings
                WHERE user_id = %s
                  AND kind = 'sleep_stage'
                  AND recorded_at >= NOW() - INTERVAL '18 hours'
                  AND payload->>'stage' NOT IN ('AWAKE', 'IN_BED', 'UNKNOWN')
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row and row[0] is not None and float(row[0]) > 0:
                last_sleep_minutes = int(float(row[0]) // 60)
                last_sleep_ended = row[1]

    line = _compose_body_line(
        hrv_avg=hrv_avg,
        hr_resting=hr_resting,
        last_sleep_minutes=last_sleep_minutes,
    )

    return BodySummary(
        line=line,
        hrv_avg_ms=hrv_avg,
        hr_resting_bpm=hr_resting,
        last_sleep_duration_minutes=last_sleep_minutes,
        last_sleep_ended_at=last_sleep_ended,
        readings_last_24h=readings_24h,
        generated_at=now,
    )


@router.get("/body/series", response_model=BodySeriesResponse)
def body_series(
    days: int = Query(default=7, ge=1, le=30),
    user_id: str = Depends(current_user_id),
    conn=Depends(get_db_conn),
) -> BodySeriesResponse:
    """Per-UTC-day series: HRV avg, HR avg, sleep minutes for the last N days."""
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = now - timedelta(days=days - 1)

    # Build a complete day list so callers can iterate without gaps.
    day_keys: list[str] = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]

    hrv_by_day: dict[str, float] = {}
    hr_by_day: dict[str, float] = {}
    sleep_by_day: dict[str, int] = {}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT to_char(recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
                   AVG(COALESCE(
                       (payload->>'rmssdMs')::float,
                       (payload->>'ms')::float,
                       (payload->>'value')::float
                   ))
            FROM sensor_readings
            WHERE user_id = %s AND kind = 'hrv' AND recorded_at >= %s
            GROUP BY day
            """,
            (user_id, start),
        )
        for d, avg in cur.fetchall():
            if avg is not None:
                hrv_by_day[d] = float(avg)

        cur.execute(
            """
            SELECT to_char(recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
                   AVG(COALESCE(
                       (payload->>'bpm')::float,
                       (payload->>'value')::float
                   ))
            FROM sensor_readings
            WHERE user_id = %s AND kind = 'heart_rate' AND recorded_at >= %s
            GROUP BY day
            """,
            (user_id, start),
        )
        for d, avg in cur.fetchall():
            if avg is not None:
                hr_by_day[d] = float(avg)

        cur.execute(
            """
            SELECT to_char(started_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
                   SUM(duration_seconds)
            FROM sleep_sessions
            WHERE user_id = %s AND started_at >= %s
            GROUP BY day
            """,
            (user_id, start),
        )
        for d, total_sec in cur.fetchall():
            if total_sec is not None:
                sleep_by_day[d] = int(total_sec) // 60

    points = [
        BodySeriesPoint(
            day=d,
            hrv_avg_ms=hrv_by_day.get(d),
            hr_avg_bpm=hr_by_day.get(d),
            sleep_minutes=sleep_by_day.get(d),
        )
        for d in day_keys
    ]

    return BodySeriesResponse(days=days, points=points)


# ---------------------------------------------------------------------------
# Whisper-line composer (deterministic, rule-based)
# ---------------------------------------------------------------------------


def _compose_body_line(
    *,
    hrv_avg: float | None,
    hr_resting: int | None,
    last_sleep_minutes: int | None,
) -> str | None:
    """Tiny rule-based composer. Returns None if there's nothing to say.

    NOTE — this is a deliberate, scoped departure from commitment #8
    ("Generative Regis from day one"). The body whisper is polled every ~5
    minutes from the iOS app, so dropping a Codex call here would burn
    tokens + add latency on every refresh for a near-static surface. Acceptable
    while the line is purely descriptive ("hrv steady. you slept 6h 41m.").

    TODO(#8): when retrieval context is rich enough that the line could
    actually drift in Regis's voice (e.g., "you barely slept. again."),
    swap to `from wisp.composer import compose_utterance` with
    `moment_kind="body_check"` and a passed-in retrieval slice. Until then
    this stays deterministic so it can't burn cycles on no-news days.
    """
    parts: list[str] = []

    hrv_phrase = _classify_hrv(hrv_avg)
    if hrv_phrase is not None:
        parts.append(hrv_phrase)
    elif hr_resting is not None:
        parts.append(f"resting {_classify_hr(hr_resting)}")

    if last_sleep_minutes is not None:
        parts.append(f"you slept {_format_sleep(last_sleep_minutes)}")

    if not parts:
        return None

    return ". ".join(parts) + "."


def _classify_hrv(ms: float | None) -> str | None:
    """Map HRV (RMSSD-ish ms) to a single-word descriptor."""
    if ms is None:
        return None
    if ms < 25:
        return "hrv soft"
    if ms < 50:
        return "hrv steady"
    return "hrv lively"


def _classify_hr(bpm: int) -> str:
    if bpm < 55:
        return "calm"
    if bpm < 70:
        return "steady"
    return "warm"


def _format_sleep(minutes: int) -> str:
    h, m = divmod(max(0, minutes), 60)
    if h == 0:
        return f"{m}m"
    return f"{h}h {m}m"
