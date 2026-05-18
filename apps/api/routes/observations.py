"""regis_observations list, optionally ranked by semantic similarity."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api import _paths  # noqa: F401
from api.deps import current_user_id
from api.schemas import ObservationItem, ObservationListResponse

from db import get_conn  # noqa: E402


router = APIRouter(tags=["observations"])


@router.get("/observations", response_model=ObservationListResponse)
def list_observations(
    limit: int = Query(20, ge=1, le=200),
    q: str | None = Query(None, description="Optional semantic query for ranking"),
    user_id: str = Depends(current_user_id),
) -> ObservationListResponse:
    if q:
        try:
            from embeddings import retrieve_similar

            hits = retrieve_similar(
                q, user_id=user_id, top_k=limit, source_types=["regis_observation"]
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"retrieval failed: {e}")

        if not hits:
            return ObservationListResponse(observations=[])

        ids = [h.source_id for h in hits]
        sim_by_id = {h.source_id: h.similarity for h in hits}
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, observed_at, observation, weight
                FROM regis_observations
                WHERE user_id = %s AND id = ANY(%s)
                """,
                (user_id, ids),
            )
            rows = cur.fetchall()
        rows_by_id = {str(r[0]): r for r in rows}
        out: list[ObservationItem] = []
        for oid in ids:
            r = rows_by_id.get(oid)
            if r is None:
                continue
            out.append(
                ObservationItem(
                    id=str(r[0]),
                    observed_at=r[1],
                    observation=r[2],
                    weight=float(r[3]),
                    similarity=round(float(sim_by_id[oid]), 3),
                )
            )
        return ObservationListResponse(observations=out)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, observed_at, observation, weight
            FROM regis_observations
            WHERE user_id = %s
            ORDER BY observed_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()

    items = [
        ObservationItem(
            id=str(r[0]),
            observed_at=r[1],
            observation=r[2],
            weight=float(r[3]),
        )
        for r in rows
    ]
    return ObservationListResponse(observations=items)
