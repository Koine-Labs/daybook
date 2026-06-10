"""Smoke test for the wake_word package.

Asserts:
  1. Command-intent classifier hits expected labels on canonical phrases
  2. Long utterances default to NONE (treated as chat message)
  3. WakeEvent dataclass round-trips
  4. VoiceWakeWordDetector loads the openWakeWord model and returns no event on silence

Skips live mic capture (requires human-at-mic). The command-dispatch handlers
(LISTEN/SEE/DISMISS -> user_actions) are deferred in Week 2: handlers.py needs the
`gesture` layer, which the rebuild scrap removed. classify_intent() alone is enough
to route a 'stop'/'dismiss' command vs a real message in the voice loop.

Run:
    cd apps && source inference/.venv/bin/activate && python -m wake_word.smoke_test
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

APPS_DIR = Path(__file__).resolve().parent.parent.parent
INFERENCE_DIR = APPS_DIR / "inference"
for _p in (APPS_DIR, INFERENCE_DIR):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from wake_word import (  # noqa: E402
    CommandIntent,
    VoiceWakeWordDetector,
    WakeEvent,
    classify_intent,
)

CLASSIFIER_CASES: list[tuple[str, CommandIntent]] = [
    ("listen", CommandIntent.LISTEN),
    ("pay attention", CommandIntent.LISTEN),
    ("look at this", CommandIntent.SEE),
    ("see this", CommandIntent.SEE),
    ("shut up", CommandIntent.DISMISS),
    ("be quiet", CommandIntent.DISMISS),
    ("go on", CommandIntent.ACKNOWLEDGE),
    ("yeah", CommandIntent.ACKNOWLEDGE),
    ("scratch that", CommandIntent.SCRATCH_THAT),
    ("never mind", CommandIntent.SCRATCH_THAT),
    ("tell me about my sleep last night and how it compares", CommandIntent.NONE),
    ("what did I dream about", CommandIntent.NONE),
    ("", CommandIntent.NONE),
]


def test_classifier() -> None:
    print("[Test 1] classify_intent() — keyword cases")
    failures: list[str] = []
    for text, expected in CLASSIFIER_CASES:
        got = classify_intent(text)
        marker = "OK" if got == expected else "FAIL"
        print(f"  [{marker}] {text!r:60s} -> {got.value:11s} (expected {expected.value})")
        if got != expected:
            failures.append(f"{text!r}: got {got.value}, expected {expected.value}")
    assert not failures, "classifier mismatches:\n  " + "\n  ".join(failures)


def test_wake_event_roundtrip() -> None:
    print("\n[Test 2] WakeEvent dataclass round-trips")
    ev = WakeEvent(
        detected_at=datetime.now(timezone.utc),
        source="voice_wake_word",
        confidence=0.83,
        raw_audio=b"\x00\x00",
        metadata={"wake_word": "hey_jarvis"},
    )
    assert ev.source == "voice_wake_word"
    assert 0.0 <= ev.confidence <= 1.0
    assert ev.metadata["wake_word"] == "hey_jarvis"
    print(f"  OK  source={ev.source} confidence={ev.confidence}")


def test_wake_word_detector_loads() -> None:
    if importlib.util.find_spec("openwakeword") is None:
        import pytest
        pytest.skip("[voice] extra not installed (openwakeword)")
    print("\n[Test 3] VoiceWakeWordDetector loads + returns None on silence")
    detector = VoiceWakeWordDetector(wake_word="hey_jarvis", threshold=0.5)
    model = detector.get_model()
    assert model is not None
    silence = np.zeros(1280, dtype=np.int16)
    ev = detector.process_audio_chunk(silence, sample_rate=16000)
    assert ev is None, f"expected no detection on silence, got {ev}"
    for _ in range(4):
        ev = detector.process_audio_chunk(silence, sample_rate=16000)
        assert ev is None
    print("  OK  model loaded, silence -> no event")


def main() -> int:
    print("=== Daybook wake_word smoke test ===\n")
    test_classifier()
    test_wake_event_roundtrip()
    test_wake_word_detector_loads()
    print("\n=== wake_word smoke test complete (all assertions passed) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
