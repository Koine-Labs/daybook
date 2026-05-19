"""End-to-end smoke test: compose Regis utterances using the full stack.

Tests four moments across both modes. For one of them, seeds the embeddings
table with a fake "intent" so retrieval has something to find.

Run with:
    cd apps/wisp && PYTHONPATH=. python -m smoke_test
    # OR
    cd apps && python -m wisp.smoke_test
"""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

# Allow `python -m wisp.smoke_test` from apps/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wisp.composer import compose_utterance  # noqa: E402

# Inference dir for db helper + embeddings store
INFERENCE_DIR = Path(__file__).resolve().parent.parent / "inference"
sys.path.insert(0, str(INFERENCE_DIR))
from db import get_conn  # noqa: E402
from embeddings.store import embed_and_store  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def main() -> int:
    print("=== Daybook Regis composer smoke test ===\n")

    # Seed a few "intent" embeddings so retrieval has stuff to find on Test 4.
    print("Seeding 3 fake intents into embeddings table (will clean up at end)...")
    seed_intents = [
        "remember the colors tonight",
        "soft body, soft mind. let go of the meeting",
        "find the house. the one with the yellow door",
    ]
    seeded_eids: list[str] = []
    seeded_sids: list[str] = []
    for txt in seed_intents:
        sid = str(uuid4())
        seeded_sids.append(sid)
        eid, _vec = embed_and_store(
            user_id=DEFAULT_USER_ID,
            source_type="intent_smoke",
            source_id=sid,
            text=txt,
        )
        seeded_eids.append(eid)
    print(f"  Seeded {len(seeded_eids)} embeddings.\n")

    # --- Test 1: Witness Mode REM whisper ---
    print("[Test 1] Witness Mode — first REM cue of the night.")
    c1 = compose_utterance(
        user_id=DEFAULT_USER_ID,
        moment_kind="rem_whisper",
        explicit_context=(
            "First REM cue. P(REM)=0.78. Sustained 90s. 2:30 AM. "
            "This is cue #1 of the night."
        ),
        retrieval_source_types=["intent_smoke"],
    )
    print(f"  mode: {c1.mode}")
    print(f"  composed in {c1.composition_seconds*1000:.0f}ms")
    print(f"  retrieved {len(c1.retrieved)} memories (top sim: {max((r['similarity'] for r in c1.retrieved if 'similarity' in r), default=0):.3f})")
    print(f"  Regis: {c1.text!r}\n")

    # --- Test 2: Companion Mode pre-sleep greeting ---
    print("[Test 2] Companion Mode — pre-sleep greeting.")
    c2 = compose_utterance(
        user_id=DEFAULT_USER_ID,
        moment_kind="pre_sleep_greeting",
        explicit_context="User tapped 'begin' on bedside display. 22:48. Last night was poor.",
        retrieval_source_types=["intent_smoke"],
    )
    print(f"  mode: {c2.mode}")
    print(f"  Regis: {c2.text!r}\n")

    # --- Test 3: Companion Mode morning recall ---
    print("[Test 3] Companion Mode — morning recall prompt.")
    c3 = compose_utterance(
        user_id=DEFAULT_USER_ID,
        moment_kind="morning_recall_prompt",
        explicit_context=(
            "07:42 AM. User stably awake 80 seconds. Two REM cues fired overnight, both inside REM windows."
        ),
        retrieval_query="last night's intent",
        retrieval_source_types=["intent_smoke"],
    )
    print(f"  mode: {c3.mode}")
    print(f"  retrieved {len(c3.retrieved)} relevant intents")
    for r in c3.retrieved[:3]:
        print(f"    sim={r.get('similarity', 0):.3f}  {r.get('source_id','')[:8]}")
    print(f"  Regis: {c3.text!r}\n")

    # --- Test 4: Companion Mode w/ retrieval-influenced context ---
    print("[Test 4] Companion Mode — wake greeting that should reference an intent.")
    c4 = compose_utterance(
        user_id=DEFAULT_USER_ID,
        moment_kind="morning_recall_prompt",
        explicit_context=(
            "06:55 AM. User awake 90s. Last night's intent (most recent): 'find the house. the one with the yellow door'. "
            "Two REM cues fired, both landed inside REM windows."
        ),
        retrieval_query="finding a house with a yellow door, returning home",
        retrieval_source_types=["intent_smoke"],
    )
    print(f"  mode: {c4.mode}")
    print(f"  retrieved {len(c4.retrieved)} relevant memories")
    for r in c4.retrieved[:3]:
        print(f"    sim={r.get('similarity', 0):.3f}  {r.get('source_type', '')}")
    print(f"  Regis: {c4.text!r}\n")

    # Cleanup
    print("Cleaning up seeded embeddings...")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM embeddings WHERE source_type = 'intent_smoke'")
        deleted = cur.rowcount
        conn.commit()
    print(f"  Deleted {deleted} seeded rows.")
    print("\n=== Composer smoke test complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
