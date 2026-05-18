"""Similarity retrieval against the embeddings table via pgvector HNSW."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402

from .model import embed
from .store import _vec_literal


@dataclass
class RetrievalResult:
    embedding_id: str
    source_type: str
    source_id: str
    similarity: float
    model: str


def retrieve_similar(
    query: str | list[float],
    *,
    user_id: str,
    top_k: int = 5,
    source_types: Sequence[str] | None = None,
    min_similarity: float = 0.0,
) -> list[RetrievalResult]:
    """Cosine-similarity search.

    `query` can be raw text (will be embedded) or a pre-computed embedding vector.
    `source_types` filters to a subset (e.g., ['dream_recall', 'intent']).
    Returns top_k results above `min_similarity`, sorted desc.
    """
    if isinstance(query, str):
        qvec = embed(query)
    else:
        qvec = list(query)

    sql_parts = [
        "SELECT id, source_type, source_id, model, 1 - (embedding <=> %s::vector) AS sim",
        "FROM embeddings",
        "WHERE user_id = %s",
    ]
    params: list = [_vec_literal(qvec), user_id]

    if source_types:
        sql_parts.append("AND source_type = ANY(%s)")
        params.append(list(source_types))

    sql_parts.append("ORDER BY embedding <=> %s::vector ASC")
    params.append(_vec_literal(qvec))
    sql_parts.append("LIMIT %s")
    params.append(top_k * 4)  # over-fetch to allow min_similarity filtering

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("\n".join(sql_parts), tuple(params))
        rows = cur.fetchall()

    results = [
        RetrievalResult(
            embedding_id=str(r[0]),
            source_type=r[1],
            source_id=str(r[2]),
            similarity=float(r[4]),
            model=r[3],
        )
        for r in rows
        if float(r[4]) >= min_similarity
    ]
    return results[:top_k]
