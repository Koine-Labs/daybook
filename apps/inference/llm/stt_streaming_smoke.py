"""Smoke test for streaming STT.

Confirms:
  1. Streaming backend is available
  2. A sample WAV (from ~/.daybook/recall_audio/) or a generated silence WAV
     transcribes through the chunked pipeline without crashing

Does NOT auto-test live mic — that requires a human at the keyboard.

Run with:
    cd apps/inference && source .venv/bin/activate && python -m llm.stt_streaming_smoke
"""
from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from llm.stt_streaming import (  # noqa: E402
    get_streaming_backend,
    transcribe_wav_streaming,
)

RECALL_AUDIO_DIR = Path.home() / ".daybook" / "recall_audio"


def _pick_sample_wav() -> Path | None:
    """First .wav with non-trivial size, else None."""
    if not RECALL_AUDIO_DIR.exists():
        return None
    candidates = sorted(RECALL_AUDIO_DIR.glob("*.wav"))
    for p in candidates:
        # Skip the silent smoke fixture if larger ones exist.
        if p.stat().st_size > 100_000:
            return p
    return candidates[0] if candidates else None


def _make_silence_wav(out_path: Path, *, seconds: float = 3.0) -> Path:
    """Write a 3-second 16kHz mono silence WAV (16-bit PCM)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16000
    n_samples = int(sample_rate * seconds)
    silence = b"\x00\x00" * n_samples
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(silence)
    return out_path


def main() -> int:
    print("=== Streaming STT smoke test ===\n")

    backend = get_streaming_backend()
    print(f"[1] Streaming backend: {backend}")
    if backend == "none":
        print("    ERROR: no STT backend installed (install faster-whisper)")
        return 1
    print()

    sample = _pick_sample_wav()
    if sample is None:
        sample = _make_silence_wav(Path("/tmp/daybook_streaming_silence.wav"))
        print(f"[2] No sample WAV in {RECALL_AUDIO_DIR}; using silence: {sample}")
    else:
        print(f"[2] Using sample WAV: {sample} ({sample.stat().st_size:,} bytes)")

    partials: list[str] = []

    def on_partial(text: str) -> None:
        partials.append(text)
        snippet = text if len(text) < 80 else text[:77] + "..."
        print(f"    partial @ {len(partials)}: {snippet!r}")

    t0 = time.monotonic()
    try:
        final = transcribe_wav_streaming(sample, on_partial=on_partial)
    except Exception as exc:
        print(f"    FAIL: transcribe_wav_streaming raised {type(exc).__name__}: {exc}")
        return 1
    elapsed = time.monotonic() - t0

    print(f"\n[3] Final transcript ({elapsed*1000:.0f}ms total):")
    print(f"    {final!r}")
    print(f"    partial emits: {len(partials)}")

    print("\n=== Streaming STT smoke test PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
