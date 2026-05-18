"""Voice REPL for Daybook chat.

Press ENTER to start recording, ENTER again to stop. Transcribe locally
via Whisper, route through chat.handler.handle_user_message, print
Regis's reply, then speak it via inference.audio.speak (if Phase 1 has
landed; otherwise just print).

Usage:
    python -m chat.voice_cli                  # interactive voice REPL
    python -m chat.voice_cli --new            # forces new conversation
    python -m chat.voice_cli --conversation <uuid>
    python -m chat.voice_cli --no-speak       # transcribe input + print response only
    python -m chat.voice_cli --max-seconds 60 # raise max recording window
"""
from __future__ import annotations

import argparse
import sys
from textwrap import indent

from . import _paths  # noqa: F401
from llm import ChatClient  # noqa: E402
from llm.stt import record_and_transcribe  # noqa: E402

from .conversation import (
    create_conversation,
    end_conversation,
    most_recent_conversation_within,
)
from .handler import handle_user_message

RESUME_WINDOW_MINUTES = 30

try:
    from inference.audio import speak as _speak
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    _speak = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chat.voice_cli")
    parser.add_argument("--new", action="store_true", help="Start a fresh conversation")
    parser.add_argument(
        "--conversation",
        metavar="UUID",
        help="Resume a specific conversation by id",
    )
    parser.add_argument(
        "--user",
        default=_paths.DEFAULT_USER_ID,
        help="user_id (default: Aakash)",
    )
    parser.add_argument(
        "--no-speak",
        action="store_true",
        help="Print Regis's reply instead of speaking it (useful before TTS lands)",
    )
    parser.add_argument(
        "--max-seconds",
        type=int,
        default=30,
        help="Max mic recording window per turn (default 30)",
    )
    args = parser.parse_args(argv)

    user_id = args.user
    if args.conversation:
        conversation_id = args.conversation
        kind = "resumed (explicit)"
    elif args.new:
        conversation_id = create_conversation(user_id=user_id)
        kind = "new (forced)"
    else:
        existing = most_recent_conversation_within(user_id, minutes=RESUME_WINDOW_MINUTES)
        if existing:
            conversation_id = existing
            kind = f"resumed (within {RESUME_WINDOW_MINUTES}m)"
        else:
            conversation_id = create_conversation(user_id=user_id)
            kind = "new"

    client = ChatClient.auto()
    speak_enabled = AUDIO_AVAILABLE and not args.no_speak

    print(
        f"[Daybook voice chat — Regis | model: {client.model} ({client.backend}) | "
        f"conversation: {conversation_id[:8]}... ({kind})]"
    )
    audio_note = "ON" if speak_enabled else ("OFF (--no-speak)" if args.no_speak else "OFF (inference.audio unavailable)")
    print(f"[voice out: {audio_note}]")
    print("(Ctrl-C to quit. Type /end on a prompt to close conversation. Press ENTER to begin a turn.)")
    print()

    try:
        while True:
            if not _wait_for_first_enter():
                break

            print("[recording...]")
            try:
                rec = record_and_transcribe(
                    max_seconds=args.max_seconds,
                    prompt="",
                    show_progress=False,
                )
            except KeyboardInterrupt:
                print("\n[aborted]")
                break
            except Exception as e:
                print(f"[recording failed: {e}]", file=sys.stderr)
                continue

            print("[transcribing...]")
            user_text = rec.text.strip()
            if not user_text:
                print("[no speech detected — try again]")
                continue
            print(f"You: {user_text}")

            if user_text in {"/quit", "/exit"}:
                break
            if user_text == "/end":
                end_conversation(conversation_id=conversation_id)
                print("[conversation ended]")
                break

            print("[Regis is thinking...]")
            try:
                resp = handle_user_message(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_text=user_text,
                    client=client,
                )
            except Exception as e:
                print(f"\n[error]: {e}\n", file=sys.stderr)
                continue

            print()
            print("Regis:")
            print(indent(resp.text, "  "))
            print()

            if speak_enabled:
                print("[speaking...]")
                try:
                    _speak(resp.text, mode="companion")
                except Exception as e:
                    print(f"[speak failed (continuing): {e}]", file=sys.stderr)
    except KeyboardInterrupt:
        print()

    return 0


def _wait_for_first_enter() -> bool:
    """Prompt to start a turn. Returns False on EOF/Ctrl-D."""
    try:
        input("[Press ENTER to speak. Press ENTER again to stop.]")
    except EOFError:
        print()
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
