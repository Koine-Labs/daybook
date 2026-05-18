"""Sleep sessions + stage timelines + user_state_estimate streams."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api import _paths  # noqa: F401
from api.deps import current_user_id
from api.schemas import (
    SessionDetail,
    SessionListItem,
    SessionListResponse,
    SessionStateResponse,
    StageRow,
    StageSummary,
    StateRow,
)

from db import get_conn  # noqa: E402


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
def list_sessions(
    limit: int = Query(30, ge=1, le=200),
    days: int = Query(30, ge=1, le=3650),
    user_id: str = Depends(current_user_id),
) -> SessionListResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, started_at, ended_at, duration_seconds
            FROM sleep_sessions
            WHERE user_id = %s AND started_at >= %s
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (user_id, cutoff, limit),
        )
        sess_rows = cur.fetchall()

        if not sess_rows:
            return SessionListResponse(sessions=[])

        sess_ids = [r[0] for r in sess_rows]
        cur.execute(
            """
            SELECT session_id, stage, COUNT(*)
            FROM sleep_stage_classifications
            WHERE session_id = ANY(%s)
            GROUP BY session_id, stage
            """,
            (sess_ids,),
        )
        stage_rows = cur.fetchall()

    counts: dict[str, dict[str, int]] = {}
    for sid, stage, n in stage_rows:
        counts.setdefault(str(sid), {})[stage] = int(n)

    out: list[SessionListItem] = []
    for r in sess_rows:
        sid = str(r[0])
        out.append(
            SessionListItem(
                id=sid,
                started_at=r[1],
                ended_at=r[2],
                duration_seconds=int(r[3] or 0),
                stage_summary=_stage_summary(counts.get(sid, {})),
            )
        )
    return SessionListResponse(sessions=out)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    user_id: str = Depends(current_user_id),
) -> SessionDetail:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, started_at, ended_at, duration_seconds, sensor_sources, notes
            FROM sleep_sessions
            WHERE user_id = %s AND id = %s
            """,
            (user_id, session_id),
        )
        sess = cur.fetchone()
        if sess is None:
            raise HTTPException(status_code=404, detail="session not found")

        cur.execute(
            """
            SELECT epoch_start_at, stage, source, confidence
            FROM sleep_stage_classifications
            WHERE session_id = %s
            ORDER BY epoch_start_at ASC
            """,
            (session_id,),
        )
        stage_rows = cur.fetchall()

    counts: dict[str, int] = {}
    stages: list[StageRow] = []
    for er in stage_rows:
        counts[er[1]] = counts.get(er[1], 0) + 1
        stages.append(
            StageRow(
                epoch_start_at=er[0],
                stage=er[1],
                source=er[2],
                confidence=float(er[3]) if er[3] is not None else None,
            )
        )

    return SessionDetail(
        id=str(sess[0]),
        started_at=sess[1],
        ended_at=sess[2],
        duration_seconds=int(sess[3] or 0),
        sensor_sources=list(sess[4] or []),
        notes=sess[5],
        stage_summary=_stage_summary(counts),
        stages=stages,
    )


@router.get("/{session_id}/state", response_model=SessionStateResponse)
def get_session_state(
    session_id: str,
    user_id: str = Depends(current_user_id),
) -> SessionStateResponse:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM sleep_sessions WHERE id = %s AND user_id = %s",
            (session_id, user_id),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="session not found")

        cur.execute(
            """
            SELECT estimated_at, stage_proba, arousal, valence, presence,
                   confidence, source
            FROM user_state_estimate
            WHERE session_id = %s
            ORDER BY estimated_at ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()

    states = [
        StateRow(
            estimated_at=r[0],
            stage_proba=r[1],
            arousal=float(r[2]) if r[2] is not None else None,
            valence=float(r[3]) if r[3] is not None else None,
            presence=float(r[4]) if r[4] is not None else None,
            confidence=float(r[5]) if r[5] is not None else None,
            source=r[6],
        )
        for r in rows
    ]
    return SessionStateResponse(session_id=session_id, states=states)


def _stage_summary(counts: dict[str, int]) -> StageSummary:
    total = sum(counts.values())
    if total == 0:
        return StageSummary()
    pct = {k: round(100.0 * v / total, 1) for k, v in counts.items()}
    return StageSummary(
        REM_pct=pct.get("REM", 0.0),
        CORE_pct=pct.get("CORE", 0.0),
        DEEP_pct=pct.get("DEEP", 0.0),
        AWAKE_pct=pct.get("AWAKE", 0.0),
    )
