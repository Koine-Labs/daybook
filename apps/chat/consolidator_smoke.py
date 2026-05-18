"""Smoke test for chat.consolidator.

Seeds a few fake chat exchanges dated yesterday, runs consolidate_yesterday,
prints the observations, then cleans up all test rows.

Run with:
    cd apps/inference && source .venv/bin/activate
    python -m chat.consolidator_smoke
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402

from .consolidator import consolidate_yesterday


DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


SEED_EXCHANGES = [
    # Conversation 1 — builder mode, mentioning Pi project
    (
        "I've been thinking about the Pi project all weekend. The ESP32 wiring is bothering me — too many loose connections.",
        "Tape them. You'll lose a day if one of those drops mid-session.",
    ),
    (
        "Yeah. I want to ship the bedside rig by next weekend even if it's ugly.",
        "Ugly and live beats clean and parked. What's the smallest version that does anything?",
    ),
    (
        "Just the cue trigger. I don't need recall capture wired yet — I can voice-memo from my phone.",
        "Good. One nerve, alive.",
    ),
    # Conversation 2 — reflective, mentions a recurring dream theme
    (
        "I dreamed about my grandfather again last night. Third time this month. He's always at the same kitchen table.",
        "What is he doing at the table?",
    ),
    (
        "Just sitting. Waiting. I think he's waiting for me to say something but I never do.",
        "Note when you dream it again. The pattern is worth keeping near you.",
    ),
]


def _seed_conversations() -> tuple[list[str], list[str]]:
    """Insert two fake conversations from yesterday. Returns (conv_ids, msg_ids)."""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    base_ts = yesterday.replace(hour=14, minute=0, second=0, microsecond=0)

    conv_ids: list[str] = []
    msg_ids: list[str] = []

    with get_conn() as conn, conn.cursor() as cur:
        for conv_idx, exchanges in enumerate([SEED_EXCHANGES[:3], SEED_EXCHANGES[3:]]):
            cur.execute(
                """
                INSERT INTO chat_conversations (user_id, started_at, title)
                VALUES (%s, %s, %s)
                RETURNING id::text
                """,
                (DEFAULT_USER_ID, base_ts + timedelta(hours=conv_idx * 2), "smoke-test"),
            )
            conv_id = cur.fetchone()[0]
            conv_ids.append(conv_id)

            for turn_idx, (user_text, asst_text) in enumerate(exchanges):
                ts = base_ts + timedelta(hours=conv_idx * 2, minutes=turn_idx * 4)
                cur.execute(
                    """
                    INSERT INTO chat_messages (conversation_id, user_id, role, content, sent_at, metadata)
                    VALUES (%s, %s, 'user', %s, %s, %s::jsonb)
                    RETURNING id::text
                    """,
                    (conv_id, DEFAULT_USER_ID, user_text, ts, json.dumps({"smoke": True})),
                )
                msg_ids.append(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO chat_messages (conversation_id, user_id, role, content, sent_at, metadata)
                    VALUES (%s, %s, 'assistant', %s, %s, %s::jsonb)
                    RETURNING id::text
                    """,
                    (conv_id, DEFAULT_USER_ID, asst_text, ts + timedelta(seconds=30), json.dumps({"smoke": True})),
                )
                msg_ids.append(cur.fetchone()[0])
        conn.commit()
    return conv_ids, msg_ids


def _cleanup(conv_ids: list[str], obs_ids: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with get_conn() as conn, conn.cursor() as cur:
        # Observations + their embeddings
        if obs_ids:
            cur.execute(
                "DELETE FROM embeddings WHERE source_type='regis_observation' AND source_id::text = ANY(%s)",
                (obs_ids,),
            )
            cur.execute("DELETE FROM regis_observations WHERE id::text = ANY(%s)", (obs_ids,))
            counts["observations"] = cur.rowcount
        # Cascade delete conversations (also deletes messages + embeddings via app-level link)
        if conv_ids:
            # Detach chat_messages' embedding links first (won't cascade)
            cur.execute(
                """
                DELETE FROM embeddings
                WHERE source_type = 'chat_message'
                  AND source_id::text IN (
                    SELECT id::text FROM chat_messages WHERE conversation_id::text = ANY(%s)
                  )
                """,
                (conv_ids,),
            )
            counts["chat_msg_embeddings"] = cur.rowcount
            cur.execute("DELETE FROM chat_conversations WHERE id::text = ANY(%s)", (conv_ids,))
            counts["conversations"] = cur.rowcount
        conn.commit()
    return counts


def main() -> int:
    print("=== Chat Consolidator smoke test ===\n")

    print("[1] Seeding 2 fake conversations from yesterday (5 user turns, 5 assistant turns)...")
    conv_ids, msg_ids = _seed_conversations()
    print(f"  Inserted {len(conv_ids)} conversations, {len(msg_ids)} message rows.")

    obs_ids: list[str] = []
    try:
        print("\n[2] Calling consolidate_yesterday() (LLM call — may take 5-30s)...")
        n_before = _count_observations(source="chat_consolidator")
        n_written = consolidate_yesterday(user_id=DEFAULT_USER_ID, persist=True)
        n_after = _count_observations(source="chat_consolidator")
        print(f"\n[3] Wrote {n_written} observations (table delta: {n_after - n_before})")

        # Find the new ones
        obs_ids = _find_smoke_observations()
        for i, (oid, text) in enumerate(obs_ids, 1):
            print(f"  {i}. {text}")
        obs_ids = [oid for oid, _ in obs_ids]

    finally:
        print("\n[4] Cleaning up smoke test rows...")
        counts = _cleanup(conv_ids, obs_ids)
        for k, v in counts.items():
            print(f"  deleted {v} from {k}")

    print("\n=== Chat Consolidator smoke test complete ===")
    return 0


def _count_observations(*, source: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM regis_observations WHERE source = %s", (source,))
        return int(cur.fetchone()[0])


def _find_smoke_observations() -> list[tuple[str, str]]:
    """Find the consolidator observations from this smoke test (last 10 min, this user)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, observation FROM regis_observations
            WHERE user_id = %s
              AND source = 'chat_consolidator'
              AND observed_at > NOW() - INTERVAL '10 minutes'
            ORDER BY observed_at
            """,
            (DEFAULT_USER_ID,),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


if __name__ == "__main__":
    sys.exit(main())
