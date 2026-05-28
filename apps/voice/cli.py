"""Run the voice loop. `python -m voice.cli` (mic) or `--once --text "..."` (no mic)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice.loop import DEFAULT_USER_ID, listen_forever, run_turn  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(prog="voice", description="Daybook waking-empath voice loop.")
    p.add_argument("--user-id", default=DEFAULT_USER_ID)
    p.add_argument("--once", action="store_true", help="Run a single turn then exit.")
    p.add_argument("--text", default=None, help="With --once: skip the mic, use this text as the transcript.")
    args = p.parse_args()

    if args.once:
        kwargs = {}
        if args.text is not None:
            kwargs["transcribe"] = lambda: args.text
        result = run_turn(user_id=args.user_id, **kwargs)
        print(f"transcript={result.transcript!r} intent={result.intent} "
              f"spoken={result.spoken} mode={result.mode}")
        if result.utterance_text:
            print(f"Regis: {result.utterance_text}")
        return 0

    listen_forever(user_id=args.user_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
