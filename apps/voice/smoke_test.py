"""End-to-end voice-loop smoke with mocked mic/compose/TTS. No hardware needed."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

APPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(APPS / "inference"))

from voice.loop import run_turn


@dataclass
class _Composed:
    text: str
    mode: str


def main() -> int:
    spoken: list[tuple[str, str]] = []

    # 1. A real message routes through compose + speak.
    r = run_turn(
        user_id="smoke",
        transcribe=lambda: "Regis, how am I doing after this long stretch of work",
        compose=lambda **k: _Composed("Steady. You've earned a pause.", "companion"),
        speak_fn=lambda text, *, mode: spoken.append((text, mode)),
    )
    assert r.spoken and r.mode == "companion", r
    assert spoken == [("Steady. You've earned a pause.", "companion")], spoken

    # 2. A dismiss command short-circuits.
    r2 = run_turn(
        user_id="smoke",
        transcribe=lambda: "stop",
        compose=lambda **k: _Composed("should-not-compose", "companion"),
        speak_fn=lambda text, *, mode: spoken.append((text, mode)),
    )
    assert not r2.spoken and r2.intent == "dismiss", r2
    assert len(spoken) == 1, "dismiss must not speak"

    print("OK -- voice loop smoke passed (message routed, dismiss short-circuited).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
