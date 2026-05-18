"""End-to-end audio smoke test.

Confirms:
  1. Active TTS backend (kokoro vs say vs none)
  2. Witness Mode synthesis + playback ("You are dreaming.")
  3. Companion Mode synthesis + playback ("There you are. ...")
  4. wisp.voice_chain.speak_moment() — full compose→synth→play

This test ACTUALLY PLAYS AUDIO. If Bluetooth headphones are connected, audio
routes there; otherwise it goes to the Mac speakers. Set DAYBOOK_NO_PLAY=1 to
skip playback (useful for CI / quick syntax checks).

Run with:
    cd apps && source inference/.venv/bin/activate && python -m inference.audio.smoke_test
    # or:
    cd apps/inference && python -m audio.smoke_test
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Allow running as either `inference.audio.smoke_test` (from apps/) or
# `audio.smoke_test` (from apps/inference/). Add apps/inference to sys.path.
INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

# Also add apps/ so we can import wisp.voice_chain
APPS_DIR = INFERENCE_DIR.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from audio import (  # noqa: E402
    MODE_COMPANION,
    MODE_WITNESS,
    get_active_backend,
    play,
    synthesize,
)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
SKIP_PLAYBACK = os.environ.get("DAYBOOK_NO_PLAY") == "1"


def _save_and_maybe_play(wav_bytes: bytes, path: Path, label: str) -> float:
    """Write wav to disk, optionally play it. Returns playback duration (s)."""
    path.write_bytes(wav_bytes)
    print(f"  saved {label} → {path} ({len(wav_bytes):,} bytes)")
    if SKIP_PLAYBACK:
        print(f"  skipping playback (DAYBOOK_NO_PLAY=1)")
        return 0.0
    t0 = time.monotonic()
    play(wav_bytes)
    return time.monotonic() - t0


def main() -> int:
    print("=== Daybook audio smoke test ===\n")

    # --- Step 1: backend detection ---
    backend = get_active_backend()
    print(f"[1] Active TTS backend: {backend}")
    if backend == "none":
        print("    ERROR: no TTS backend available. Install kokoro-onnx + models, or run on macOS.")
        return 1
    print(f"    DAYBOOK_TTS env: {os.environ.get('DAYBOOK_TTS') or '(unset → auto)'}")
    print(f"    DAYBOOK_NO_PLAY: {os.environ.get('DAYBOOK_NO_PLAY') or '(unset → will play)'}\n")

    # --- Step 2: Witness Mode ---
    witness_text = "You are dreaming."
    print(f"[2] Witness Mode synth: {witness_text!r}")
    t0 = time.monotonic()
    witness_wav = synthesize(witness_text, mode=MODE_WITNESS)
    witness_synth_s = time.monotonic() - t0
    print(f"    synth: {witness_synth_s*1000:.0f}ms")
    witness_play_s = _save_and_maybe_play(
        witness_wav, Path("/tmp/daybook_witness.wav"), "witness"
    )
    print(f"    play:  {witness_play_s*1000:.0f}ms\n")

    # --- Step 3: Companion Mode ---
    companion_text = "There you are. Try not to think too hard tonight."
    print(f"[3] Companion Mode synth: {companion_text!r}")
    t0 = time.monotonic()
    companion_wav = synthesize(companion_text, mode=MODE_COMPANION)
    companion_synth_s = time.monotonic() - t0
    print(f"    synth: {companion_synth_s*1000:.0f}ms")
    companion_play_s = _save_and_maybe_play(
        companion_wav, Path("/tmp/daybook_companion.wav"), "companion"
    )
    print(f"    play:  {companion_play_s*1000:.0f}ms\n")

    # --- Step 4: End-to-end via voice_chain (requires DB + LLM auth) ---
    print("[4] End-to-end voice_chain.speak_moment()")
    try:
        from wisp.voice_chain import speak_moment
        out = speak_moment(
            user_id=DEFAULT_USER_ID,
            moment_kind="morning_recall_prompt",
            explicit_context=(
                "07:42 AM. User stably awake 80 seconds. "
                "Two REM cues fired overnight, both inside REM windows."
            ),
            retrieval_source_types=("intent", "dream_recall"),
            dry_run=SKIP_PLAYBACK,
        )
        print(f"    mode:    {out['mode']}")
        print(f"    backend: {out['backend']}")
        print(f"    compose: {out['composition_seconds']*1000:.0f}ms")
        print(f"    synth:   {out['synthesis_seconds']*1000:.0f}ms")
        print(f"    play:    {out['playback_seconds']*1000:.0f}ms")
        print(f"    Regis:   {out['text']!r}")
        chain_path = Path("/tmp/daybook_voice_chain.wav")
        chain_path.write_bytes(out["audio_bytes"])
        print(f"    saved → {chain_path} ({len(out['audio_bytes']):,} bytes)")
    except Exception as exc:
        print(f"    voice_chain failed: {type(exc).__name__}: {exc}")
        print(f"    (DB/LLM may not be reachable — Steps 1-3 are still definitive for TTS.)")

    print("\n=== Audio smoke test complete ===")
    print("Files written to /tmp/daybook_*.wav")
    return 0


if __name__ == "__main__":
    sys.exit(main())
