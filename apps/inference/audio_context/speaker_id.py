"""Speaker identity: enroll the user's voice centroid, classify utterances."""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_THRESHOLD = 0.75
ENROLL_DIR = Path.home() / ".daybook"


@lru_cache(maxsize=1)
def _encoder():
    from resemblyzer import VoiceEncoder
    return VoiceEncoder()


def _centroid_path(user_id: str) -> Path:
    return ENROLL_DIR / f"speaker_{user_id}.npy"


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def embed_utterance(audio: np.ndarray, sample_rate: int) -> np.ndarray | None:
    """resemblyzer embedding for one utterance; None if too short."""
    from resemblyzer import preprocess_wav
    samples = np.asarray(audio, dtype=np.float32)
    if samples.size == 0:
        return None
    try:
        wav = preprocess_wav(samples, source_sr=sample_rate)
        return _encoder().embed_utterance(wav)
    except Exception:
        return None


def enroll(user_id: str, wav_paths: list[Path]) -> np.ndarray:
    """Embed each reference clip, store the mean centroid. Returns the centroid."""
    import soundfile as sf
    embeddings: list[np.ndarray] = []
    for p in wav_paths:
        audio, sr = sf.read(str(p), dtype="float32")
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        emb = embed_utterance(audio, sr)
        if emb is not None:
            embeddings.append(emb)
    if not embeddings:
        raise ValueError("no usable reference clips for enrollment")
    centroid = np.mean(np.stack(embeddings), axis=0).astype(np.float32)
    ENROLL_DIR.mkdir(parents=True, exist_ok=True)
    np.save(_centroid_path(user_id), centroid)
    return centroid


def load_centroid(user_id: str) -> np.ndarray | None:
    p = _centroid_path(user_id)
    return np.load(p) if p.exists() else None


def identify(
    embedding: np.ndarray,
    *,
    centroid: np.ndarray | None,
    threshold: float = DEFAULT_THRESHOLD,
) -> str:
    """'self' if cosine(embedding, centroid) >= threshold, 'other' if below,
    'unknown' if no centroid is enrolled."""
    if centroid is None:
        return "unknown"
    return "self" if _cosine(embedding, centroid) >= threshold else "other"
