"""Write embeddings to the embeddings table in Postgres."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402

from .model import embed

EMBED_MODEL_TAG = "BAAI/bge-m3"


def store_embedding(
    *,
    user_id: str,
    source_type: str,
    source_id: str,
    vector: list[float],
    model_tag: str = EMBED_MODEL_TAG,
) -> str:
    """Insert one row into embeddings table. Returns new embedding id (UUID str)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO embeddings (user_id, source_type, source_id, embedding, model)
            VALUES (%s, %s, %s, %s::vector, %s)
            RETURNING id
            """,
            (user_id, source_type, source_id, _vec_literal(vector), model_tag),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id


def embed_and_store(
    *,
    user_id: str,
    source_type: str,
    source_id: str,
    text: str,
) -> tuple[str, list[float]]:
    """One-shot: embed text and persist to embeddings.

    Returns (embedding_id, vector). The vector is returned so callers can
    reuse it (e.g. for novelty logging) without paying for a second embed.
    """
    vec = embed(text)
    emb_id = store_embedding(
        user_id=user_id, source_type=source_type, source_id=source_id, vector=vec
    )
    return emb_id, vec


def _vec_literal(vector: list[float]) -> str:
    """Format a list of floats as a pgvector literal string: '[1.0,2.0,...]'."""
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
