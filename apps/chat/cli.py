"""Interactive REPL.

Usage:
    cd apps && python -m chat.cli                       # resume if recent, else new
    cd apps && python -m chat.cli --new                 # force fresh conversation
    cd apps && python -m chat.cli --conversation <uuid> # resume specific id
"""
from __future__ import annotations

import argparse
import sys
from textwrap import indent

from . import _paths  # noqa: F401
from llm import ChatClient  # noqa: E402

from .conversation import (
    create_conversation,
    end_conversation,
    most_recent_conversation_within,
)
from .handler import handle_user_message

RESUME_WINDOW_MINUTES = 30


COMMANDS = {"/quit", "/exit", "/new", "/clear", "/help", "/end"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chat.cli")
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
    print(
        f"[Daybook chat — Regis | model: {client.model} ({client.backend}) | "
        f"conversation: {conversation_id[:8]}... ({kind})]"
    )
    print("(type /quit to exit, /new for fresh conversation, /clear to clear screen, /help for commands)")
    print()

    while True:
        try:
            user_text = input("> You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not user_text:
            continue

        if user_text in COMMANDS:
            if user_text in {"/quit", "/exit"}:
                break
            if user_text == "/new":
                conversation_id = create_conversation(user_id=user_id)
                print(f"\n[new conversation: {conversation_id[:8]}...]\n")
                continue
            if user_text == "/end":
                end_conversation(conversation_id=conversation_id)
                print("[conversation ended]")
                break
            if user_text == "/clear":
                print("\033[2J\033[H", end="")
                continue
            if user_text == "/help":
                print("commands: /quit /exit /new /end /clear /help")
                continue

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
        if resp.observation_extracted:
            print(f"\n  (noted: {resp.observation_extracted})")
        if resp.trait_deltas:
            summary = ", ".join(
                f"{d['trait']}{d['delta']:+.02f}" for d in resp.trait_deltas
            )
            print(f"  (drift: {summary})")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
