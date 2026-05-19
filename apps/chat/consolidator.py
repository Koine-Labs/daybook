"""Daily chat consolidation.

Pulls a day's chat_messages across all conversations for one user, hands them
to the LLM as structured turn-pairs, and asks for 0-5 short observations
Regis would want to remember.

Each observation is persisted to regis_observations (source='chat_consolidator')
and embedded so future retrieval can find it.

Skipped when the day has fewer than MIN_MESSAGES_TO_CONSOLIDATE messages —
nothing meaningful to consolidate from a handful of check-ins.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402
from embeddings import embed, embed_and_store  # noqa: E402
from imodels import log_novelty_observation  # noqa: E402
from llm import ChatClient  # noqa: E402


logger = logging.getLogger(__name__)

MIN_MESSAGES_TO_CONSOLIDATE = 3
MAX_OBSERVATIONS = 5


class DayObservations(BaseModel):
    """LLM schema: 0-5 short notes Regis would remember from today's chats."""

    model_config = ConfigDict(extra="forbid")

    observations: list[str] = Field(
        description="0-5 short notes Regis would remember from today's chats; empty list if nothing notable"
    )


CONSOLIDATOR_SYSTEM = (
    "You are Regis's daily-consolidation memory layer. You read one day of chat "
    "exchanges between the user and Regis and extract 0-5 short notes a personal "
    "companion would want to remember about the user. Be terse, specific, "
    "pattern-oriented. Each note is 1-2 sentences. "
    "Skip pleasantries and short check-ins. If the day was unremarkable, return an empty list."
)

CONSOLIDATOR_TEMPLATE = """# Date: {target_date}

# Today's chat conversations (oldest first)
{conversation_blocks}

# Task
Extract 0-5 short observations Regis would want to remember about the user
based on today's exchanges. Look for: stated intents, mentioned interests,
shifts in mood, recurring themes, things the user wants Regis to follow up on,
or context that would help future conversations land better.
Each note is 1-2 sentences, specific, not generic.
If nothing notable was discussed, return an empty list."""


def consolidate_chat_day(
    *,
    user_id: str,
    target_date: date,
    persist: bool = True,
    client: ChatClient | None = None,
) -> int:
    """Summarize a day's chat exchanges into regis_observations. Returns count written."""
    messages = _fetch_messages_for_day(user_id=user_id, target_date=target_date)
    if len(messages) < MIN_MESSAGES_TO_CONSOLIDATE:
        logger.info(
            "consolidate_chat_day: only %d messages on %s, skipping (need >= %d)",
            len(messages),
            target_date.isoformat(),
            MIN_MESSAGES_TO_CONSOLIDATE,
        )
        return 0

    blocks = _format_conversation_blocks(messages)
    prompt = CONSOLIDATOR_TEMPLATE.format(
        target_date=target_date.isoformat(),
        conversation_blocks=blocks,
    )

    try:
        c = client or ChatClient.auto()
        result = c.chat_structured(
            system=CONSOLIDATOR_SYSTEM,
            user=prompt,
            schema=DayObservations,
            schema_name="DayObservations",
            reasoning_effort="medium",
            verbosity="low",
        )
        observations = [o.strip() for o in result.observations if o.strip()][:MAX_OBSERVATIONS]
    except Exception as e:
        logger.warning("consolidate_chat_day LLM failed for %s: %s", target_date.isoformat(), e)
        return 0

    if not observations:
        return 0

    if not persist:
        for o in observations:
            print(f"- {o}")
        return len(observations)

    written = 0
    for obs_text in observations:
        try:
            obs_id = _insert_observation(
                user_id=user_id,
                observation=obs_text,
                context={
                    "target_date": target_date.isoformat(),
                    "source": "chat_consolidator",
                    "message_count": len(messages),
                },
            )
            embed_and_store(
                user_id=user_id,
                source_type="regis_observation",
                source_id=obs_id,
                text=obs_text,
            )
            _link_embedding(obs_id)
            # Novelty signal: nightly NREM consolidations are derived user-state
            # summaries. Per brief, log as 'regis_observation' source_type to
            # match how they're stored. Never block on failure.
            try:
                obs_vec = embed(obs_text)
                log_novelty_observation(
                    user_id=user_id,
                    state_snapshot={
                        "source_type": "regis_observation",
                        "source_id": obs_id,
                        "source": "chat_consolidator",
                        "target_date": target_date.isoformat(),
                        "text_preview": obs_text[:200],
                    },
                    embedding=obs_vec,
                )
            except Exception as e:
                logger.warning("novelty logging failed (consolidator): %s", e)
            written += 1
        except Exception as e:
            logger.warning("consolidate_chat_day persist failed: %s", e)

    return written


def consolidate_yesterday(*, user_id: str, **kwargs: Any) -> int:
    """Convenience: consolidate yesterday's chats (UTC)."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    return consolidate_chat_day(user_id=user_id, target_date=yesterday, **kwargs)


# Compatibility wrapper retained for any existing callers from the old stub.
def consolidate_day(
    *, user_id: str, day: datetime | None = None
) -> dict[str, int]:
    """Stub-compat wrapper: invokes consolidate_chat_day for the given day."""
    target = day or (datetime.now(timezone.utc) - timedelta(days=1))
    written = consolidate_chat_day(user_id=user_id, target_date=target.date(), persist=True)
    return {
        "exchanges_scanned": _count_messages(user_id=user_id, target_date=target.date()),
        "observations_written": written,
        "trait_deltas_applied": 0,
    }


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _fetch_messages_for_day(
    *, user_id: str, target_date: date
) -> list[tuple[str, str, str, datetime]]:
    """Return all messages (conversation_id, role, content, sent_at) on target_date UTC."""
    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT conversation_id::text, role, content, sent_at
            FROM chat_messages
            WHERE user_id = %s
              AND sent_at >= %s AND sent_at < %s
            ORDER BY sent_at
            """,
            (user_id, start, end),
        )
        return list(cur.fetchall())


def _count_messages(*, user_id: str, target_date: date) -> int:
    return len(_fetch_messages_for_day(user_id=user_id, target_date=target_date))


def _format_conversation_blocks(
    messages: list[tuple[str, str, str, datetime]],
) -> str:
    """Group messages by conversation_id and format as labeled turn blocks."""
    by_conv: dict[str, list[tuple[str, str, datetime]]] = defaultdict(list)
    for conv_id, role, content, sent_at in messages:
        by_conv[conv_id].append((role, content, sent_at))

    blocks: list[str] = []
    for i, (conv_id, turns) in enumerate(by_conv.items(), 1):
        turns.sort(key=lambda t: t[2])
        block_lines = [f"## Conversation {i} (id {conv_id[:8]}.., {len(turns)} turns)"]
        for role, content, sent_at in turns:
            tag = "USER" if role == "user" else ("REGIS" if role == "assistant" else role.upper())
            text = content.strip()
            if len(text) > 600:
                text = text[:600].rstrip() + "..."
            block_lines.append(f"  {tag}: {text}")
        blocks.append("\n".join(block_lines))
    return "\n\n".join(blocks)


def _insert_observation(
    *, user_id: str, observation: str, context: dict[str, Any]
) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regis_observations
                (user_id, observation, context, source)
            VALUES (%s, %s, %s::jsonb, 'chat_consolidator')
            RETURNING id::text
            """,
            (user_id, observation, json.dumps(context, default=str)),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
    return new_id


def _link_embedding(obs_id: str) -> None:
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
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="Target date YYYY-MM-DD (UTC)")
    g.add_argument("--yesterday", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.yesterday:
        n = consolidate_yesterday(user_id=args.user_id, persist=not args.dry_run)
    else:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
        n = consolidate_chat_day(
            user_id=args.user_id, target_date=target, persist=not args.dry_run
        )
    print(f"Wrote {n} observations.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
