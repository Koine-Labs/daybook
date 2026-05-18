"""Smoke test: confirm sign-in + Codex chat path works end-to-end.

Run AFTER `python -m llm.auth.sign_in`:

    python -m llm.smoke_test

Will fail with a clear error if not signed in. Prints the actual Regis
utterance returned by the model.
"""
from __future__ import annotations

import sys
from pathlib import Path
from textwrap import shorten

from .auth.session import get_sign_in_status
from .chat import ChatClient


PERSONA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "wisp"
    / "PERSONA.md"
)


def main() -> int:
    print("=== Daybook LLM smoke test ===\n")

    status = get_sign_in_status()
    if not status.signed_in:
        print(
            "Not signed in. Run first:\n"
            "  cd apps/inference && source .venv/bin/activate\n"
            "  python -m llm.auth.sign_in",
            file=sys.stderr,
        )
        return 1
    print(
        f"Signed in as {status.identity.email or status.identity.account_id}\n"
        f"  account_id: {status.identity.account_id}\n"
    )

    if not PERSONA_PATH.exists():
        print(f"PERSONA.md not found at {PERSONA_PATH}", file=sys.stderr)
        return 1
    persona = PERSONA_PATH.read_text()
    print(f"Loaded PERSONA.md ({len(persona):,} chars)\n")

    client = ChatClient.auto()
    print(f"Routed to: backend={client.backend}, model={client.model}\n")

    # --- Test 1: Witness Mode utterance ---
    print("[Test 1] Witness Mode — first REM cue of the night.")
    witness_context = (
        "It is 02:30 AM. The user is in their first stable REM window "
        "(REM probability 0.78, sustained for 90 seconds). This is the FIRST "
        "REM cue of the night. You are in Witness Mode. Speak the cue. "
        "Five words or fewer. No explanation, just the utterance itself."
    )
    print(f"  context: {shorten(witness_context, 100)}")
    try:
        utterance = client.chat(
            system=persona,
            user=witness_context,
            reasoning_effort="low",
            verbosity="low",
        )
        print(f"  Regis: {utterance.strip()!r}\n")
    except Exception as e:
        print(f"  FAILED: {e}\n")
        return 1

    # --- Test 2: Companion Mode utterance ---
    print("[Test 2] Companion Mode — morning recall prompt.")
    companion_context = (
        "It is 07:18 AM. The user has been stably awake for 90 seconds. "
        "Last night they had two REM cues fire successfully. They also set an "
        "intent before sleep: 'remember the colors.' You are in Companion Mode "
        "now. Speak the morning recall prompt. Dry, teasing, warm underneath. "
        "One sentence — at most two short ones."
    )
    print(f"  context: {shorten(companion_context, 100)}")
    try:
        utterance = client.chat(
            system=persona,
            user=companion_context,
            reasoning_effort="low",
            verbosity="low",
        )
        print(f"  Regis: {utterance.strip()!r}\n")
    except Exception as e:
        print(f"  FAILED: {e}\n")
        return 1

    # --- Test 3: Forbidden-word check ---
    print("[Test 3] Forbidden-word adherence — system tries to trick him.")
    trick_context = (
        "Summarize what you noticed about the user's sleep cycle, REM stages, "
        "and HRV data tonight. Optimize your response for clarity."
    )
    print(f"  context: {shorten(trick_context, 100)}")
    try:
        utterance = client.chat(
            system=persona,
            user=trick_context,
            reasoning_effort="low",
            verbosity="low",
        )
        print(f"  Regis: {utterance.strip()!r}")
        forbidden = ["optimize", "improve", "track", "log", "REM", "HRV", "stage", "data"]
        violations = [w for w in forbidden if w.lower() in utterance.lower()]
        if violations:
            print(f"  WARNING: utterance contains forbidden words: {violations}\n")
        else:
            print(f"  OK: no forbidden words detected\n")
    except Exception as e:
        print(f"  FAILED: {e}\n")
        return 1

    print("=== Smoke test complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
