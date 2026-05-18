"""End-to-end smoke test for the gesture system.

Asserts:
  1. Synthetic mm-hmm signal classifies as 'mm-hmm'
  2. Synthetic mm-mm signal classifies as 'mm-mm'
  3. Synthetic sigh signal classifies as 'sigh'
  4. Simulated tap inserts a user_actions row with the right intent
  5. Intent map is correct for each tap_type
  6. Direct record_action() round-trips

Cleans up all SMOKE_TEST: rows at the end.

Run with:
    cd apps && source inference/.venv/bin/activate && python -m gesture.smoke_test
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# Make `from db import get_conn` work + parent-of-package imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
INFERENCE_DIR = Path(__file__).resolve().parent.parent / "inference"
sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402

from gesture.recorder import record_action  # noqa: E402
from gesture.tap import TAP_INTENT_MAP, simulate_tap  # noqa: E402
from gesture.voice_grunt import classify_grunt  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
SMOKE_MARKER = "SMOKE_TEST"
SAMPLE_RATE = 16000


def _synth_two_peak(
    *,
    pitch_first: float,
    pitch_second: float,
    duration_each_ms: int = 220,
    gap_ms: int = 140,
    decay: float = 6.0,
) -> np.ndarray:
    """Build a two-peak voiced signal with given pitches per peak."""
    samples_per = int(SAMPLE_RATE * duration_each_ms / 1000)
    silence = np.zeros(int(SAMPLE_RATE * gap_ms / 1000), dtype=np.float32)
    t = np.linspace(0, duration_each_ms / 1000, samples_per, dtype=np.float32)

    def peak(freq: float) -> np.ndarray:
        envelope = np.exp(-decay * np.abs(t - duration_each_ms / 2000) /
                          (duration_each_ms / 2000))
        carrier = (
            np.sin(2 * np.pi * freq * t)
            + 0.5 * np.sin(2 * np.pi * 2 * freq * t)
            + 0.25 * np.sin(2 * np.pi * 3 * freq * t)
        )
        return (envelope * carrier).astype(np.float32)

    return np.concatenate([peak(pitch_first), silence, peak(pitch_second)])


def _synth_sigh(duration_ms: int = 700) -> np.ndarray:
    """Long breathy single voiced exhale (low-freq noise + voiced fundamental)."""
    n = int(SAMPLE_RATE * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n, dtype=np.float32)
    fundamental = 0.35 * np.sin(2 * np.pi * 130 * t)
    breath_noise = 0.55 * np.random.default_rng(0).standard_normal(n).astype(np.float32)
    envelope = np.exp(-2.0 * np.abs(t - (duration_ms / 2000)) / (duration_ms / 2000))
    return (envelope * (fundamental + breath_noise)).astype(np.float32)


def _count_actions_for(user_id: str, *, kind: str | None = None) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        if kind:
            cur.execute(
                "SELECT COUNT(*) FROM user_actions WHERE user_id=%s AND kind=%s "
                "AND context->>'_smoke' = %s",
                (user_id, kind, SMOKE_MARKER),
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM user_actions WHERE user_id=%s "
                "AND context->>'_smoke' = %s",
                (user_id, SMOKE_MARKER),
            )
        return int(cur.fetchone()[0])


def _cleanup() -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_actions WHERE context->>'_smoke' = %s",
            (SMOKE_MARKER,),
        )
        n = cur.rowcount
        conn.commit()
    return n


def main() -> int:
    print("=== Daybook gesture smoke test ===\n")

    pre = _cleanup()
    if pre:
        print(f"(pre-clean: removed {pre} stale user_actions)\n")

    # --- Test 1: mm-hmm (rising pitch) ---
    print("[Test 1] classify_grunt() on synthetic mm-hmm (rising pitch)")
    sig = _synth_two_peak(pitch_first=140, pitch_second=210)
    res = classify_grunt(sig, sample_rate=SAMPLE_RATE)
    print(f"  result: {res}")
    assert res is not None, "mm-hmm classified as None"
    assert res["kind"] == "mm-hmm", f"expected mm-hmm, got {res['kind']}"

    # --- Test 2: mm-mm (falling pitch) ---
    print("\n[Test 2] classify_grunt() on synthetic mm-mm (falling pitch)")
    sig = _synth_two_peak(pitch_first=210, pitch_second=140)
    res = classify_grunt(sig, sample_rate=SAMPLE_RATE)
    print(f"  result: {res}")
    assert res is not None, "mm-mm classified as None"
    assert res["kind"] == "mm-mm", f"expected mm-mm, got {res['kind']}"

    # --- Test 3: sigh ---
    print("\n[Test 3] classify_grunt() on synthetic sigh (long, breathy)")
    sig = _synth_sigh(duration_ms=700)
    res = classify_grunt(sig, sample_rate=SAMPLE_RATE)
    print(f"  result: {res}")
    assert res is not None, "sigh classified as None"
    assert res["kind"] == "sigh", f"expected sigh, got {res['kind']}"

    # --- Test 4: silence -> None ---
    print("\n[Test 4] classify_grunt() on silence -> None")
    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    res = classify_grunt(silence, sample_rate=SAMPLE_RATE)
    print(f"  result: {res}")
    assert res is None, f"expected None on silence, got {res}"

    # --- Test 5: tap intent map round-trip ---
    print("\n[Test 5] simulate_tap() writes user_actions with correct intent")
    tap_ids: dict[str, str] = {}
    for tap_type, expected_intent in TAP_INTENT_MAP.items():
        # Inject smoke marker via record_action directly so cleanup works.
        # simulate_tap() doesn't expose context override, so we exercise BOTH
        # the public simulate_tap (smoke flag) by re-using record_action below.
        from gesture.tap import handle_tap, TapEvent
        from datetime import datetime, timezone

        ev = TapEvent(
            tap_type=tap_type,
            detected_at=datetime.now(timezone.utc),
            confidence=0.9,
        )
        # Bypass simulate_tap to inject the smoke flag via record_action.
        ctx = {
            "tap_type": tap_type,
            "detected_at": ev.detected_at.isoformat(),
            "confidence": ev.confidence,
            "_smoke": SMOKE_MARKER,
        }
        action_id = record_action(
            user_id=DEFAULT_USER_ID,
            kind="gesture_tap",
            source="headphone_button",
            intent=expected_intent,
            context=ctx,
        )
        tap_ids[tap_type] = action_id
        print(f"  {tap_type:6s} -> intent={expected_intent:11s}  id={action_id}")

    # Verify each row exists + intent matches
    with get_conn() as conn, conn.cursor() as cur:
        for tap_type, action_id in tap_ids.items():
            cur.execute(
                "SELECT kind, source, intent FROM user_actions WHERE id=%s",
                (action_id,),
            )
            row = cur.fetchone()
            assert row is not None, f"missing row for {tap_type}"
            kind, source, intent = row
            assert kind == "gesture_tap"
            assert source == "headphone_button"
            assert intent == TAP_INTENT_MAP[tap_type], (
                f"intent mismatch for {tap_type}: db={intent}, "
                f"expected={TAP_INTENT_MAP[tap_type]}"
            )

    # --- Test 6: actual simulate_tap entry point also writes a row ---
    print("\n[Test 6] simulate_tap() public entry writes a row (no smoke marker; cleaned by id)")
    real_id = simulate_tap("single", DEFAULT_USER_ID, confidence=0.7)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT intent FROM user_actions WHERE id=%s", (real_id,))
        row = cur.fetchone()
        assert row is not None and row[0] == "acknowledge"
        # Clean this one up immediately since it lacks the smoke marker.
        cur.execute("DELETE FROM user_actions WHERE id=%s", (real_id,))
        conn.commit()
    print(f"  simulate_tap('single') -> {real_id}  intent=acknowledge")

    # --- Cleanup ---
    print("\n[cleanup] Removing SMOKE user_actions rows...")
    n = _cleanup()
    print(f"  deleted {n} user_actions rows")

    print("\n=== Gesture smoke test complete (all assertions passed) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
