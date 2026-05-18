"""Dream recall capture + listing."""
from __future__ import annotations

import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from api import _paths
from api.deps import current_user_id
from api.schemas import (
    DreamDetail,
    DreamListItem,
    DreamListResponse,
    RecallResponse,
    RecallTextRequest,
)

from db import get_conn  # noqa: E402


router = APIRouter(tags=["recall"])


@router.post("/recall", response_model=RecallResponse)
def recall_text(
    body: RecallTextRequest,
    user_id: str = Depends(current_user_id),
) -> RecallResponse:
    """Text-mode recall — pass JSON {text, ack}."""
    from recall.capture import capture

    try:
        result = capture(text=body.text, user_id=user_id, ack=body.ack)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"recall failed: {e}")

    return RecallResponse(
        dream_recall_id=result.dream_recall_id,
        embedding_id=result.embedding_id,
        text=result.text,
        depth=result.depth,
        captured_at=result.captured_at,
        regis_utterance=result.regis_utterance,
    )


@router.post("/recall/audio", response_model=RecallResponse)
async def recall_audio(
    audio: UploadFile = File(...),
    ack: bool = Form(True),
    user_id: str = Depends(current_user_id),
) -> RecallResponse:
    """Audio-mode recall — multipart upload of a WAV; transcribed via Whisper."""
    from recall.capture import capture

    _paths.RECALL_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(audio.filename or "upload.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=suffix, dir=str(_paths.RECALL_AUDIO_DIR)
    ) as tmp:
        shutil.copyfileobj(audio.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        result = capture(audio_path=tmp_path, user_id=user_id, ack=ack)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"recall failed: {e}")

    return RecallResponse(
        dream_recall_id=result.dream_recall_id,
        embedding_id=result.embedding_id,
        text=result.text,
        depth=result.depth,
        captured_at=result.captured_at,
        regis_utterance=result.regis_utterance,
    )


@router.get("/dreams", response_model=DreamListResponse)
def list_dreams(
    limit: int = Query(50, ge=1, le=500),
    before: datetime | None = Query(None),
    q: str | None = Query(None, description="Optional semantic query for ranking"),
    user_id: str = Depends(current_user_id),
) -> DreamListResponse:
    """List dream recalls; if `q` is provided, rank by embedding similarity."""
    if q:
        try:
            from embeddings import retrieve_similar

            hits = retrieve_similar(
                q, user_id=user_id, top_k=limit, source_types=["dream_recall"]
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"retrieval failed: {e}")

        if not hits:
            return DreamListResponse(dreams=[])

        ids = [h.source_id for h in hits]
        sim_by_id = {h.source_id: h.similarity for h in hits}
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, captured_at, depth, raw_text, themes
                FROM dream_recalls
                WHERE user_id = %s AND id = ANY(%s)
                """,
                (user_id, ids),
            )
            rows = cur.fetchall()
        rows_by_id = {str(r[0]): r for r in rows}
        ordered: list[DreamListItem] = []
        for did in ids:
            r = rows_by_id.get(did)
            if r is None:
                continue
            ordered.append(
                DreamListItem(
                    id=str(r[0]),
                    captured_at=r[1],
                    depth=r[2],
                    raw_text=r[3],
                    themes=list(r[4] or []),
                    similarity=round(float(sim_by_id[did]), 3),
                )
            )
        return DreamListResponse(dreams=ordered)

    sql_parts = [
        "SELECT id, captured_at, depth, raw_text, themes",
        "FROM dream_recalls",
        "WHERE user_id = %s",
    ]
    params: list[Any] = [user_id]
    if before is not None:
        sql_parts.append("AND captured_at < %s")
        params.append(before)
    sql_parts.append("ORDER BY captured_at DESC")
    sql_parts.append("LIMIT %s")
    params.append(limit)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("\n".join(sql_parts), tuple(params))
        rows = cur.fetchall()

    items = [
        DreamListItem(
            id=str(r[0]),
            captured_at=r[1],
            depth=r[2],
            raw_text=r[3],
            themes=list(r[4] or []),
        )
        for r in rows
    ]
    return DreamListResponse(dreams=items)


@router.get("/dreams/{dream_id}", response_model=DreamDetail)
def get_dream(
    dream_id: str,
    user_id: str = Depends(current_user_id),
) -> DreamDetail:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, captured_at, depth, raw_text, voice_memo_url, themes, session_id
            FROM dream_recalls
            WHERE user_id = %s AND id = %s
            """,
            (user_id, dream_id),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="dream not found")
    return DreamDetail(
        id=str(row[0]),
        captured_at=row[1],
        depth=row[2],
        raw_text=row[3],
        voice_memo_url=row[4],
        themes=list(row[5] or []),
        session_id=str(row[6]) if row[6] else None,
    )
