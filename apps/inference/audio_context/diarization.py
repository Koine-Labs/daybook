"""Lightweight speaker diarization via resemblyzer embeddings + agglomerative clustering."""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from audio_context.vad import detect_voice_activity

WINDOW_SECONDS = 1.5
HOP_SECONDS = 0.75
MIN_SEGMENT_SECONDS = 0.4


@lru_cache(maxsize=1)
def _encoder():
    from resemblyzer import VoiceEncoder

    return VoiceEncoder(device="cpu", verbose=False)


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


def _resample_to_16k(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
    if sample_rate == 16000:
        return audio, sample_rate
    import librosa

    return librosa.resample(audio, orig_sr=sample_rate, target_sr=16000), 16000


def _embed_window(samples: np.ndarray) -> np.ndarray:
    from resemblyzer import preprocess_wav

    processed = preprocess_wav(samples, source_sr=16000)
    if processed.size == 0:
        return None  # type: ignore[return-value]
    return _encoder().embed_utterance(processed)


def _cluster_embeddings(
    embeddings: np.ndarray, num_speakers: int | None
) -> np.ndarray:
    if len(embeddings) == 0:
        return np.array([], dtype=int)
    if len(embeddings) == 1:
        return np.array([0])

    from sklearn.cluster import AgglomerativeClustering

    if num_speakers is None:
        # cosine distance threshold ~0.25 separates resemblyzer voices reasonably.
        model = AgglomerativeClustering(
            n_clusters=None,
            metric="cosine",
            linkage="average",
            distance_threshold=0.25,
        )
    else:
        model = AgglomerativeClustering(
            n_clusters=num_speakers,
            metric="cosine",
            linkage="average",
        )
    return model.fit_predict(embeddings)


def diarize(
    audio: np.ndarray,
    sample_rate: int,
    *,
    num_speakers: int | None = None,
) -> list[dict]:
    """Return list of {start_seconds, end_seconds, speaker_id} for voiced regions.

    Falls back to single 'speaker_0' if too little material for clustering.
    """
    samples = _to_float32_mono(audio)
    if samples.size == 0:
        return []

    samples, sr = _resample_to_16k(samples, sample_rate)
    vad_segments = detect_voice_activity(samples, sr)
    if not vad_segments:
        return []

    windows: list[tuple[float, float, np.ndarray]] = []
    for seg in vad_segments:
        start = seg["start_seconds"]
        end = seg["end_seconds"]
        if end - start < MIN_SEGMENT_SECONDS:
            continue
        cursor = start
        while cursor < end:
            w_end = min(cursor + WINDOW_SECONDS, end)
            if w_end - cursor < MIN_SEGMENT_SECONDS:
                break
            s_idx = int(cursor * sr)
            e_idx = int(w_end * sr)
            windows.append((cursor, w_end, samples[s_idx:e_idx]))
            cursor += HOP_SECONDS

    if not windows:
        return [
            {
                "start_seconds": s["start_seconds"],
                "end_seconds": s["end_seconds"],
                "speaker_id": "speaker_0",
            }
            for s in vad_segments
        ]

    embeddings = []
    valid_windows = []
    for w_start, w_end, chunk in windows:
        emb = _embed_window(chunk)
        if emb is None:
            continue
        embeddings.append(emb)
        valid_windows.append((w_start, w_end))

    if not embeddings:
        return [
            {
                "start_seconds": s["start_seconds"],
                "end_seconds": s["end_seconds"],
                "speaker_id": "speaker_0",
            }
            for s in vad_segments
        ]

    labels = _cluster_embeddings(np.array(embeddings), num_speakers)

    raw_segments = [
        {
            "start_seconds": float(w_start),
            "end_seconds": float(w_end),
            "speaker_id": f"speaker_{int(label)}",
        }
        for (w_start, w_end), label in zip(valid_windows, labels)
    ]

    return _merge_adjacent(raw_segments)


def _merge_adjacent(segments: list[dict]) -> list[dict]:
    """Merge consecutive segments with the same speaker_id."""
    if not segments:
        return []
    segments = sorted(segments, key=lambda s: s["start_seconds"])
    merged = [dict(segments[0])]
    for seg in segments[1:]:
        last = merged[-1]
        if (
            seg["speaker_id"] == last["speaker_id"]
            and seg["start_seconds"] <= last["end_seconds"] + 0.5
        ):
            last["end_seconds"] = max(last["end_seconds"], seg["end_seconds"])
        else:
            merged.append(dict(seg))
    return merged
