from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

APPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(APPS / "inference"))

from voice.loop import run_turn


@dataclass
class _FakeComposed:
    text: str
    mode: str


def test_run_turn_speaks_composed_reply():
    spoken = {}

    def fake_compose(**kwargs):
        assert kwargs["explicit_context"] == "Regis how am I doing today really"
        return _FakeComposed(text="You're holding steady.", mode="companion")

    def fake_speak(text, *, mode):
        spoken["text"] = text
        spoken["mode"] = mode

    result = run_turn(
        user_id="u1",
        transcribe=lambda: "Regis how am I doing today really",
        compose=fake_compose,
        speak_fn=fake_speak,
    )

    assert result.spoken is True
    assert result.utterance_text == "You're holding steady."
    assert result.mode == "companion"
    assert spoken == {"text": "You're holding steady.", "mode": "companion"}


def test_run_turn_dismiss_short_circuits():
    called = {"composed": False, "spoke": False}

    def fake_compose(**kwargs):
        called["composed"] = True
        return _FakeComposed(text="x", mode="companion")

    def fake_speak(text, *, mode):
        called["spoke"] = True

    result = run_turn(
        user_id="u1",
        transcribe=lambda: "stop",
        compose=fake_compose,
        speak_fn=fake_speak,
    )

    assert result.spoken is False
    assert result.intent == "dismiss"
    assert called == {"composed": False, "spoke": False}


def test_run_turn_empty_transcript_no_compose():
    result = run_turn(
        user_id="u1",
        transcribe=lambda: "   ",
        compose=lambda **k: _FakeComposed("x", "companion"),
        speak_fn=lambda text, *, mode: None,
    )
    assert result.spoken is False
    assert result.transcript == ""
