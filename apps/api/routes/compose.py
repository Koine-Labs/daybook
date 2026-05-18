"""Direct access to the generative composer (for debugging / testing)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api import _paths  # noqa: F401
from api.deps import current_user_id
from api.schemas import ComposeRequest, ComposeResponse


router = APIRouter(tags=["compose"])


@router.post("/compose", response_model=ComposeResponse)
def compose(
    body: ComposeRequest,
    user_id: str = Depends(current_user_id),
) -> ComposeResponse:
    from wisp.composer import compose_utterance

    try:
        composed = compose_utterance(
            user_id=user_id,
            moment_kind=body.moment_kind,
            explicit_context=body.explicit_context,
            retrieval_query=body.retrieval_query,
            retrieval_top_k=body.retrieval_top_k,
            persist=body.persist,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"compose failed: {e}")

    return ComposeResponse(
        text=composed.text,
        mode=composed.mode,
        retrieved=composed.retrieved,
        composition_seconds=composed.composition_seconds,
        model=composed.model,
        backend=composed.backend,
        persisted_moment_id=composed.persisted_moment_id,
    )
