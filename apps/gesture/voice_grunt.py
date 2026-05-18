"""Lightweight voice-grunt classifier.

Distinguishes four non-word vocal back-channel utterances via energy + pitch
envelope heuristics (no ML, no model load):

  - 'mm-hmm' : two energy peaks, rising pitch on second  (acknowledge / yes)
  - 'mm-mm'  : two energy peaks, falling pitch on second (negation / no)
  - 'sigh'   : long single voiced exhale, breathy        (dismissal / frustration)
  - 'hmm'    : single voiced sustained tone              (thinking / wait)

Good enough for v0. v2+ should swap to a tiny audio classifier trained on
collected examples.
"""
from __future__ import annotations

import numpy as np

# Heuristic thresholds (tuned for 16 kHz mono audio, normalized [-1, 1]).
_FRAME_MS = 20
_ENERGY_THRESHOLD_DB = -32.0     # below this is silence
_PEAK_MIN_DURATION_MS = 80       # ignore micro blips
_PEAK_MIN_GAP_MS = 80            # min silence between two peaks
_SINGLE_PEAK_MIN_MS = 220        # minimum voiced span for 'hmm'/'sigh'
_SIGH_MIN_MS = 500               # 'sigh' is longer than 'hmm'
_SIGH_SPECTRAL_FLATNESS = 0.20   # breathiness floor


def classify_grunt(audio: np.ndarray, sample_rate: int = 16000) -> dict | None:
    """Returns {kind: 'mm-hmm'|'mm-mm'|'sigh'|'hmm', confidence: 0..1} or None.

    Returns None if the signal looks like noise / speech / nothing.
    """
    if audio.size == 0:
        return None

    audio = audio.astype(np.float32).reshape(-1)
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio / peak

    peaks = _voiced_peaks(audio, sample_rate)
    if not peaks:
        return None

    if len(peaks) == 1:
        return _classify_single(audio, sample_rate, peaks[0])

    if len(peaks) >= 2:
        return _classify_two_peak(audio, sample_rate, peaks[0], peaks[-1])

    return None


def _voiced_peaks(audio: np.ndarray, sample_rate: int) -> list[tuple[int, int]]:
    """Return list of (start_sample, end_sample) for voiced spans."""
    frame_samples = max(1, int(sample_rate * _FRAME_MS / 1000))
    n_frames = len(audio) // frame_samples
    if n_frames == 0:
        return []

    energies_db = np.full(n_frames, -120.0, dtype=np.float32)
    for i in range(n_frames):
        chunk = audio[i * frame_samples : (i + 1) * frame_samples]
        rms = float(np.sqrt(np.mean(chunk * chunk) + 1e-12))
        energies_db[i] = 20.0 * np.log10(rms + 1e-12)

    voiced = energies_db > _ENERGY_THRESHOLD_DB
    spans: list[tuple[int, int]] = []
    i = 0
    while i < n_frames:
        if voiced[i]:
            j = i
            while j < n_frames and voiced[j]:
                j += 1
            span_ms = (j - i) * _FRAME_MS
            if span_ms >= _PEAK_MIN_DURATION_MS:
                spans.append((i * frame_samples, j * frame_samples))
            i = j
        else:
            i += 1

    # Merge spans with tiny gaps below _PEAK_MIN_GAP_MS
    if not spans:
        return spans
    merged: list[tuple[int, int]] = [spans[0]]
    for start, end in spans[1:]:
        prev_start, prev_end = merged[-1]
        gap_ms = (start - prev_end) * 1000 / sample_rate
        if gap_ms < _PEAK_MIN_GAP_MS:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    return merged


def _classify_single(
    audio: np.ndarray, sample_rate: int, span: tuple[int, int]
) -> dict | None:
    start, end = span
    duration_ms = (end - start) * 1000 / sample_rate
    if duration_ms < _SINGLE_PEAK_MIN_MS:
        return None

    chunk = audio[start:end]
    flatness = _spectral_flatness(chunk, sample_rate)

    if duration_ms >= _SIGH_MIN_MS and flatness >= _SIGH_SPECTRAL_FLATNESS:
        return {
            "kind": "sigh",
            "confidence": min(0.95, 0.5 + flatness),
            "duration_ms": round(duration_ms, 1),
            "spectral_flatness": round(flatness, 3),
        }

    return {
        "kind": "hmm",
        "confidence": 0.6 if duration_ms < _SIGH_MIN_MS else 0.5,
        "duration_ms": round(duration_ms, 1),
        "spectral_flatness": round(flatness, 3),
    }


def _classify_two_peak(
    audio: np.ndarray,
    sample_rate: int,
    first: tuple[int, int],
    second: tuple[int, int],
) -> dict:
    pitch_first = _dominant_pitch_hz(audio[first[0] : first[1]], sample_rate)
    pitch_second = _dominant_pitch_hz(audio[second[0] : second[1]], sample_rate)

    rising = pitch_second > pitch_first * 1.04
    falling = pitch_second < pitch_first * 0.96

    if rising:
        confidence = min(0.95, 0.55 + (pitch_second - pitch_first) / max(pitch_first, 1.0))
        return {
            "kind": "mm-hmm",
            "confidence": round(float(confidence), 3),
            "pitch_first_hz": round(pitch_first, 1),
            "pitch_second_hz": round(pitch_second, 1),
        }
    if falling:
        confidence = min(0.95, 0.55 + (pitch_first - pitch_second) / max(pitch_first, 1.0))
        return {
            "kind": "mm-mm",
            "confidence": round(float(confidence), 3),
            "pitch_first_hz": round(pitch_first, 1),
            "pitch_second_hz": round(pitch_second, 1),
        }
    # Flat two-peak — call it mm-hmm with low confidence (more common
    # back-channel than mm-mm in natural usage).
    return {
        "kind": "mm-hmm",
        "confidence": 0.45,
        "pitch_first_hz": round(pitch_first, 1),
        "pitch_second_hz": round(pitch_second, 1),
    }


def _dominant_pitch_hz(chunk: np.ndarray, sample_rate: int) -> float:
    """Crude pitch estimate via autocorrelation peak in 70-400 Hz band."""
    if chunk.size < sample_rate // 40:
        return 0.0
    chunk = chunk - float(np.mean(chunk))
    corr = np.correlate(chunk, chunk, mode="full")[len(chunk) - 1 :]
    min_lag = sample_rate // 400
    max_lag = sample_rate // 70
    if max_lag >= len(corr):
        max_lag = len(corr) - 1
    if min_lag >= max_lag:
        return 0.0
    window = corr[min_lag:max_lag]
    if window.size == 0:
        return 0.0
    lag = int(np.argmax(window)) + min_lag
    if lag <= 0:
        return 0.0
    return float(sample_rate) / float(lag)


def _spectral_flatness(chunk: np.ndarray, sample_rate: int) -> float:
    """Geometric-mean / arithmetic-mean of magnitude spectrum. ~1 = white."""
    if chunk.size < 64:
        return 0.0
    spec = np.abs(np.fft.rfft(chunk * np.hanning(chunk.size))) + 1e-9
    geo = float(np.exp(np.mean(np.log(spec))))
    arith = float(np.mean(spec))
    return geo / arith if arith > 0 else 0.0
