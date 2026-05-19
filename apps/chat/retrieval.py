"""Gather everything Regis should know about right now into one dict.

Wraps the shared substrate (imodels.gather_substrate) with chat-specific
reads. Substrate covers what BOTH chat and wisp need:
  - regis_traits, current_user_state, current_prosody
  - active_i_models, relevant_observations

Chat layers on top:
  - current_conversation_recent (last 6 turns, verbatim)
  - similar_past_exchanges (top-5 outside current conversation)
  - relevant_health_data (keyword-gated only)
"""
from __future__ import annotations

import time
from typing import Any

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402
from embeddings import embed, retrieve_similar  # noqa: E402
from imodels.substrate import gather_substrate  # noqa: E402

from .health_summary import summarize_health_for_query


RECENT_TURNS = 6
SIMILAR_PAST_TOP_K = 5
SIMILAR_PAST_MIN_SIMILARITY = 0.3


def gather_context(
    *,
    user_id: str,
    conversation_id: str,
    user_text: str,
    user_embedding: list[float] | None = None,
) -> dict[str, Any]:
    """Build the structured context dict that handler turns into a prompt.

    Shape preserved exactly across the substrate refactor — chat callers
    (handler._build_prompt, smoke tests) rely on these keys.
    """
    t0 = time.monotonic()
    qvec = user_embedding if user_embedding is not None else embed(user_text)

    substrate = gather_substrate(user_id=user_id, query_embedding=qvec)

    recent = _recent_turns(conversation_id=conversation_id, limit=RECENT_TURNS)
    similar_past = _similar_past_exchanges(
        user_id=user_id,
        conversation_id=conversation_id,
        qvec=qvec,
        top_k=SIMILAR_PAST_TOP_K,
    )
    health = summarize_health_for_query(user_text, user_id=user_id)

    # Strip cluster_id from active_i_models — it's a new substrate-only field
    # used by wisp's persistence path; chat's contract never exposed it and we
    # don't want it leaking into chat's debug logs / handler renderings.
    active_imodels_chat_shape = [
        {k: v for k, v in im.items() if k != "cluster_id"}
        for im in substrate.active_i_models
    ]

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    return {
        "current_conversation_recent": recent,
        "similar_past_exchanges": similar_past,
        "relevant_health_data": health,
        "relevant_observations": substrate.relevant_observations,
        "current_user_state": substrate.current_user_state,
        "regis_traits": substrate.regis_traits,
        "current_prosody": substrate.current_prosody,
        "active_i_models": active_imodels_chat_shape,
        "_retrieval_ms": elapsed_ms,
    }


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
