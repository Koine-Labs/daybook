"""Intent capture: write a pre-sleep intent + embed it.

CLI:
    python -m intent.capture --text "remember the colors tonight"
    python -m intent.capture                    # interactive: prompts for text
    python -m intent.capture --voice            # interactive: records via mic + transcribes
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
from embeddings import embed_and_store  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def set_intent(
    *,
    user_id: str,
    text: str,
    target_session_id: str | None = None,
) -> dict:
    """Write to intents table + embed text into embeddings (source_type='intent')."""
    text = text.strip()
    if not text:
        raise ValueError("intent text is empty")

    set_at = datetime.now(timezone.utc)
    intent_id = _insert_intent(
        user_id=user_id,
        set_at=set_at,
        intent_text=text,
        target_session_id=target_session_id,
    )

    embedding_id: str | None = None
    embed_error: str | None = None
    try:
        embedding_id = embed_and_store(
            user_id=user_id,
            source_type="intent",
            source_id=intent_id,
            text=text,
        )
    except Exception as e:
        embed_error = str(e)
        logger.warning("Embedding failed (continuing): %s", e)

    return {
        "intent_id": intent_id,
        "embedding_id": embedding_id,
        "set_at": set_at,
        "text": text,
        "target_session_id": target_session_id,
        "embed_error": embed_error,
    }


def _insert_intent(
    *,
    user_id: str,
    set_at: datetime,
    intent_text: str,
    target_session_id: str | None,
) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO intents (user_id, set_at, intent_text, target_session_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, set_at, intent_text, target_session_id),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id


def _cli() -> int:
    parser = argparse.ArgumentParser(
        prog="intent.capture",
        description="Capture a pre-sleep (or anytime) intent.",
    )
    parser.add_argument("--text", type=str, help="Intent text (skip prompt).")
    parser.add_argument("--voice", action="store_true", help="Record via mic + transcribe.")
    parser.add_argument("--target-session", type=str, default=None, help="Optional sleep_sessions.id to attach.")
    parser.add_argument("--user-id", type=str, default=DEFAULT_USER_ID, help="User UUID (default: Aakash).")
    parser.add_argument("--max-seconds", type=int, default=30, help="Max mic record duration in voice mode.")
    args = parser.parse_args()

    try:
        text = _resolve_text(args)
    except KeyboardInterrupt:
        print()
        return 1
    except Exception as e:
        print(f"intent capture failed during input: {e}", file=sys.stderr)
        return 1

    try:
        result = set_intent(
            user_id=args.user_id,
            text=text,
            target_session_id=args.target_session,
        )
    except Exception as e:
        print(f"intent capture failed: {e}", file=sys.stderr)
        return 1

    print()
    print(f"intent_id:    {result['intent_id']}")
    print(f"embedding_id: {result['embedding_id'] or '(skipped: ' + (result['embed_error'] or '?') + ')'}")
    print(f"set_at:       {result['set_at'].isoformat()}")
    if result["target_session_id"]:
        print(f"target_session: {result['target_session_id']}")
    print(f"text:         {result['text']!r}")
    return 0


def _resolve_text(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.voice:
        from llm.stt import record_and_transcribe

        print(f"[Press ENTER to start recording. Press ENTER again to stop (max {args.max_seconds}s).]")
        try:
            input()
        except EOFError:
            pass
        print("[recording...]")
        rec = record_and_transcribe(
            max_seconds=args.max_seconds,
            prompt="",
            show_progress=True,
        )
        print(f"[transcribed in {rec.transcribe_seconds:.1f}s]")
        print(f"Transcript: {rec.text!r}")
        return rec.text
    try:
        text = input("intent: ").strip()
    except EOFError:
        return ""
    return text


if __name__ == "__main__":
    sys.exit(_cli())
