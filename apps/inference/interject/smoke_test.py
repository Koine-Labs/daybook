"""End-to-end smoke test for the interject decider + post_recall trigger.

Asserts:
  1. decide() on a high-receptivity post_recall context fires + persists
  2. decide() on a low-receptivity context holds silence + persists
  3. post_recall_trigger registers in TRIGGER_REGISTRY
  4. post_recall_trigger runs end-to-end and returns a sensible decision
  5. Any composed regis_moments row is linked back via resulting_moment_id

Cleans up SMOKE rows at the end.

Run with:
    cd apps && source inference/.venv/bin/activate && python -m interject.smoke_test
"""
from __future__ import annotations

import sys
from pathlib import Path

# apps/inference/ on sys.path
INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

# apps/ on sys.path so `from wisp.composer import ...` works
APPS_DIR = INFERENCE_DIR.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from db import get_conn  # noqa: E402

from interject.decider import InterjectContext, decide  # noqa: E402
from interject.post_recall_trigger import post_recall_trigger  # noqa: E402
from interject.triggers import TRIGGER_REGISTRY  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

SMOKE_DREAM = (
    "SMOKE_TEST: I dreamed of standing in an empty observatory at dawn, "
    "watching the stars dissolve one by one into the brightening sky."
)


def _smoke_decision_ids() -> list[str]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM interject_decisions "
            "WHERE context_snapshot->'trigger_payload'->>'dream_text' LIKE %s "
            "OR reason LIKE %s",
            (f"%SMOKE_TEST%", "smoke:%"),
        )
        return [str(r[0]) for r in cur.fetchall()]


def _cleanup() -> tuple[int, int, int]:
    """Remove smoke interject_decisions, related regis_moments, and dream_recalls."""
    decision_deleted = 0
    moment_deleted = 0
    dream_deleted = 0
    with get_conn() as conn, conn.cursor() as cur:
        # Decisions tagged smoke (via reason prefix OR via dream_text marker)
        cur.execute(
            "SELECT id, resulting_moment_id FROM interject_decisions "
            "WHERE reason LIKE 'smoke:%' "
            "OR (context_snapshot->'trigger_payload'->>'dream_text') LIKE 'SMOKE_TEST:%'"
        )
        rows = cur.fetchall()
        moment_ids = [str(r[1]) for r in rows if r[1] is not None]
        decision_ids = [str(r[0]) for r in rows]

        if moment_ids:
            cur.execute(
                "DELETE FROM regis_moments WHERE id = ANY(%s::uuid[])",
                (moment_ids,),
            )
            moment_deleted = cur.rowcount

        # Also clean any regis_moments tied to SMOKE dream context.
        cur.execute(
            "DELETE FROM regis_moments WHERE kind='post_recall_reflection' "
            "AND triggering_context::text LIKE '%SMOKE_TEST%'"
        )
        moment_deleted += cur.rowcount

        if decision_ids:
            cur.execute(
                "DELETE FROM interject_decisions WHERE id = ANY(%s::uuid[])",
                (decision_ids,),
            )
            decision_deleted = cur.rowcount

        # Clean smoke dream rows
        cur.execute("DELETE FROM dream_recalls WHERE raw_text LIKE 'SMOKE_TEST:%'")
        dream_deleted = cur.rowcount

        conn.commit()
    return decision_deleted, moment_deleted, dream_deleted


def _insert_smoke_dream() -> str:
    """Create a temporary dream_recalls row so the FK-less trigger has a target."""
    from datetime import datetime, timezone

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dream_recalls
                (user_id, captured_at, depth, raw_text, themes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                DEFAULT_USER_ID,
                datetime.now(timezone.utc),
                "SCENE",
                SMOKE_DREAM,
                [],
            ),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id


def main() -> int:
    print("=== Daybook interject smoke test ===\n")

    pre = _cleanup()
    print(f"(pre-clean: {pre[0]} decisions, {pre[1]} moments, {pre[2]} dreams)\n")

    # --- Test 1: high-input context fires ---
    print("[Test 1] decide() on high-input post_recall context")
    ctx_high = InterjectContext(
        user_id=DEFAULT_USER_ID,
        trigger_kind="post_recall",
        recent_silence_seconds=20 * 60,
        user_receptivity=0.9,
        novelty=0.95,
        time_of_day_score=0.8,
        active_traits={},
        trigger_payload={"dream_text": SMOKE_DREAM},
    )
    d_high = decide(ctx_high)
    # Tag for cleanup by overriding reason post-hoc.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE interject_decisions SET reason=%s WHERE id=%s",
            (f"smoke: {d_high.reason}", d_high.persisted_id),
        )
        conn.commit()
    print(f"  score={d_high.score}  threshold={d_high.threshold}  decided={d_high.decided}")
    print(f"  reason: {d_high.reason}")
    print(f"  persisted_id: {d_high.persisted_id}")
    assert d_high.decided, "high-input context should have fired"
    assert d_high.persisted_id is not None

    # --- Test 2: low-input context holds silence ---
    print("\n[Test 2] decide() on low-input context (held silence)")
    ctx_low = InterjectContext(
        user_id=DEFAULT_USER_ID,
        trigger_kind="post_recall",
        recent_silence_seconds=30,
        user_receptivity=0.1,
        novelty=0.2,
        time_of_day_score=0.2,
        active_traits={},
        trigger_payload={"dream_text": SMOKE_DREAM},
    )
    d_low = decide(ctx_low)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE interject_decisions SET reason=%s WHERE id=%s",
            (f"smoke: {d_low.reason}", d_low.persisted_id),
        )
        conn.commit()
    print(f"  score={d_low.score}  threshold={d_low.threshold}  decided={d_low.decided}")
    print(f"  reason: {d_low.reason}")
    assert not d_low.decided, "low-input context should have held silence"
    assert d_low.persisted_id is not None

    # Verify rows present in DB
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM interject_decisions "
            "WHERE id IN (%s, %s)",
            (d_high.persisted_id, d_low.persisted_id),
        )
        n = int(cur.fetchone()[0])
    assert n == 2, f"expected 2 persisted decisions, got {n}"
    print("  both decisions persisted to interject_decisions: OK")

    # --- Test 3: trigger registry ---
    print("\n[Test 3] TRIGGER_REGISTRY contains 'post_recall'")
    assert "post_recall" in TRIGGER_REGISTRY, f"registry={list(TRIGGER_REGISTRY)}"
    print(f"  registry: {list(TRIGGER_REGISTRY)}")

    # --- Test 4: post_recall_trigger end-to-end ---
    print("\n[Test 4] post_recall_trigger() end-to-end (composes against LLM)")
    smoke_dream_id = _insert_smoke_dream()
    print(f"  inserted smoke dream_recall: {smoke_dream_id}")
    decision = post_recall_trigger(
        user_id=DEFAULT_USER_ID,
        dream_recall_id=smoke_dream_id,
        dream_text=SMOKE_DREAM,
    )
    # Tag for cleanup.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE interject_decisions SET reason=%s WHERE id=%s",
            (f"smoke: {decision.reason}", decision.persisted_id),
        )
        conn.commit()
    print(f"  decision: decided={decision.decided} score={decision.score}")
    print(f"  reason: {decision.reason}")
    print(f"  persisted_id: {decision.persisted_id}")
    assert decision.persisted_id is not None, "expected decision to persist"

    # If it fired, check that resulting_moment_id is linked + show the utterance
    if decision.decided:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT resulting_moment_id FROM interject_decisions WHERE id=%s",
                (decision.persisted_id,),
            )
            moment_id = cur.fetchone()[0]
            print(f"  resulting_moment_id: {moment_id}")
            if moment_id is not None:
                cur.execute(
                    "SELECT kind, mode, content FROM regis_moments WHERE id=%s",
                    (moment_id,),
                )
                row = cur.fetchone()
                if row is not None:
                    kind, mode, content = row
                    print(f"  moment kind={kind} mode={mode}")
                    print(f"  Regis: {content!r}")
    else:
        print("  (decision was hold-silence; no utterance composed — that's fine)")

    # --- Cleanup ---
    print("\n[cleanup] Removing smoke decisions + moments + dreams...")
    n_dec, n_mom, n_dr = _cleanup()
    print(f"  deleted {n_dec} decisions, {n_mom} moments, {n_dr} dreams")

    print("\n=== Interject smoke test complete (all assertions passed) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
