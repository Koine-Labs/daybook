"""Voice activity detection via silero-vad (lightweight, CPU-friendly)."""

from __future__ import annotations

from functools import lru_cache

import numpy as np


@lru_cache(maxsize=1)
def _model():
    from silero_vad import load_silero_vad

    return load_silero_vad()


def _to_float32_mono(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio)
    if arr.ndim == 2:
        arr = arr.mean(axis=1)
    if arr.dtype == np.int16:
        arr = arr.astype(np.float32) / 32768.0
    elif arr.dtype == np.int32:
        arr = arr.astype(np.float32) / 2147483648.0
    elif arr.dtype != np.float32:
        arr = arr.astype(np.float32)
    return arr


def detect_voice_activity(audio: np.ndarray, sample_rate: int) -> list[dict]:
    """Return list of {start_seconds, end_seconds, confidence} for speech segments."""
    import torch
    from silero_vad import get_speech_timestamps

    samples = _to_float32_mono(audio)
    if samples.size == 0:
        return []

    # silero supports 8k and 16k natively; resample others via librosa.
    if sample_rate not in (8000, 16000):
        import librosa

        samples = librosa.resample(samples, orig_sr=sample_rate, target_sr=16000)
        sample_rate = 16000

    tensor = torch.from_numpy(samples)
    timestamps = get_speech_timestamps(
        tensor,
        _model(),
        sampling_rate=sample_rate,
        return_seconds=True,
    )
    return [
        {
            "start_seconds": float(t["start"]),
            "end_seconds": float(t["end"]),
            "confidence": float(t.get("confidence", 1.0)),
        }
        for t in timestamps
    ]


def is_speech_now(audio_chunk: np.ndarray, sample_rate: int = 16000) -> bool:
    """Fast yes/no for a short chunk (~30ms)."""
    import torch

    samples = _to_float32_mono(audio_chunk)
    if samples.size == 0:
        return False

    if sample_rate not in (8000, 16000):
        import librosa

        samples = librosa.resample(samples, orig_sr=sample_rate, target_sr=16000)
        sample_rate = 16000

    window = 512 if sample_rate == 16000 else 256
    if samples.size < window:
        samples = np.pad(samples, (0, window - samples.size))
    samples = samples[:window]

    tensor = torch.from_numpy(samples)
    prob = _model()(tensor, sample_rate).item()
    return prob > 0.5
