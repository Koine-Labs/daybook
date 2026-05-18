"""Smoke test for the wake_word package.

Asserts:
  1. Command-intent classifier hits expected labels on canonical phrases
  2. Long utterances default to NONE (treated as chat message)
  3. WakeEvent dataclass round-trips
  4. Each handler writes a user_actions row with kind='voice_command' + correct intent
  5. handle_scratch_that survives gracefully even with no prior regis_moments
  6. VoiceWakeWordDetector loads the openWakeWord model and returns no event on silence

Skips live mic capture (requires human-at-mic).

Run:
    cd apps && source inference/.venv/bin/activate && python -m wake_word.smoke_test
"""
from __future__ import annotations

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

from db import get_conn  # noqa: E402

from wake_word import (  # noqa: E402
    CommandIntent,
    VoiceWakeWordDetector,
    WakeEvent,
    classify_intent,
)
from wake_word import handlers  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
SMOKE_MARKER = "SMOKE_TEST_WAKE_WORD"


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


def _cleanup() -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_actions WHERE context->>'_smoke' = %s",
            (SMOKE_MARKER,),
        )
        n = cur.rowcount
        conn.commit()
    return n


def _fetch_action(action_id: str) -> tuple[str, str, str] | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT kind, source, intent FROM user_actions WHERE id = %s",
            (action_id,),
        )
        return cur.fetchone()


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


def test_handlers_db_writes() -> None:
    print("\n[Test 3] handlers write user_actions rows with correct intent")
    cases = [
        (CommandIntent.LISTEN, handlers.handle_listen),
        (CommandIntent.SEE, handlers.handle_see),
        (CommandIntent.DISMISS, handlers.handle_dismiss),
        (CommandIntent.ACKNOWLEDGE, handlers.handle_acknowledge),
        (CommandIntent.SCRATCH_THAT, handlers.handle_scratch_that),
    ]
    for intent, fn in cases:
        result = fn(
            user_id=DEFAULT_USER_ID,
            context={"_smoke": SMOKE_MARKER, "test_intent": intent.value},
        )
        assert result["ok"] is True, f"{intent.value} returned ok=False: {result}"
        action_id = result["action_id"]
        assert action_id, f"{intent.value} missing action_id"
        row = _fetch_action(action_id)
        assert row is not None, f"{intent.value}: no row written"
        kind, source, db_intent = row
        assert kind == "voice_command", f"{intent.value}: kind={kind!r}"
        assert source == "voice_command", f"{intent.value}: source={source!r}"
        assert db_intent == intent.value, (
            f"{intent.value}: db intent={db_intent!r}"
        )
        print(
            f"  OK  {intent.value:11s} id={action_id} ack={result['ack']!r}"
        )


def test_dispatch_unknown() -> None:
    print("\n[Test 4] dispatch() with NONE intent yields graceful no-op")
    result = handlers.dispatch(
        CommandIntent.NONE,
        user_id=DEFAULT_USER_ID,
        context={"_smoke": SMOKE_MARKER},
    )
    assert result["ok"] is False, f"unexpected ok=True for NONE: {result}"
    print(f"  OK  result={result}")


def test_wake_word_detector_loads() -> None:
    print("\n[Test 5] VoiceWakeWordDetector loads + returns None on silence")
    detector = VoiceWakeWordDetector(wake_word="hey_jarvis", threshold=0.5)
    model = detector.get_model()
    assert model is not None
    silence = np.zeros(1280, dtype=np.int16)
    ev = detector.process_audio_chunk(silence, sample_rate=16000)
    assert ev is None, f"expected no detection on silence, got {ev}"
    # Repeated calls also fine
    for _ in range(4):
        ev = detector.process_audio_chunk(silence, sample_rate=16000)
        assert ev is None
    print(f"  OK  model loaded, silence -> no event")


def main() -> int:
    print("=== Daybook wake_word smoke test ===\n")
    pre = _cleanup()
    if pre:
        print(f"(pre-clean: removed {pre} stale user_actions)\n")

    try:
        test_classifier()
        test_wake_event_roundtrip()
        test_handlers_db_writes()
        test_dispatch_unknown()
        test_wake_word_detector_loads()
    finally:
        print("\n[cleanup] removing SMOKE user_actions rows...")
        n = _cleanup()
        print(f"  deleted {n} rows")

    print("\n=== wake_word smoke test complete (all assertions passed) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
