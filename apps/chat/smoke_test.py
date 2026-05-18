"""End-to-end chat smoke test.

Runs 3 fixed exchanges, verifies persistence + retrieval, prints Regis
responses for eyeball review, then cleans up.

Run with:
    cd apps && source inference/.venv/bin/activate
    python -m chat.smoke_test
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402

from .conversation import create_conversation, end_conversation
from .handler import handle_user_message


SMOKE_TITLE = "SMOKE_TEST: chat regis"
PROMPTS = [
    "How did I sleep last week?",
    "What patterns have you noticed in my dreams?",
    "Just checking in.",
]


def _apply_migration() -> None:
    """Idempotent: 0004 uses CREATE TABLE IF NOT EXISTS."""
    sql_path = (
        Path(__file__).resolve().parent.parent
        / "inference"
        / "migrations"
        / "0004_chat_messages.sql"
    )
    if not sql_path.exists():
        raise FileNotFoundError(f"missing migration: {sql_path}")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql_path.read_text())
        conn.commit()


def _cleanup() -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM chat_conversations WHERE title LIKE 'SMOKE_TEST:%'"
        )
        ids = [str(r[0]) for r in cur.fetchall()]
        if not ids:
            return 0
        cur.execute(
            """
            DELETE FROM embeddings
            WHERE source_type = 'chat_message'
              AND source_id IN (
                SELECT id FROM chat_messages WHERE conversation_id = ANY(%s)
              )
            """,
            (ids,),
        )
        emb_deleted = cur.rowcount
        cur.execute(
            "DELETE FROM chat_conversations WHERE id = ANY(%s)", (ids,)
        )
        conv_deleted = cur.rowcount
        cur.execute(
            "DELETE FROM regis_observations WHERE source = 'chat_observer' AND context->>'_smoke_test' = 'true'"
        )
        cur.execute(
            "DELETE FROM regis_trait_history WHERE reason LIKE 'smoke:%'"
        )
        conn.commit()
    print(f"  cleaned {conv_deleted} conversations, {emb_deleted} chat embeddings")
    return conv_deleted


def main() -> int:
    print("=== Daybook chat smoke test ===\n")

    print("[setup] applying migration 0004 (idempotent)...")
    _apply_migration()
    print("  ok\n")

    print("[setup] cleaning any leftover SMOKE_TEST: conversations from prior runs...")
    _cleanup()
    print()

    conversation_id = create_conversation(
        user_id=_paths.DEFAULT_USER_ID, title=SMOKE_TITLE
    )
    print(f"[setup] new conversation: {conversation_id}\n")

    results = []
    for i, prompt in enumerate(PROMPTS, start=1):
        print(f"--- exchange {i}/{len(PROMPTS)} ---")
        print(f"> You: {prompt}")
        resp = handle_user_message(
            user_id=_paths.DEFAULT_USER_ID,
            conversation_id=conversation_id,
            user_text=prompt,
        )
        print(f"\nRegis ({resp.elapsed_ms}ms via {resp.backend}/{resp.model}):")
        for line in resp.text.splitlines() or [""]:
            print(f"  {line}")
        if resp.observation_extracted:
            print(f"  >> observation extracted: {resp.observation_extracted!r}")
        else:
            print("  >> observation: (none / skipped — short message)")
        if resp.trait_deltas:
            print("  >> trait drift:")
            for d in resp.trait_deltas:
                print(f"     {d['trait']:>12} {d['delta']:+.03f}  ({d['reason']})")
        else:
            print("  >> trait drift: (no rules fired)")
        ctx = resp.context_assembled
        print(
            f"  >> context: retrieval_ms={ctx.get('_retrieval_ms')}, "
            f"recent={ctx.get('current_conversation_recent_count', 0)}, "
            f"similar_past={ctx.get('similar_past_exchanges_count', 0)}, "
            f"observations={ctx.get('relevant_observations_count', 0)}, "
            f"health={'yes' if (ctx.get('relevant_health_data') or '').strip() else 'no'}"
        )
        print()
        results.append(resp)

    print("--- verification ---")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM chat_conversations WHERE id = %s",
            (conversation_id,),
        )
        n_conv = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*), COUNT(embedding_id) FROM chat_messages "
            "WHERE conversation_id = %s",
            (conversation_id,),
        )
        n_msg, n_with_emb = cur.fetchone()
        cur.execute(
            "SELECT role, COUNT(*) FROM chat_messages WHERE conversation_id = %s GROUP BY role",
            (conversation_id,),
        )
        per_role = dict(cur.fetchall())

    print(f"  conversations row exists: {n_conv == 1}")
    print(f"  message rows: {n_msg} (expected 6)")
    print(f"  per role: {per_role}")
    print(f"  rows with embedding_id set: {n_with_emb} (expected {n_msg})")

    ok = (
        n_conv == 1
        and n_msg == 6
        and per_role.get("user") == 3
        and per_role.get("assistant") == 3
        and n_with_emb == n_msg
    )
    print(f"  >>> verification: {'PASS' if ok else 'FAIL'}\n")

    print("[cleanup] removing SMOKE_TEST: conversations + chat embeddings...")
    end_conversation(conversation_id=conversation_id)
    _cleanup()

    print("\n=== chat smoke test complete ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
