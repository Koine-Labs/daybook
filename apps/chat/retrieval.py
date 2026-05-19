"""Gather everything Regis should know about right now into one dict.

Pieces:
  - recent turns of current conversation (verbatim, last 6)
  - similar past chat exchanges (top-5, OUTSIDE current conversation)
  - relevant health data slice (from health_summary)
  - top-3 relevant regis_observations by similarity
  - latest user_state_estimate row
  - current trait values (latest row per trait)
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402
from embeddings import embed, retrieve_similar  # noqa: E402
from imodels.activator import get_active_clusters  # noqa: E402

from .baseline_computer import fetch_current_trait_values
from .health_summary import summarize_health_for_query


RECENT_TURNS = 6
SIMILAR_PAST_TOP_K = 5
OBSERVATION_TOP_K = 3
SIMILAR_PAST_MIN_SIMILARITY = 0.3
# Only treat user_state_estimate as "current" if it's at most 1 hour old.
# Otherwise we'd inject stale snapshots into chat prompts (e.g., a sleep
# estimate from last night doesn't mean Aakash is asleep right now).
USER_STATE_FRESHNESS_SECONDS = 60 * 60


def gather_context(
    *,
    user_id: str,
    conversation_id: str,
    user_text: str,
    user_embedding: list[float] | None = None,
) -> dict[str, Any]:
    """Build the structured context dict that handler turns into a prompt."""
    t0 = time.monotonic()
    qvec = user_embedding if user_embedding is not None else embed(user_text)

    recent = _recent_turns(conversation_id=conversation_id, limit=RECENT_TURNS)
    similar_past = _similar_past_exchanges(
        user_id=user_id,
        conversation_id=conversation_id,
        qvec=qvec,
        top_k=SIMILAR_PAST_TOP_K,
    )
    health = summarize_health_for_query(user_text, user_id=user_id)
    observations = _relevant_observations(
        user_id=user_id, qvec=qvec, top_k=OBSERVATION_TOP_K
    )
    state = _latest_user_state(user_id)
    traits = _current_traits(user_id)
    prosody = _recent_prosody(user_id)
    active_i_models = _active_i_models(user_id=user_id, user_embedding=qvec)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    return {
        "current_conversation_recent": recent,
        "similar_past_exchanges": similar_past,
        "relevant_health_data": health,
        "relevant_observations": observations,
        "current_user_state": state,
        "regis_traits": traits,
        "current_prosody": prosody,
        "active_i_models": active_i_models,
        "_retrieval_ms": elapsed_ms,
    }


def _recent_prosody(user_id: str, limit: int = 3) -> list[dict[str, Any]]:
    """Last `limit` audio_context sensor_readings within the past 10 minutes."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT recorded_at, payload
                FROM sensor_readings
                WHERE user_id = %s
                  AND kind = 'audio_context'
                  AND recorded_at >= %s
                ORDER BY recorded_at DESC
                LIMIT %s
                """,
                (user_id, cutoff, limit),
            )
            rows = cur.fetchall()
    except Exception:
        return []
    return [
        {
            "recorded_at": r[0].isoformat(),
            "tone": (r[1] or {}).get("tone"),
            "energy": (r[1] or {}).get("energy"),
            "pitch_mean_hz": (r[1] or {}).get("pitch_mean_hz"),
            "pitch_std_hz": (r[1] or {}).get("pitch_std_hz"),
            "speaking_rate_wpm": (r[1] or {}).get("speaking_rate_wpm"),
            "vad_active": (r[1] or {}).get("vad_active"),
        }
        for r in rows
    ]


def _active_i_models(
    *, user_id: str, user_embedding: list[float]
) -> list[dict[str, Any]]:
    """Top-3 I-Model clusters firing for the current embedding."""
    try:
        active = get_active_clusters(
            user_id=user_id,
            query_embedding=user_embedding,
            top_k=3,
            min_similarity=0.4,
        )
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for c in active:
        label = c.label or f"unlabeled cluster #{c.cluster_id[:8]}"
        out.append(
            {
                "label": label,
                "similarity": round(c.similarity, 3),
                "model_owner": c.model_owner,
            }
        )
    return out


def _recent_turns(*, conversation_id: str, limit: int) -> list[dict[str, str]]:
    """Last `limit` messages in this conversation, oldest-first."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT role, content, sent_at
            FROM chat_messages
            WHERE conversation_id = %s
            ORDER BY sent_at DESC
            LIMIT %s
            """,
            (conversation_id, limit),
        )
        rows = list(reversed(cur.fetchall()))
    return [
        {"role": r[0], "content": r[1], "sent_at": r[2].isoformat()} for r in rows
    ]


def _similar_past_exchanges(
    *, user_id: str, conversation_id: str, qvec: list[float], top_k: int
) -> list[dict[str, Any]]:
    """Top-K semantically similar past chat messages OUTSIDE this conversation."""
    try:
        hits = retrieve_similar(
            qvec,
            user_id=user_id,
            top_k=top_k * 3,
            source_types=["chat_message"],
            min_similarity=SIMILAR_PAST_MIN_SIMILARITY,
        )
    except Exception as e:
        return [{"_retrieval_error": str(e)}]

    if not hits:
        return []

    msg_ids = [h.source_id for h in hits]
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, role, content, sent_at, conversation_id
            FROM chat_messages
            WHERE id = ANY(%s)
              AND conversation_id <> %s
            """,
            (msg_ids, conversation_id),
        )
        rows = {str(r[0]): r for r in cur.fetchall()}

    sim_by_id = {h.source_id: h.similarity for h in hits}
    matches: list[dict[str, Any]] = []
    for mid in msg_ids:
        if mid in rows:
            r = rows[mid]
            matches.append(
                {
                    "role": r[1],
                    "content": r[2],
                    "sent_at": r[3].isoformat(),
                    "similarity": round(float(sim_by_id[mid]), 3),
                }
            )
            if len(matches) >= top_k:
                break
    return matches


def _relevant_observations(
    *, user_id: str, qvec: list[float], top_k: int
) -> list[dict[str, Any]]:
    """Top-N regis_observations by embedding similarity, with full text."""
    try:
        hits = retrieve_similar(
            qvec,
            user_id=user_id,
            top_k=top_k,
            source_types=["regis_observation"],
        )
    except Exception as e:
        return [{"_retrieval_error": str(e)}]

    if not hits:
        return []

    obs_ids = [h.source_id for h in hits]
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, observation, observed_at
            FROM regis_observations
            WHERE id = ANY(%s)
            """,
            (obs_ids,),
        )
        rows = {str(r[0]): r for r in cur.fetchall()}

    sim_by_id = {h.source_id: h.similarity for h in hits}
    out: list[dict[str, Any]] = []
    for oid in obs_ids:
        if oid in rows:
            r = rows[oid]
            out.append(
                {
                    "observation": r[1],
                    "observed_at": r[2].isoformat(),
                    "similarity": round(float(sim_by_id[oid]), 3),
                }
            )
    return out


def _latest_user_state(user_id: str) -> dict[str, Any] | None:
    """Latest user_state_estimate row — only if fresh (within the last hour).

    Stale rows from past sessions or smoke tests are dropped: they would
    mislead Regis into thinking the user is currently in REM, etc.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=USER_STATE_FRESHNESS_SECONDS)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT estimated_at, stage_proba, arousal, valence, presence,
                   confidence, source
            FROM user_state_estimate
            WHERE user_id = %s
              AND estimated_at >= %s
            ORDER BY estimated_at DESC
            LIMIT 1
            """,
            (user_id, cutoff),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "estimated_at": row[0].isoformat() if row[0] else None,
        "stage_proba": row[1],
        "arousal": row[2],
        "valence": row[3],
        "presence": row[4],
        "confidence": row[5],
        "source": row[6],
    }


def _current_traits(user_id: str) -> dict[str, float]:
    """Latest value for each trait_name. Empty dict if no history yet.

    Delegates to baseline_computer.fetch_current_trait_values so the
    source-filter convention (exclude baseline/decay rows) lives in one
    place. See CURRENT_VALUE_SOURCE_FILTER for the rationale.
    """
    return fetch_current_trait_values(user_id)
