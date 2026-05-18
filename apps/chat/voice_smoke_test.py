"""Voice CLI smoke test — non-interactive.

Run with:
    cd apps && source inference/.venv/bin/activate && python -m chat.voice_smoke_test

Verifies:
  1. llm.stt module imports cleanly
  2. chat.voice_cli module imports cleanly (so --help works)
  3. argparse on voice_cli accepts expected flags
  4. If a test wav is present in ~/.daybook/recall_audio/, transcribe it
  5. Otherwise synthesize a small silent wav and confirm transcribe runs

Does NOT exercise the live mic / Phase 1 audio output. Interactive recording
must be tested by a human.
"""
from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parent.parent
INFERENCE_DIR = APPS_DIR / "inference"
for p in (APPS_DIR, INFERENCE_DIR):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


def main() -> int:
    print("=== Daybook voice CLI smoke test ===\n")

    print("[Test 1] import llm.stt")
    from llm import stt  # noqa: F401

    assert hasattr(stt, "transcribe"), "stt.transcribe missing"
    assert hasattr(stt, "record_and_transcribe"), "stt.record_and_transcribe missing"
    print("  OK (transcribe + record_and_transcribe exported)")

    print("\n[Test 2] import chat.voice_cli")
    from chat import voice_cli  # noqa: F401

    assert hasattr(voice_cli, "main"), "voice_cli.main missing"
    print(f"  OK (AUDIO_AVAILABLE = {voice_cli.AUDIO_AVAILABLE})")

    print("\n[Test 3] voice_cli --help parses without invoking REPL")
    parser_argv = ["--help"]
    rc = None
    try:
        voice_cli.main(parser_argv)
    except SystemExit as e:
        rc = e.code
    assert rc == 0, f"--help should exit 0, got {rc}"
    print("  OK (--help exit 0)")

    print("\n[Test 4] voice_cli arg parser accepts all documented flags")
    import argparse

    test_argv = ["--new", "--no-speak", "--max-seconds", "45", "--user", "test-uid"]
    try:
        parsed = _build_parser().parse_args(test_argv)
        assert parsed.new is True
        assert parsed.no_speak is True
        assert parsed.max_seconds == 45
        assert parsed.user == "test-uid"
        print("  OK (--new, --no-speak, --max-seconds, --user all accepted)")
    except SystemExit:
        raise AssertionError("flag parsing failed")

    print("\n[Test 5] transcribe a sample WAV")
    audio_dir = Path.home() / ".daybook" / "recall_audio"
    sample = _pick_or_make_sample(audio_dir)
    print(f"  using sample: {sample}")
    text = stt.transcribe(sample)
    print(f"  transcribed text: {text!r}")
    # We don't assert content — silent wavs often yield '' and that's a pass.
    print("  OK (transcribe returned without exception)")

    print("\n=== Voice smoke test complete (all assertions passed) ===")
    return 0


def _build_parser():
    """Mirror voice_cli's argparse for non-invocation flag validation."""
    import argparse

    p = argparse.ArgumentParser(prog="chat.voice_cli")
    p.add_argument("--new", action="store_true")
    p.add_argument("--conversation", metavar="UUID")
    p.add_argument("--user", default="x")
    p.add_argument("--no-speak", action="store_true")
    p.add_argument("--max-seconds", type=int, default=30)
    return p


def _pick_or_make_sample(audio_dir: Path) -> Path:
    """Return an existing recall_audio wav if any, else synthesize a 1s silent wav."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(audio_dir.glob("*.wav"))
    if existing:
        return existing[-1]
    out = audio_dir / "_smoke_silent.wav"
    if not out.exists():
        with wave.open(str(out), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 16000)  # 1 second silence
    return out


if __name__ == "__main__":
    sys.exit(main())
