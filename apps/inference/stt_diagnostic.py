"""STT diagnostic: record from MacBook mic, play back, transcribe with multiple models.

Lets you separate three possible failure modes:
  1. Mic captures muddled audio → mic / device issue
  2. Mic captures clear audio but small.en transcribes wrong → model too small
  3. Mic + small.en both fine but medium.en is much better → just upgrade model
  4. Even medium.en gets it wrong → cloud STT is the answer

Run from apps/inference/ with the venv active:
    python -m stt_diagnostic
    python -m stt_diagnostic --duration 8 --sentence "Test the recognition accuracy"
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))

SAMPLE_RATE = 16000
DEFAULT_DURATION = 5.0
SAMPLE_SENTENCE = (
    "Hey Regis, can you tell me what's on my mind tonight and how my sleep has been "
    "going for the past week."
)


def find_macbook_mic() -> tuple[int, str]:
    """Find the MacBook built-in mic, raise if not found."""
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and "macbook" in d["name"].lower():
            return i, d["name"]
    # Fallback: first non-BT mic
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and "tk-" not in d["name"].lower():
            return i, d["name"]
    raise RuntimeError("No MacBook mic found")


def record(duration: float, device: int) -> np.ndarray:
    print(f"\n=== Recording {duration}s — start speaking ===")
    print("3...", end="", flush=True); time.sleep(1)
    print("2...", end="", flush=True); time.sleep(1)
    print("1... SPEAK", flush=True)
    audio = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=device,
    )
    sd.wait()
    print("=== Recording complete ===")
    return audio.flatten()


def playback(audio: np.ndarray) -> None:
    print("\n=== Playing back what we captured ===")
    sd.play(audio, samplerate=SAMPLE_RATE, blocking=True)
    print("=== Playback complete ===")
    print("LISTEN: Did your voice sound clear? muddled? distant? cut off?")


def transcribe_with(model_name: str, audio: np.ndarray) -> tuple[str, float]:
    """Load + use a faster-whisper model. Returns (text, elapsed_seconds)."""
    from faster_whisper import WhisperModel

    print(f"\n=== Loading {model_name} model (may take a moment first run) ===")
    t0 = time.monotonic()
    model = WhisperModel(model_name, compute_type="int8")
    load_t = time.monotonic() - t0
    print(f"  loaded in {load_t:.1f}s")

    t0 = time.monotonic()
    segments, _info = model.transcribe(
        audio,
        language="en",
        beam_size=5,
        condition_on_previous_text=False,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 250},
    )
    text = "".join(seg.text for seg in segments).strip()
    transcribe_t = time.monotonic() - t0
    return text, transcribe_t


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION,
                        help=f"recording length in seconds (default {DEFAULT_DURATION})")
    parser.add_argument("--sentence", default=SAMPLE_SENTENCE,
                        help="suggested sentence to read")
    parser.add_argument("--models", nargs="+", default=["small.en", "medium.en"],
                        help="which models to test")
    parser.add_argument("--device", type=int, default=None,
                        help="audio input device index (default: MacBook mic)")
    parser.add_argument("--save", default="/tmp/daybook_stt_sample.wav",
                        help="where to save the WAV for later inspection")
    args = parser.parse_args(argv)

    if args.device is None:
        idx, name = find_macbook_mic()
        args.device = idx
        print(f"Using input device: [{idx}] {name}")
    else:
        d = sd.query_devices(args.device)
        print(f"Using input device: [{args.device}] {d['name']}")

    print()
    print("=" * 70)
    print("Please say this sentence clearly when prompted:")
    print(f'  "{args.sentence}"')
    print("=" * 70)
    input("Press ENTER when ready to start the 3-second countdown...")

    audio = record(args.duration, args.device)
    sf.write(args.save, audio, SAMPLE_RATE)
    print(f"Saved sample to {args.save}")

    energy = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))
    print(f"\nAudio stats: RMS={energy:.4f}  peak={peak:.4f}  duration={len(audio)/SAMPLE_RATE:.2f}s")
    if energy < 0.005:
        print("WARNING: very low energy — mic may not be picking up your voice well")
    if peak > 0.95:
        print("WARNING: clipping detected — speaking too loud or too close")

    playback(audio)

    print(f"\n=== Expected sentence ===")
    print(f"  {args.sentence}")

    for m in args.models:
        try:
            text, t = transcribe_with(m, audio)
            print(f"\n[{m}] ({t:.2f}s)")
            print(f"  {text!r}")
        except Exception as e:
            print(f"\n[{m}] FAILED: {e}")

    print()
    print("=" * 70)
    print("DIAGNOSIS GUIDE")
    print("=" * 70)
    print("If playback sounded muddled/distant → mic placement or device issue")
    print("If playback sounded clear AND small.en is wrong → model too small")
    print("If both models are wrong on clear audio → need cloud STT (Deepgram/OpenAI)")
    print("If medium.en is markedly better → just upgrade default")
    print()
    print(f"Sample saved at {args.save} — you can replay it any time with:")
    print(f"  afplay {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
