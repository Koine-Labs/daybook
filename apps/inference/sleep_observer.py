"""After each sleep session, summarize the night into Regis-flavored observations.

The session post-mortem feeds the LLM:
  - session metadata (start, end, duration)
  - sleep_stage_classifications (Apple labels: AWAKE/REM/CORE/DEEP)
  - sensor aggregates (HR mean/std, HRV samples, resp rate)
  - user_state_estimate rows (if any)
  - dream_recalls from the morning after (if any)
  - regis_moments / cue_events during the session
  - intent_set the evening before

Output: 1-5 short observations Regis would remember. Persisted to
regis_observations + embedded for future retrieval.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_conn  # noqa: E402
from embeddings import embed_and_store  # noqa: E402
from imodels import log_novelty_observation  # noqa: E402
from llm import ChatClient  # noqa: E402

logger = logging.getLogger(__name__)


class SessionObservations(BaseModel):
    """LLM schema: 1-5 short notes Regis would remember about a sleep night."""

    model_config = ConfigDict(extra="forbid")

    observations: list[str] = Field(
        description="1-5 short notes Regis would remember about this sleep session"
    )


OBSERVER_SYSTEM = (
    "You are Regis's memory layer for sleep observations. "
    "You read a structured night summary and extract a SHORT LIST of noteworthy patterns "
    "the user's personal companion would want to remember about them. "
    "Be terse, specific, and pattern-oriented. Each note is 1-2 sentences. "
    "Do NOT generic-narrate ('they slept well'). Note what is unusual, repeating, or worth tracking."
)

OBSERVER_TEMPLATE = """# Sleep session summary

Session start: {started_at}
Session end:   {ended_at}
Duration:      {duration_min} minutes ({duration_hours:.1f} hours)
Sensor sources: {sensor_sources}

## Sleep stages (from Apple Health)
{stages_summary}

## Sensor aggregates
{sensor_summary}

## State estimates (Daybook RealtimeClassifier)
{state_summary}

## Dream recalls captured the morning after
{dream_recalls}

## Regis moments / cue events during this session
{moments_summary}

## Intent the user set the evening before (if any)
{intent_summary}

## Recent context (last 7 days)
{recent_context}

## Task
Return 1-5 short observations Regis would want to remember about this night.
Focus on what's distinctive: fragmentation patterns, REM proportion deviations,
streaks (third night this week, etc.), correlations between intent and recall,
unusually high/low HRV vs the user's recent baseline, anything pattern-shaped.
If nothing is noteworthy, return one observation like "unremarkable night, holding baseline"."""


@dataclass
class _SessionRow:
    id: str
    user_id: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    sensor_sources: list[str]


def observe_sleep_session(
    *,
    session_id: str,
    user_id: str,
    persist: bool = True,
    client: ChatClient | None = None,
) -> list[str]:
    """Summarize one session into observations. Returns the texts (also persisted if requested)."""
    session = _fetch_session(session_id)
    if session is None:
        logger.warning("sleep_observer: session %s not found", session_id)
        return []
    if session.user_id != user_id:
        logger.warning(
            "sleep_observer: session %s belongs to %s, not %s",
            session_id,
            session.user_id,
            user_id,
        )
        return []

    prompt = OBSERVER_TEMPLATE.format(
        started_at=session.started_at.isoformat(),
        ended_at=session.ended_at.isoformat(),
        duration_min=session.duration_seconds // 60,
        duration_hours=session.duration_seconds / 3600.0,
        sensor_sources=", ".join(session.sensor_sources) or "(none)",
        stages_summary=_summarize_stages(session_id),
        sensor_summary=_summarize_sensors(session_id, user_id),
        state_summary=_summarize_state_estimates(session_id, user_id),
        dream_recalls=_summarize_dream_recalls(session_id, user_id, session.ended_at),
        moments_summary=_summarize_moments(session_id),
        intent_summary=_summarize_intent(session_id, user_id, session.started_at),
        recent_context=_summarize_recent_context(user_id, session.started_at),
    )

    try:
        c = client or ChatClient.auto()
        result = c.chat_structured(
            system=OBSERVER_SYSTEM,
            user=prompt,
            schema=SessionObservations,
            schema_name="SessionObservations",
            reasoning_effort="medium",
            verbosity="low",
        )
        observations = [o.strip() for o in result.observations if o.strip()]
    except Exception as e:
        logger.warning("sleep_observer LLM failed for session %s: %s", session_id, e)
        return []

    if not observations:
        return []

    observations = observations[:5]

    if persist:
        for obs_text in observations:
            try:
                obs_id = _insert_observation(
                    user_id=user_id,
                    observation=obs_text,
                    context={
                        "session_id": session_id,
                        "session_started_at": session.started_at.isoformat(),
                        "source": "sleep_observer",
                    },
                )
                _emb_id, obs_vec = embed_and_store(
                    user_id=user_id,
                    source_type="regis_observation",
                    source_id=obs_id,
                    text=obs_text,
                )
                _link_embedding(obs_id)
                # Novelty signal: sleep-session observations are user-state
                # evidence (patterns Regis distilled from one night). Vector
                # reused from embed_and_store above. Never block the write
                # path on novelty failure.
                try:
                    log_novelty_observation(
                        user_id=user_id,
                        state_snapshot={
                            "source_type": "regis_observation",
                            "source_id": obs_id,
                            "source": "sleep_observer",
                            "session_id": session_id,
                            "text_preview": obs_text[:200],
                        },
                        embedding=obs_vec,
                    )
                except Exception as e:
                    logger.warning("novelty logging failed (sleep_observer): %s", e)
            except Exception as e:
                logger.warning("sleep_observer persist failed: %s", e)

    return observations


def observe_recent_sessions(
    *,
    user_id: str,
    since_date: date,
    max_sessions: int = 30,
    client: ChatClient | None = None,
) -> int:
    """Backfill observations for recent sessions. Returns total observations written."""
    cutoff = datetime.combine(since_date, datetime.min.time(), tzinfo=timezone.utc)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text FROM sleep_sessions
            WHERE user_id = %s AND started_at >= %s
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (user_id, cutoff, max_sessions),
        )
        sessions = [r[0] for r in cur.fetchall()]

    total = 0
    for sid in sessions:
        obs = observe_sleep_session(
            session_id=sid, user_id=user_id, client=client, persist=True
        )
        total += len(obs)
    return total


# ----------------------------------------------------------------------------
# Helpers — pull and condense each section of the session context.
# ----------------------------------------------------------------------------


def _fetch_session(session_id: str) -> _SessionRow | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, user_id::text, started_at, ended_at, duration_seconds, sensor_sources
            FROM sleep_sessions
            WHERE id = %s
            """,
            (session_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return _SessionRow(
        id=row[0],
        user_id=row[1],
        started_at=row[2],
        ended_at=row[3],
        duration_seconds=row[4],
        sensor_sources=list(row[5] or []),
    )


def _summarize_stages(session_id: str) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT stage, epoch_start_at FROM sleep_stage_classifications
            WHERE session_id = %s
            ORDER BY epoch_start_at
            """,
            (session_id,),
        )
        rows = cur.fetchall()
    if not rows:
        return "(no stage classifications)"
    counts = Counter(r[0] for r in rows)
    total = sum(counts.values())
    transitions = sum(1 for i in range(1, len(rows)) if rows[i][0] != rows[i - 1][0])
    pct = {k: round(100.0 * v / total) for k, v in counts.items()}
    pct_line = ", ".join(f"{p}% {s}" for s, p in pct.items())
    return f"{total} epochs, {transitions} stage transitions. Distribution: {pct_line}."


def _summarize_sensors(session_id: str, user_id: str) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT kind, payload FROM sensor_readings
            WHERE session_id = %s
            """,
            (session_id,),
        )
        rows = cur.fetchall()

    if not rows:
        return "(no sensor readings tied to this session)"

    hrs: list[float] = []
    hrvs: list[float] = []
    resps: list[float] = []
    for kind, payload in rows:
        if kind == "heart_rate" and isinstance(payload, dict):
            v = payload.get("bpm")
            if isinstance(v, (int, float)):
                hrs.append(float(v))
        elif kind == "hrv" and isinstance(payload, dict):
            v = payload.get("rmssdMs")
            if isinstance(v, (int, float)):
                hrvs.append(float(v))
        elif kind == "respiratory_rate" and isinstance(payload, dict):
            v = payload.get("breathsPerMinute")
            if isinstance(v, (int, float)):
                resps.append(float(v))

    parts: list[str] = []
    if hrs:
        m = mean(hrs)
        s = stdev(hrs) if len(hrs) > 1 else 0.0
        parts.append(f"HR n={len(hrs)} mean={m:.1f} std={s:.1f} min={min(hrs):.0f} max={max(hrs):.0f}")
    if hrvs:
        parts.append(f"HRV n={len(hrvs)} mean={mean(hrvs):.1f}ms min={min(hrvs):.1f} max={max(hrvs):.1f}")
    if resps:
        parts.append(f"Resp n={len(resps)} mean={mean(resps):.1f}/min")
    return " | ".join(parts) if parts else "(sensor data present but no recognized kinds)"


def _summarize_state_estimates(session_id: str, user_id: str) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT stage_proba, arousal, valence, presence, confidence
            FROM user_state_estimate
            WHERE session_id = %s
            ORDER BY estimated_at
            """,
            (session_id,),
        )
        rows = cur.fetchall()
    if not rows:
        return "(no state estimates for this session)"
    rem_probs = [r[0].get("REM") for r in rows if r[0] and "REM" in r[0]]
    parts = [f"n={len(rows)} estimates"]
    if rem_probs:
        valid = [float(p) for p in rem_probs if isinstance(p, (int, float))]
        if valid:
            parts.append(f"REM prob mean={mean(valid):.2f} max={max(valid):.2f}")
    return " | ".join(parts)


def _summarize_dream_recalls(session_id: str, user_id: str, ended_at: datetime) -> str:
    """Recalls explicitly tied to this session OR captured within 6 hours after wake."""
    window_end = ended_at + timedelta(hours=6)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT captured_at, depth, raw_text, themes
            FROM dream_recalls
            WHERE user_id = %s
              AND (session_id = %s OR (captured_at BETWEEN %s AND %s))
            ORDER BY captured_at
            """,
            (user_id, session_id, ended_at, window_end),
        )
        rows = cur.fetchall()
    if not rows:
        return "(no dream recalls captured)"
    parts: list[str] = []
    for cap, depth, text, themes in rows:
        snippet = (text or "")[:280].replace("\n", " ")
        themes_str = ", ".join(themes or [])
        parts.append(f"[{depth}] {snippet}{' (themes: ' + themes_str + ')' if themes_str else ''}")
    return "\n".join(parts)


def _summarize_moments(session_id: str) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT occurred_at, kind, mode, content
            FROM regis_moments
            WHERE session_id = %s
            ORDER BY occurred_at
            """,
            (session_id,),
        )
        rows = cur.fetchall()
        cur.execute(
            """
            SELECT delivered_at, cue_content, content_type, response_detected
            FROM cue_events
            WHERE session_id = %s
            ORDER BY delivered_at
            """,
            (session_id,),
        )
        cues = cur.fetchall()
    parts: list[str] = []
    for occ, kind, mode, content in rows:
        parts.append(f"moment [{kind}/{mode}] {content[:160]}")
    for d, content, ctype, resp in cues:
        parts.append(f"cue [{ctype}] response={resp} {content[:160]}")
    return "\n".join(parts) if parts else "(none)"


def _summarize_intent(session_id: str, user_id: str, started_at: datetime) -> str:
    window_start = started_at - timedelta(hours=12)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT intent_text, set_at FROM intents
            WHERE user_id = %s
              AND (target_session_id = %s OR (set_at BETWEEN %s AND %s))
            ORDER BY set_at DESC
            LIMIT 3
            """,
            (user_id, session_id, window_start, started_at),
        )
        rows = cur.fetchall()
    if not rows:
        return "(no intent set)"
    return "\n".join(f"({r[1].isoformat()}) {r[0]}" for r in rows)


def _summarize_recent_context(user_id: str, session_start: datetime) -> str:
    """One-paragraph stat: recall rate + avg duration the past 7 days."""
    window_start = session_start - timedelta(days=7)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*), avg(duration_seconds)
            FROM sleep_sessions
            WHERE user_id = %s
              AND started_at BETWEEN %s AND %s
            """,
            (user_id, window_start, session_start),
        )
        n_sessions, avg_dur = cur.fetchone()
        cur.execute(
            """
            SELECT count(*)
            FROM dream_recalls dr
            JOIN sleep_sessions ss ON dr.session_id = ss.id
            WHERE dr.user_id = %s
              AND ss.started_at BETWEEN %s AND %s
              AND dr.depth <> 'NONE'
            """,
            (user_id, window_start, session_start),
        )
        n_recalls = cur.fetchone()[0]
    avg_dur_h = (float(avg_dur) / 3600.0) if avg_dur else 0.0
    recall_rate = (n_recalls / n_sessions * 100.0) if n_sessions else 0.0
    return f"Past 7 days: {n_sessions} sessions, avg {avg_dur_h:.1f}h, recall rate {recall_rate:.0f}%."


def _insert_observation(*, user_id: str, observation: str, context: dict[str, Any]) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regis_observations
                (user_id, observation, context, source)
            VALUES (%s, %s, %s::jsonb, 'sleep_observer')
            RETURNING id::text
            """,
            (user_id, observation, json.dumps(context, default=str)),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
    return new_id


def _link_embedding(obs_id: str) -> None:
    """Mirror the embedding back into regis_observations.embedding."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE regis_observations
            SET embedding = (
              SELECT embedding FROM embeddings
              WHERE source_type = 'regis_observation' AND source_id = %s
              ORDER BY created_at DESC LIMIT 1
            )
            WHERE id = %s
            """,
            (obs_id, obs_id),
        )
        conn.commit()


def _main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--session-id", help="Specific session UUID to observe")
    ap.add_argument(
        "--since-date",
        help="Backfill all sessions started on/after this YYYY-MM-DD date",
    )
    ap.add_argument("--max-sessions", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true", help="Do not persist observations")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.session_id:
        obs = observe_sleep_session(
            session_id=args.session_id,
            user_id=args.user_id,
            persist=not args.dry_run,
        )
        for o in obs:
            print(f"- {o}")
        return 0
    if args.since_date:
        since = datetime.strptime(args.since_date, "%Y-%m-%d").date()
        total = observe_recent_sessions(
            user_id=args.user_id, since_date=since, max_sessions=args.max_sessions
        )
        print(f"Wrote {total} observations across recent sessions.")
        return 0
    print("Pass --session-id or --since-date.")
    return 2


if __name__ == "__main__":
    sys.exit(_main())
