"""Differentiated audio semantic packet writers (Week 3 taxonomy)."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from consent import CONSENT_SCOPES  # noqa: E402
from db import get_conn  # noqa: E402

SOURCE = "mic_listener_v1"
_SCOPE = CONSENT_SCOPES["voice"]


def _insert(user_id: str, kind: str, recorded_at: datetime, payload: dict[str, Any]) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sensor_readings
                (user_id, kind, recorded_at, source, payload, consent_scope)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
            """,
            (user_id, kind, recorded_at, SOURCE, json.dumps(payload), _SCOPE),
        )
        row = cur.fetchone()
        conn.commit()
    return str(row[0])


def write_social_context(user_id: str, recorded_at: datetime, *, speaker: str,
                         num_speakers: int, vad_active: bool) -> str:
    """speaker: 'self' | 'other' | 'both' | 'none'."""
    return _insert(user_id, "audio_social_context", recorded_at,
                   {"speaker": speaker, "num_speakers": num_speakers, "vad_active": vad_active})


def write_prosody(user_id: str, recorded_at: datetime, prosody: dict[str, Any]) -> str:
    return _insert(user_id, "audio_prosody", recorded_at, prosody)


def write_ambient(user_id: str, recorded_at: datetime, top_classes: list[dict[str, Any]]) -> str:
    return _insert(user_id, "audio_ambient", recorded_at, {"top_classes": top_classes})
