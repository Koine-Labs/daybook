"""Health check — reports DB, LLM, embeddings, content counters."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api import _paths  # noqa: F401
from api.deps import current_user_id
from api.schemas import HealthResponse

from db import get_conn  # noqa: E402


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(user_id: str = Depends(current_user_id)) -> HealthResponse:
    db_connected = False
    last_dream_at = None
    total_dreams = 0
    total_chat_messages = 0
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
            db_connected = True

            cur.execute(
                "SELECT MAX(captured_at), COUNT(*) FROM dream_recalls WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            last_dream_at = row[0]
            total_dreams = int(row[1] or 0)

            cur.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE user_id = %s",
                (user_id,),
            )
            total_chat_messages = int(cur.fetchone()[0] or 0)
    except Exception:
        db_connected = False

    llm_signed_in = False
    llm_email: str | None = None
    try:
        from llm.auth.session import get_sign_in_status

        status = get_sign_in_status()
        llm_signed_in = bool(status.signed_in)
        if status.identity is not None:
            llm_email = getattr(status.identity, "email", None)
    except Exception:
        pass

    embeddings_loaded = False
    try:
        from embeddings.model import get_model

        embeddings_loaded = get_model.cache_info().currsize > 0  # type: ignore[attr-defined]
    except Exception:
        embeddings_loaded = False

    return HealthResponse(
        db_connected=db_connected,
        llm_signed_in=llm_signed_in,
        llm_account_email=llm_email,
        embeddings_loaded=embeddings_loaded,
        last_dream_at=last_dream_at,
        total_dreams=total_dreams,
        total_chat_messages=total_chat_messages,
    )
