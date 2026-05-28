"""Persist audio_context packets into sensor_readings as kind='audio_context'.

This is the runtime hand-off point: mic_listener captures a voiced segment,
hands the np.ndarray to processor.process_audio_chunk(), then this module
writes the resulting prosody packet so the chat layer can read it as
"how the user sounded right now" between turns.

Never raises — failures are logged and return None so the live voice loop
isn't taken down by a transient DB issue.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from audio_context.processor import AudioContextPacket, process_audio_chunk
from db import get_conn

logger = logging.getLogger(__name__)

KIND = "audio_context"
DEFAULT_SOURCE = "mic_listener_v1"


def persist_audio_packet(
    user_id: str,
    packet: dict | AudioContextPacket,
    *,
    source: str = DEFAULT_SOURCE,
) -> str | None:
    """Write one sensor_readings row with kind='audio_context'.

    Accepts either a raw payload dict or an AudioContextPacket (the latter is
    flattened to its .payload). Returns the new row id, or None on any failure
    (DB unavailable, malformed payload, etc.) — never raises.
    """
    try:
        if isinstance(packet, AudioContextPacket):
            payload = dict(packet.payload)
            recorded_at = packet.started_at
        else:
            payload = dict(packet)
            recorded_at = datetime.now(timezone.utc)

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sensor_readings
                    (user_id, recorded_at, kind, source, payload)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    user_id,
                    recorded_at,
                    KIND,
                    source,
                    json.dumps(payload),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return str(row[0]) if row else None
    except Exception:
        logger.exception("persist_audio_packet failed (user_id=%s)", user_id)
        return None


def _record_default_mic(seconds: float, sample_rate: int = 16000) -> np.ndarray:
    """Block-record `seconds` from the default mic as float32 mono."""
    import sounddevice as sd

    print(f"[persistor] recording {seconds:.1f}s @ {sample_rate} Hz...")
    audio = sd.rec(
        int(round(seconds * sample_rate)),
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return audio.reshape(-1)


def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    user_id = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
    sample_rate = 16000
    audio = _record_default_mic(5.0, sample_rate=sample_rate)
    packet = process_audio_chunk(audio, sample_rate, started_at=datetime.now(timezone.utc))
    print(
        f"[persistor] packet: vad_active={packet.vad_active} "
        f"tone={packet.prosody.tone} energy={packet.prosody.energy} "
        f"pitch_mean={packet.prosody.pitch_mean_hz}Hz pitch_std={packet.prosody.pitch_std_hz}Hz"
    )
    row_id = persist_audio_packet(user_id, packet, source="persistor_cli")
    if row_id is None:
        print("[persistor] persist FAILED (see log)")
        return 1
    print(f"[persistor] row id: {row_id}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
