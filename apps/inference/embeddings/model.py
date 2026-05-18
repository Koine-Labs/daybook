"""BGE-M3 dense embedding model — lazy-loaded, device-auto-detected."""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = os.environ.get("DAYBOOK_EMBED_MODEL", "BAAI/bge-m3")
EMBED_DIM = 1024  # BGE-M3 dense output dim — must match vector(1024) in schema


def _pick_device() -> str:
    """Prefer GPU acceleration; fall back to CPU."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


@lru_cache(maxsize=1)
def get_model() -> "SentenceTransformer":
    """Load BGE-M3 once per process. Cached across calls."""
    from sentence_transformers import SentenceTransformer

    device = _pick_device()
    logger.info("Loading %s on device=%s ...", MODEL_NAME, device)
    model = SentenceTransformer(MODEL_NAME, device=device)
    logger.info("Loaded %s (dim=%d).", MODEL_NAME, model.get_sentence_embedding_dimension())
    return model


def embed(text: str) -> list[float]:
    """Embed one text. Returns 1024-dim list[float] (matches vector(1024) schema)."""
    model = get_model()
    vec = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return vec.tolist()


def embed_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embed many texts in one model pass."""
    if not texts:
        return []
    model = get_model()
    vecs = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return [v.tolist() for v in vecs]
