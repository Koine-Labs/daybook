"""Pull relevant slices of health data for a chat query.

v0 heuristic — keyword routing into a handful of compact text summaries.
Each section is capped near 500 chars; concise wins over completeness.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import mean

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402


SLEEP_WORDS = {"sleep", "slept", "rest", "rested", "night", "tired", "rem",
                "dream", "dreamt", "dreamed", "dreams", "nap", "napped",
                "wake", "woke", "insomnia", "bed"}
HR_WORDS = {"heart", "hr", "pulse", "stress", "stressed", "anxious",
            "calm", "calmness", "bpm", "rate"}
HRV_WORDS = {"hrv", "variability", "recovery", "nervous", "system"}
BREATH_WORDS = {"breath", "breathing", "respiratory", "breathe", "respiration"}


def summarize_health_for_query(
    query: str, *, user_id: str, days: int = 7
) -> str:
    """Return relevant health context ONLY if the query asks for it.

    Regis is a general partner; he doesn't volunteer biometric stats every turn.
    Returns an empty string when no keywords match — the handler then skips the
    health-data section entirely.
    """
    q = query.lower()
    sections: list[str] = []

    if _any(q, SLEEP_WORDS):
        sections.append(_format_sleep(user_id, days))
    if _any(q, HR_WORDS):
        sections.append(_format_hr(user_id, days))
    if _any(q, HRV_WORDS):
        sections.append(_format_hrv(user_id, days))
    if _any(q, BREATH_WORDS):
        sections.append(_format_respiratory(user_id, days))

    return "\n\n".join(s for s in sections if s)


def _any(text: str, words: set[str]) -> bool:
    return any(w in text for w in words)


def _format_sleep(user_id: str, days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, started_at, ended_at, duration_seconds
            FROM sleep_sessions
            WHERE user_id = %s AND started_at >= %s
            ORDER BY started_at DESC
            """,
            (user_id, cutoff),
        )
        sessions = cur.fetchall()

        if not sessions:
            return f"Sleep last {days} days: no sessions on record."

        session_ids = [s[0] for s in sessions]
        cur.execute(
            """
            SELECT session_id, stage
            FROM sleep_stage_classifications
            WHERE session_id = ANY(%s)
            """,
            (session_ids,),
        )
        stage_rows = cur.fetchall()

    durations_h = [s[3] / 3600.0 for s in sessions]
    avg_h = mean(durations_h) if durations_h else 0.0
    short_nights = [s for s in sessions if s[3] < 6 * 3600]

    stage_counts: Counter[str] = Counter(r[1] for r in stage_rows)
    total_epochs = sum(stage_counts.values()) or 1
    stage_pct = {k: 100.0 * v / total_epochs for k, v in stage_counts.items()}

    latest = sessions[0]
    latest_h = latest[3] / 3600.0
    latest_date = latest[1].strftime("%Y-%m-%d")
    latest_session_id = latest[0]
    latest_stage_rows = [r for r in stage_rows if r[0] == latest_session_id]
    latest_stage_counts: Counter[str] = Counter(r[1] for r in latest_stage_rows)
    latest_total = sum(latest_stage_counts.values()) or 1
    latest_rem_pct = 100.0 * latest_stage_counts.get("REM", 0) / latest_total

    short_dates = ", ".join(s[1].strftime("%a") for s in short_nights) or "none"
    stage_summary = ", ".join(
        f"{int(round(stage_pct.get(s, 0)))}% {s}"
        for s in ("REM", "CORE", "DEEP", "AWAKE")
        if stage_pct.get(s, 0) > 0
    )

    return (
        f"Sleep last {days} days:\n"
        f"  Sessions: {len(sessions)}\n"
        f"  Avg duration: {avg_h:.1f}h (target 7.5h)\n"
        f"  Nights below 6h: {len(short_nights)} ({short_dates})\n"
        f"  Stage distribution: {stage_summary or 'unknown'}\n"
        f"  Latest night ({latest_date}): {latest_h:.1f}h, "
        f"{latest_rem_pct:.0f}% REM"
    )


def _format_hr(user_id: str, days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              AVG((payload->>'bpm')::float) AS avg_bpm,
              MIN((payload->>'bpm')::float) AS min_bpm,
              MAX((payload->>'bpm')::float) AS max_bpm,
              COUNT(*) AS n
            FROM sensor_readings
            WHERE user_id = %s
              AND kind = 'heart_rate'
              AND recorded_at >= %s
            """,
            (user_id, cutoff),
        )
        row = cur.fetchone()

    if not row or row[3] == 0:
        return f"Heart rate last {days} days: no samples on record."

    avg_bpm, min_bpm, max_bpm, n = row
    return (
        f"Heart rate last {days} days:\n"
        f"  Samples: {n:,}\n"
        f"  Avg: {avg_bpm:.0f} bpm  (range {min_bpm:.0f}-{max_bpm:.0f})"
    )


def _format_hrv(user_id: str, days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              AVG((payload->>'sdnn_ms')::float) AS avg_sdnn,
              MIN((payload->>'sdnn_ms')::float) AS min_sdnn,
              MAX((payload->>'sdnn_ms')::float) AS max_sdnn,
              COUNT(*) AS n
            FROM sensor_readings
            WHERE user_id = %s
              AND kind = 'hrv'
              AND recorded_at >= %s
            """,
            (user_id, cutoff),
        )
        row = cur.fetchone()

    if not row or not row[3]:
        return ""

    avg_sdnn, min_sdnn, max_sdnn, n = row
    if avg_sdnn is None:
        return ""
    return (
        f"Heart rate variability last {days} days:\n"
        f"  Samples: {n:,}\n"
        f"  Avg SDNN: {avg_sdnn:.0f} ms (range {min_sdnn:.0f}-{max_sdnn:.0f})"
    )


def _format_respiratory(user_id: str, days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              AVG((payload->>'breaths_per_min')::float) AS avg_br,
              COUNT(*) AS n
            FROM sensor_readings
            WHERE user_id = %s
              AND kind = 'respiratory_rate'
              AND recorded_at >= %s
            """,
            (user_id, cutoff),
        )
        row = cur.fetchone()

    if not row or not row[1] or row[0] is None:
        return ""
    avg_br, n = row
    return (
        f"Respiratory rate last {days} days:\n"
        f"  Samples: {n}\n"
        f"  Avg: {avg_br:.1f} breaths/min"
    )


def _default_snapshot(user_id: str, days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*), MAX(started_at) FROM sleep_sessions "
            "WHERE user_id = %s AND started_at >= %s",
            (user_id, cutoff),
        )
        n_sessions, latest = cur.fetchone()
        cur.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE user_id = %s AND recorded_at >= %s",
            (user_id, cutoff),
        )
        n_readings = cur.fetchone()[0]

    latest_iso = latest.strftime("%Y-%m-%d") if latest else "n/a"
    return (
        f"Overall last {days} days:\n"
        f"  Sleep sessions on record: {n_sessions}\n"
        f"  Latest session: {latest_iso}\n"
        f"  Sensor samples on record: {n_readings:,}"
    )
