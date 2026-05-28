"""Pure VAD + diarization + prosody bundling into a single semantic packet.

Persistence lives in audio_context/writer.py (consent-stamped, privacy-gated).
This module never touches the DB — extraction only.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio_context.diarization import diarize
from audio_context.prosody import ProsodyFeatures, extract_prosody
from audio_context.vad import detect_voice_activity


@dataclass
class AudioContextPacket:
    started_at: datetime
    duration_ms: int
    vad_active: bool
    speakers: list[str]
    prosody: ProsodyFeatures
    payload: dict = field(default_factory=dict)


def _to_float32_mono(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio)
    if arr.ndim == 2:
        arr = arr.mean(axis=1)
    if arr.dtype == np.int16:
        arr = arr.astype(np.float32) / 32768.0
    elif arr.dtype == np.int32:
        arr = arr.astype(np.float32) / 2147483648.0
    elif arr.dtype != np.float32:
        arr = arr.astype(np.float32)
    return arr


def process_audio_chunk(
    audio: np.ndarray,
    sample_rate: int,
    *,
    started_at: datetime | None = None,
) -> AudioContextPacket:
    """Run VAD → diarization → prosody on a chunk; return semantic packet."""
    samples = _to_float32_mono(audio)
    duration_ms = int(round(samples.size / sample_rate * 1000))
    if started_at is None:
        started_at = datetime.now(timezone.utc)

    vad_segments = detect_voice_activity(samples, sample_rate)
    vad_active = len(vad_segments) > 0

    speakers: list[str] = []
    diarization_segments: list[dict] = []
    voiced_samples = samples
    if vad_active:
        diarization_segments = diarize(samples, sample_rate)
        speakers = sorted({s["speaker_id"] for s in diarization_segments})
        voiced_pieces = [
            samples[int(s["start_seconds"] * sample_rate) : int(s["end_seconds"] * sample_rate)]
            for s in vad_segments
        ]
        if voiced_pieces:
            voiced_samples = np.concatenate(voiced_pieces)

    prosody = extract_prosody(voiced_samples if vad_active else samples, sample_rate)

    payload = {
        "vad_active": vad_active,
        "vad_segments": [
            {
                "start_ms": int(round(s["start_seconds"] * 1000)),
                "end_ms": int(round(s["end_seconds"] * 1000)),
            }
            for s in vad_segments
        ],
        "speakers": speakers,
        "diarization": [
            {
                "start_ms": int(round(s["start_seconds"] * 1000)),
                "end_ms": int(round(s["end_seconds"] * 1000)),
                "speaker_id": s["speaker_id"],
            }
            for s in diarization_segments
        ],
        "tone": prosody.tone,
        "energy": prosody.energy,
        "pitch_mean_hz": prosody.pitch_mean_hz,
        "pitch_std_hz": prosody.pitch_std_hz,
        "speaking_rate_wpm": prosody.speaking_rate_wpm,
        "duration_ms": duration_ms,
        "sample_rate": sample_rate,
    }

    return AudioContextPacket(
        started_at=started_at,
        duration_ms=duration_ms,
        vad_active=vad_active,
        speakers=speakers,
        prosody=prosody,
        payload=payload,
    )
