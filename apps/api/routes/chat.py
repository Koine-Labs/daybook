"""Chat conversations + message turns wrapped over apps/chat/handler.py."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api import _paths  # noqa: F401
from api.deps import current_user_id
from api.schemas import (
    ChatMessage,
    ConversationListItem,
    ConversationListResponse,
    ConversationOut,
    CreateConversationRequest,
    MessageListResponse,
    SendMessageRequest,
    SendMessageResponse,
    TraitDelta,
)

from db import get_conn  # noqa: E402


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(
    body: CreateConversationRequest,
    user_id: str = Depends(current_user_id),
) -> ConversationOut:
    from chat.conversation import create_conversation as _create

    conv_id = _create(user_id=user_id, title=body.title)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT started_at, title FROM chat_conversations WHERE id = %s",
            (conv_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="conversation insert failed")
    return ConversationOut(id=conv_id, started_at=row[0], title=row[1])


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    limit: int = Query(20, ge=1, le=200),
    user_id: str = Depends(current_user_id),
) -> ConversationListResponse:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.started_at, c.ended_at, c.title,
                   COUNT(m.id) AS msg_count,
                   MAX(m.sent_at) AS last_msg_at
            FROM chat_conversations c
            LEFT JOIN chat_messages m ON m.conversation_id = c.id
            WHERE c.user_id = %s
            GROUP BY c.id, c.started_at, c.ended_at, c.title
            ORDER BY COALESCE(MAX(m.sent_at), c.started_at) DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()

    items = [
        ConversationListItem(
            id=str(r[0]),
            started_at=r[1],
            ended_at=r[2],
            title=r[3],
            message_count=int(r[4] or 0),
            last_message_at=r[5],
        )
        for r in rows
    ]
    return ConversationListResponse(conversations=items)


@router.post(
    "/conversations/{conv_id}/messages",
    response_model=SendMessageResponse,
)
def send_message(
    conv_id: str,
    body: SendMessageRequest,
    user_id: str = Depends(current_user_id),
) -> SendMessageResponse:
    _ensure_conversation(conv_id, user_id)

    from chat.handler import handle_user_message

    try:
        resp = handle_user_message(
            user_id=user_id,
            conversation_id=conv_id,
            user_text=body.text,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"chat handler failed: {e}")

    return SendMessageResponse(
        user_message_id=resp.user_message_id,
        assistant_message_id=resp.assistant_message_id,
        text=resp.text,
        model=resp.model,
        backend=resp.backend,
        elapsed_ms=resp.elapsed_ms,
        observation_extracted=resp.observation_extracted,
        trait_deltas=[TraitDelta(**d) for d in resp.trait_deltas],
    )


@router.get(
    "/conversations/{conv_id}/messages",
    response_model=MessageListResponse,
)
def list_messages(
    conv_id: str,
    limit: int = Query(50, ge=1, le=500),
    before: datetime | None = Query(None),
    user_id: str = Depends(current_user_id),
) -> MessageListResponse:
    _ensure_conversation(conv_id, user_id)

    sql_parts: list[str] = [
        "SELECT id, role, content, sent_at, metadata",
        "FROM chat_messages",
        "WHERE conversation_id = %s",
    ]
    params: list[Any] = [conv_id]
    if before is not None:
        sql_parts.append("AND sent_at < %s")
        params.append(before)
    sql_parts.append("ORDER BY sent_at DESC")
    sql_parts.append("LIMIT %s")
    params.append(limit)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("\n".join(sql_parts), tuple(params))
        rows = list(reversed(cur.fetchall()))

    messages = [
        ChatMessage(
            id=str(r[0]),
            role=r[1],
            content=r[2],
            sent_at=r[3],
            metadata=r[4] or {},
        )
        for r in rows
    ]
    return MessageListResponse(messages=messages)


def _ensure_conversation(conv_id: str, user_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM chat_conversations WHERE id = %s AND user_id = %s",
            (conv_id, user_id),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="conversation not found")
