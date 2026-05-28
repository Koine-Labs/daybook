"""Tone / energy / pitch features via librosa heuristics."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class ProsodyFeatures:
    energy: float
    pitch_mean_hz: float
    pitch_std_hz: float
    speaking_rate_wpm: float | None
    tone: str

    def to_dict(self) -> dict:
        return asdict(self)


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


def _normalized_rms_energy(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(samples**2)))
    # Map -60 dBFS..0 dBFS to 0..1 (rms 0.001 → ~0, rms 1.0 → 1)
    if rms <= 1e-6:
        return 0.0
    db = 20.0 * np.log10(rms)
    return float(max(0.0, min(1.0, (db + 60.0) / 60.0)))


def _pitch_stats(samples: np.ndarray, sample_rate: int) -> tuple[float, float]:
    import librosa

    if samples.size < sample_rate // 4:  # need at least ~250ms
        return 0.0, 0.0
    try:
        f0, voiced_flag, _ = librosa.pyin(
            samples,
            fmin=50.0,
            fmax=500.0,
            sr=sample_rate,
            frame_length=2048,
        )
    except Exception:
        return 0.0, 0.0
    voiced = f0[voiced_flag == True]  # noqa: E712
    voiced = voiced[~np.isnan(voiced)]
    if voiced.size == 0:
        return 0.0, 0.0
    return float(np.mean(voiced)), float(np.std(voiced))


def _classify_tone(energy: float, pitch_std: float, pitch_mean: float) -> str:
    if energy < 0.15:
        return "quiet"
    if energy > 0.6 and pitch_std > 35:
        return "raised"
    if energy > 0.55 and pitch_std < 20:
        return "sharp"
    if 0.25 <= energy <= 0.55 and pitch_std < 30 and 90 < pitch_mean < 280:
        return "warm"
    return "neutral"


def extract_prosody(audio: np.ndarray, sample_rate: int) -> ProsodyFeatures:
    """Compute energy/pitch/tone heuristic for one audio chunk."""
    samples = _to_float32_mono(audio)
    energy = _normalized_rms_energy(samples)
    pitch_mean, pitch_std = _pitch_stats(samples, sample_rate)
    tone = _classify_tone(energy, pitch_std, pitch_mean)
    return ProsodyFeatures(
        energy=round(energy, 3),
        pitch_mean_hz=round(pitch_mean, 1),
        pitch_std_hz=round(pitch_std, 1),
        speaking_rate_wpm=None,  # requires STT — set by escalation path, not here
        tone=tone,
    )
