"""Mic recorder built on sounddevice. Writes 16kHz mono WAV files."""
from __future__ import annotations

import logging
import sys
import threading
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000  # whisper native rate
CHANNELS = 1
DTYPE = "int16"  # 16-bit PCM keeps wav writing trivial


class RecorderError(RuntimeError):
    """Raised when sounddevice/microphone setup fails."""


def _import_sounddevice():
    try:
        import sounddevice as sd
        import numpy as np

        return sd, np
    except OSError as e:
        raise RecorderError(
            f"sounddevice failed to load PortAudio: {e}. "
            "On macOS, grant terminal microphone permission in System Settings > Privacy."
        ) from e
    except ImportError as e:
        raise RecorderError(
            f"sounddevice not installed: {e}. Run: uv pip install sounddevice"
        ) from e


def record_interactive(
    output_path: Path,
    *,
    max_seconds: int = 60,
    show_progress: bool = True,
) -> Path:
    """Record from default mic until ENTER is pressed (or max_seconds elapses).

    The first ENTER press in the parent CLI is what triggers calling this function;
    inside here we wait for the *second* ENTER on stdin to stop early.
    """
    sd, np = _import_sounddevice()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    frames: list = []
    stop_event = threading.Event()

    def callback(indata, _frames_count, _time_info, status):
        if status:
            logger.warning("sounddevice status: %s", status)
        frames.append(indata.copy())

    def wait_for_enter():
        try:
            sys.stdin.readline()
        except Exception:
            pass
        stop_event.set()

    try:
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=callback,
        )
    except Exception as e:
        raise RecorderError(
            f"Could not open input stream: {e}. Is a microphone connected and permitted?"
        ) from e

    enter_thread = threading.Thread(target=wait_for_enter, daemon=True)
    enter_thread.start()

    with stream:
        for sec in range(max_seconds):
            if stop_event.wait(timeout=1.0):
                break
            if show_progress:
                print(".", end="", flush=True)
        if show_progress:
            print()

    if not frames:
        raise RecorderError("No audio captured (empty buffer).")

    audio = np.concatenate(frames, axis=0)
    _write_wav(output_path, audio, sample_rate=SAMPLE_RATE, channels=CHANNELS)
    return output_path


def _write_wav(path: Path, samples, *, sample_rate: int, channels: int) -> None:
    """Write int16 mono/stereo samples to a 16-bit PCM WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
