"""Smoke test for sleep_observer.

Picks a real existing sleep session, runs the observer end-to-end, prints
the produced observations, then cleans up the test rows.

Run with:
    cd apps/inference && source .venv/bin/activate
    python -m sleep_observer_smoke
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_conn  # noqa: E402

from sleep_observer import observe_sleep_session

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _pick_session() -> str | None:
    """Pick the most recent session with at least some stage classifications."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id::text
            FROM sleep_sessions s
            WHERE s.user_id = %s
              AND (SELECT count(*) FROM sleep_stage_classifications WHERE session_id = s.id) > 5
            ORDER BY s.started_at DESC
            LIMIT 1
            """,
            (DEFAULT_USER_ID,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _cleanup(observation_ids: list[str]) -> int:
    """Delete the test regis_observations rows (and their embeddings cascade)."""
    if not observation_ids:
        return 0
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM embeddings WHERE source_type = 'regis_observation' AND source_id = ANY(%s)",
            (observation_ids,),
        )
        cur.execute("DELETE FROM regis_observations WHERE id::text = ANY(%s)", (observation_ids,))
        n = cur.rowcount
        conn.commit()
    return n


def main() -> int:
    print("=== Sleep Observer smoke test ===\n")
    session_id = _pick_session()
    if session_id is None:
        print("No sleep session with stage data found for user. Aborting.")
        return 1
    print(f"[1] Using session_id={session_id}")

    obs_before = _ids_for_session(session_id)
    print(f"  Existing 'sleep_observer' observation rows for this session: {len(obs_before)}")

    print("\n[2] Calling observe_sleep_session() (LLM call — may take 5-30s)...")
    observations = observe_sleep_session(
        session_id=session_id,
        user_id=DEFAULT_USER_ID,
        persist=True,
    )
    print(f"\n[3] Got {len(observations)} observations:")
    for i, o in enumerate(observations, 1):
        print(f"  {i}. {o}")

    obs_after = _ids_for_session(session_id)
    new_ids = [i for i in obs_after if i not in obs_before]
    print(f"\n[4] Newly inserted regis_observations rows: {len(new_ids)}")

    print("\n[5] Cleaning up smoke-test rows...")
    deleted = _cleanup(new_ids)
    print(f"  deleted {deleted} regis_observations + embedding mirror rows.")

    print("\n=== Sleep Observer smoke test complete ===")
    return 0


def _ids_for_session(session_id: str) -> list[str]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text FROM regis_observations
            WHERE source = 'sleep_observer'
              AND context->>'session_id' = %s
            """,
            (session_id,),
        )
        return [r[0] for r in cur.fetchall()]


if __name__ == "__main__":
    sys.exit(main())
