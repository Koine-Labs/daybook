"""Ambient sound classification via YAMNet — lazy, optional, fail-soft."""
from __future__ import annotations

import csv
from functools import lru_cache

import numpy as np

_YAMNET_HANDLE = "https://tfhub.dev/google/yamnet/1"


@lru_cache(maxsize=1)
def _model():
    """Load YAMNet from tfhub; return None if tensorflow_hub isn't installed."""
    try:
        import tensorflow_hub as hub
        return hub.load(_YAMNET_HANDLE)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _class_names() -> list[str]:
    m = _model()
    if m is None:
        return []
    import tensorflow as tf
    path = m.class_map_path().numpy()
    names: list[str] = []
    with tf.io.gfile.GFile(path) as f:
        for row in csv.DictReader(f):
            names.append(row["display_name"])
    return names


def is_available() -> bool:
    return _model() is not None


def classify_ambient(audio: np.ndarray, sample_rate: int, *, top_k: int = 3) -> list[dict]:
    """Return [{class, score}] for the dominant ambient classes, or [] if unavailable.

    YAMNet expects 16 kHz mono float32 in [-1, 1].
    """
    model = _model()
    if model is None:
        return []
    samples = np.asarray(audio, dtype=np.float32)
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    if sample_rate != 16000:
        import librosa
        samples = librosa.resample(samples, orig_sr=sample_rate, target_sr=16000)
    if samples.size == 0:
        return []
    scores, _embeddings, _spectro = model(samples)
    frame_scores = np.asarray(scores)
    clip_scores = frame_scores.mean(axis=0) if frame_scores.ndim == 2 else frame_scores
    names = _class_names()
    idx = np.argsort(clip_scores)[::-1][:top_k]
    return [{"class": names[i] if i < len(names) else str(i),
             "score": float(clip_scores[i])} for i in idx]
