"""Mood capture: write a valence+arousal report, optionally embed notes.

CLI:
    python -m mood.capture --valence 0.3 --arousal -0.5 --notes "tired but content"
    python -m mood.capture                       # interactive prompts
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parent.parent
INFERENCE_DIR = APPS_DIR / "inference"
for p in (APPS_DIR, INFERENCE_DIR):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from db import get_conn  # noqa: E402
from embeddings import embed, embed_and_store  # noqa: E402
from imodels import log_novelty_observation  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def log_mood(
    *,
    user_id: str,
    valence: float,
    arousal: float,
    notes: str = "",
) -> dict:
    """Write mood_reports row; if notes non-empty, also embed (source_type='mood')."""
    valence = float(valence)
    arousal = float(arousal)
    if not -1.0 <= valence <= 1.0:
        raise ValueError(f"valence {valence} outside [-1, 1]")
    if not -1.0 <= arousal <= 1.0:
        raise ValueError(f"arousal {arousal} outside [-1, 1]")
    notes = (notes or "").strip()

    reported_at = datetime.now(timezone.utc)
    mood_id = _insert_mood(
        user_id=user_id,
        reported_at=reported_at,
        valence=valence,
        arousal=arousal,
        notes=notes or None,
    )

    embedding_id: str | None = None
    embed_error: str | None = None
    if notes:
        try:
            embedding_id = embed_and_store(
                user_id=user_id,
                source_type="mood",
                source_id=mood_id,
                text=notes,
            )
        except Exception as e:
            embed_error = str(e)
            logger.warning("Embedding failed (continuing): %s", e)

        # Novelty signal: mood notes are direct user-state evidence. Only
        # logged if notes exist (numeric valence/arousal alone has no
        # embedding to compare). Never block on failure.
        if embedding_id is not None:
            try:
                mood_vec = embed(notes)
                log_novelty_observation(
                    user_id=user_id,
                    state_snapshot={
                        "source_type": "mood",
                        "source_id": mood_id,
                        "valence": valence,
                        "arousal": arousal,
                        "text_preview": notes[:200],
                    },
                    embedding=mood_vec,
                )
            except Exception as e:
                logger.warning("novelty logging failed (mood): %s", e)

    return {
        "mood_id": mood_id,
        "embedding_id": embedding_id,
        "reported_at": reported_at,
        "valence": valence,
        "arousal": arousal,
        "notes": notes,
        "embed_error": embed_error,
    }


def _insert_mood(
    *,
    user_id: str,
    reported_at: datetime,
    valence: float,
    arousal: float,
    notes: str | None,
) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mood_reports (user_id, reported_at, valence, arousal, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, reported_at, valence, arousal, notes),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id


def _cli() -> int:
    parser = argparse.ArgumentParser(
        prog="mood.capture",
        description="Log a mood report (valence + arousal in [-1, 1] + optional notes).",
    )
    parser.add_argument("--valence", type=float, help="Valence in [-1, 1].")
    parser.add_argument("--arousal", type=float, help="Arousal in [-1, 1].")
    parser.add_argument("--notes", type=str, default="", help="Free-text notes (optional).")
    parser.add_argument("--user-id", type=str, default=DEFAULT_USER_ID, help="User UUID (default: Aakash).")
    args = parser.parse_args()

    try:
        valence = args.valence if args.valence is not None else _prompt_float("valence (-1..1): ")
        arousal = args.arousal if args.arousal is not None else _prompt_float("arousal (-1..1): ")
        notes = args.notes if args.notes else _prompt_optional("notes (optional, ENTER to skip): ")
    except (KeyboardInterrupt, EOFError):
        print()
        return 1
    except ValueError as e:
        print(f"invalid input: {e}", file=sys.stderr)
        return 1

    try:
        result = log_mood(
            user_id=args.user_id,
            valence=valence,
            arousal=arousal,
            notes=notes,
        )
    except Exception as e:
        print(f"mood log failed: {e}", file=sys.stderr)
        return 1

    print()
    print(f"mood_id:      {result['mood_id']}")
    print(f"reported_at:  {result['reported_at'].isoformat()}")
    print(f"valence:      {result['valence']:+.2f}")
    print(f"arousal:      {result['arousal']:+.2f}")
    if result["notes"]:
        print(f"notes:        {result['notes']!r}")
        print(f"embedding_id: {result['embedding_id'] or '(skipped: ' + (result['embed_error'] or '?') + ')'}")
    else:
        print("notes:        (none, no embedding)")
    return 0


def _prompt_float(label: str) -> float:
    raw = input(label).strip()
    return float(raw)


def _prompt_optional(label: str) -> str:
    return input(label).strip()


if __name__ == "__main__":
    sys.exit(_cli())
