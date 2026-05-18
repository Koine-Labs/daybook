"""Read / write PERSONA.md (Regis's character bible, used as system prompt)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api import _paths
from api.schemas import (
    PersonaResponse,
    PersonaUpdateRequest,
    PersonaUpdateResponse,
)


router = APIRouter(tags=["persona"])


@router.get("/persona", response_model=PersonaResponse)
def get_persona() -> PersonaResponse:
    path = _paths.PERSONA_PATH
    if not path.exists():
        raise HTTPException(status_code=404, detail="PERSONA.md not found")
    content = path.read_text()
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return PersonaResponse(content=content, modified_at=mtime)


@router.put("/persona", response_model=PersonaUpdateResponse)
def put_persona(body: PersonaUpdateRequest) -> PersonaUpdateResponse:
    path = _paths.PERSONA_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = body.content.encode("utf-8")
    path.write_bytes(encoded)
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return PersonaUpdateResponse(modified_at=mtime, byte_count=len(encoded))
