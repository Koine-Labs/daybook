"""Embedding layer for Daybook.

BGE-M3 (BAAI) dense embeddings, 1024-dim, local via sentence-transformers.
Runs on MPS (Apple Silicon), CUDA (NVIDIA), or CPU automatically.

Three public surfaces:
  - embed(text)               -> list[float]      (raw embedding)
  - store_embedding(...)      -> EmbeddingID      (write to embeddings table)
  - retrieve_similar(...)     -> list[Result]     (HNSW cosine similarity search)

The model loads lazily on first call (~10 seconds first time, instant after).
"""

from .model import embed, embed_batch, get_model
from .store import store_embedding, embed_and_store
from .retrieve import retrieve_similar, RetrievalResult

__all__ = [
    "embed",
    "embed_batch",
    "get_model",
    "store_embedding",
    "embed_and_store",
    "retrieve_similar",
    "RetrievalResult",
]
