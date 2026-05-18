"""After-the-fact observation extractor.

Pulls a short note out of an exchange that Regis would want to remember.
Writes to regis_observations and embeds it so future retrieval can find it.

Cost-conscious: only fires if the user message is substantive
(>=`MIN_USER_WORDS` words). Short check-ins almost never reveal new things.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402
from embeddings import embed_and_store  # noqa: E402
from llm import ChatClient  # noqa: E402


logger = logging.getLogger(__name__)

MIN_USER_WORDS = 20

OBSERVER_SYSTEM = (
    "You extract short observations a memory layer should keep. "
    "Be terse. Return only the note itself or the literal text 'nothing notable'."
)

OBSERVER_TEMPLATE = """You are Regis's note-taking layer. Given this exchange, extract ONE noteworthy fact about the user that Regis would want to remember.

User: {user}
Regis: {assistant}

Return ONE short note (1-2 sentences max), or 'nothing notable' if the exchange revealed nothing memorable. Just the note, no preamble."""


def maybe_extract_observation(
    *,
    user_id: str,
    user_message: str,
    assistant_message: str,
    client: ChatClient | None = None,
    context: dict[str, Any] | None = None,
) -> str | None:
    """If the exchange is substantive, ask the LLM for one note. Persist + embed it.

    Returns the observation text, or None if skipped / nothing notable / LLM failed.
    """
    if len(user_message.split()) < MIN_USER_WORDS:
        return None

    try:
        c = client or ChatClient.auto()
        text = c.chat(
            system=OBSERVER_SYSTEM,
            user=OBSERVER_TEMPLATE.format(
                user=user_message.strip(), assistant=assistant_message.strip()
            ),
            reasoning_effort="low",
            verbosity="low",
        ).strip()
    except Exception as e:
        logger.warning("observer LLM call failed: %s", e)
        return None

    if not text or "nothing notable" in text.lower():
        return None

    if text.startswith('"') and text.endswith('"') and len(text) > 2:
        text = text[1:-1]
    if len(text) > 500:
        text = text[:500].rstrip() + "..."

    try:
        obs_id = _insert_observation(
            user_id=user_id,
            observation=text,
            context=context or {},
        )
        embed_and_store(
            user_id=user_id,
            source_type="regis_observation",
            source_id=obs_id,
            text=text,
        )
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
    except Exception as e:
        logger.warning("observer persist failed: %s", e)
        return None

    return text


def _insert_observation(
    *, user_id: str, observation: str, context: dict[str, Any]
) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regis_observations
              (user_id, observation, context, source)
            VALUES (%s, %s, %s::jsonb, 'chat_observer')
            RETURNING id
            """,
            (user_id, observation, json.dumps(context, default=str)),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id
