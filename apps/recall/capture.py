"""Morning dream-recall capture: voice or text -> dream_recalls + embeddings + Regis ack.

CLI:
    python -m recall.capture --text "I dreamed about the ocean."
    python -m recall.capture                       # interactive mic record
    python -m recall.capture --file path/to.wav    # use existing audio
    python -m recall.capture --text "..." --no-ack # skip LLM call
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Path setup: allow `from db import ...` and `from embeddings import ...`
INFERENCE_DIR = Path(__file__).resolve().parent.parent / "inference"
sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402
from embeddings import embed_and_store  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
AUDIO_DIR = Path.home() / ".daybook" / "recall_audio"


@dataclass
class DreamCapture:
    """Result of one morning recall capture."""

    dream_recall_id: str
    embedding_id: str | None
    text: str
    depth: str  # 'NONE' | 'FRAGMENT' | 'SCENE' | 'NARRATIVE'
    voice_memo_url: str | None
    regis_utterance: str | None
    captured_at: datetime
    themes: list[str] = field(default_factory=list)
    composition_seconds: float | None = None
    embed_error: str | None = None
    compose_error: str | None = None


def depth_from_text(text: str) -> str:
    """Word-count heuristic for v0. NONE<5, FRAGMENT 5-29, SCENE 30-99, NARRATIVE>=100."""
    words = len(text.split())
    if words < 5:
        return "NONE"
    if words < 30:
        return "FRAGMENT"
    if words < 100:
        return "SCENE"
    return "NARRATIVE"


def capture(
    *,
    text: str | None = None,
    audio_path: str | Path | None = None,
    record_mic: bool = False,
    max_seconds: int = 60,
    user_id: str = DEFAULT_USER_ID,
    session_id: str | None = None,
    ack: bool = True,
    themes: list[str] | None = None,
) -> DreamCapture:
    """Capture a morning dream recall via text, audio file, or live mic.

    Exactly one of `text`, `audio_path`, or `record_mic=True` should be provided.
    Returns a DreamCapture with the dream_recalls row id + embedding id + optional
    Regis utterance.
    """
    if sum(bool(x) for x in (text, audio_path, record_mic)) != 1:
        raise ValueError(
            "capture() requires exactly one of text=, audio_path=, or record_mic=True"
        )

    voice_memo_url: str | None = None

    if record_mic:
        from .recorder import record_interactive

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        out_path = AUDIO_DIR / f"{datetime.now(timezone.utc).isoformat().replace(':','-')}.wav"
        print(f"Recording up to {max_seconds}s. Press ENTER to stop.")
        record_interactive(out_path, max_seconds=max_seconds)
        audio_path = out_path
        voice_memo_url = str(out_path)

    if audio_path:
        from .whisper_client import transcribe

        audio_path = Path(audio_path)
        if voice_memo_url is None:
            voice_memo_url = str(audio_path.resolve())
        print(f"Transcribing {audio_path.name} ...")
        text = transcribe(audio_path)
        print(f"Transcript: {text!r}")

    assert text is not None  # by construction above
    text = text.strip()
    if not text:
        raise ValueError("Captured text is empty — nothing to record.")

    captured_at = datetime.now(timezone.utc)
    depth = depth_from_text(text)

    dream_id = _insert_dream_recall(
        user_id=user_id,
        session_id=session_id,
        captured_at=captured_at,
        depth=depth,
        raw_text=text,
        voice_memo_url=voice_memo_url,
        themes=themes or [],
    )

    embedding_id: str | None = None
    dream_vec: list[float] | None = None
    embed_error: str | None = None
    try:
        embedding_id, dream_vec = embed_and_store(
            user_id=user_id,
            source_type="dream_recall",
            source_id=dream_id,
            text=text,
        )
    except Exception as e:
        embed_error = str(e)
        logger.warning("Embedding failed (continuing): %s", e)

    regis_utterance: str | None = None
    compose_error: str | None = None
    composition_seconds: float | None = None
    if ack:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from wisp.composer import compose_utterance  # noqa: E402

            composed = compose_utterance(
                user_id=user_id,
                moment_kind="capture_ack",
                explicit_context=(
                    f"User just captured a dream recall ({depth.lower()}, "
                    f"~{len(text.split())} words). Acknowledge briefly. "
                    "One sentence. Reverent. Do not summarize or interpret."
                ),
                retrieval_query=text,
                retrieval_source_types=["dream_recall"],
                retrieval_top_k=3,
                reasoning_effort="low",
                verbosity="low",
            )
            regis_utterance = composed.text
            composition_seconds = composed.composition_seconds
        except Exception as e:
            compose_error = str(e)
            logger.warning("Composer failed (continuing): %s", e)

    return DreamCapture(
        dream_recall_id=dream_id,
        embedding_id=embedding_id,
        text=text,
        depth=depth,
        voice_memo_url=voice_memo_url,
        regis_utterance=regis_utterance,
        captured_at=captured_at,
        themes=themes or [],
        composition_seconds=composition_seconds,
        embed_error=embed_error,
        compose_error=compose_error,
    )


def _insert_dream_recall(
    *,
    user_id: str,
    session_id: str | None,
    captured_at: datetime,
    depth: str,
    raw_text: str,
    voice_memo_url: str | None,
    themes: list[str],
) -> str:
    """Insert one dream_recalls row. Returns new id (UUID string)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dream_recalls
                (user_id, session_id, captured_at, depth, raw_text, voice_memo_url, themes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, session_id, captured_at, depth, raw_text, voice_memo_url, themes),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> int:
    parser = argparse.ArgumentParser(
        prog="recall.capture",
        description="Capture a morning dream recall (text, audio file, or live mic).",
    )
    parser.add_argument("--text", type=str, help="Provide dream text directly (skip audio).")
    parser.add_argument("--file", type=str, help="Transcribe an existing audio file.")
    parser.add_argument(
        "--max-seconds", type=int, default=60, help="Max mic record duration (interactive mode)."
    )
    parser.add_argument(
        "--no-ack", action="store_true", help="Skip the Regis 'Held.' LLM call."
    )
    parser.add_argument(
        "--user-id", type=str, default=DEFAULT_USER_ID, help="User UUID (default: Aakash)."
    )
    args = parser.parse_args()

    try:
        if args.text:
            result = capture(text=args.text, user_id=args.user_id, ack=not args.no_ack)
        elif args.file:
            result = capture(
                audio_path=args.file, user_id=args.user_id, ack=not args.no_ack
            )
        else:
            print("Press ENTER to start recording. Press ENTER again to stop (max 60s).")
            try:
                input()
            except EOFError:
                pass
            result = capture(
                record_mic=True,
                max_seconds=args.max_seconds,
                user_id=args.user_id,
                ack=not args.no_ack,
            )
    except Exception as e:
        print(f"capture failed: {e}", file=sys.stderr)
        return 1

    print()
    print(f"dream_recall_id: {result.dream_recall_id}")
    print(f"embedding_id:    {result.embedding_id or '(skipped: ' + (result.embed_error or '?') + ')'}")
    print(f"depth:           {result.depth}")
    print(f"captured_at:     {result.captured_at.isoformat()}")
    if result.voice_memo_url:
        print(f"voice_memo_url:  {result.voice_memo_url}")
    if result.regis_utterance:
        print(f"Regis:           {result.regis_utterance!r}")
    elif args.no_ack:
        print("Regis:           (skipped, --no-ack)")
    elif result.compose_error:
        print(f"Regis:           (failed: {result.compose_error})")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
