"""Smoke test for audio_context: synthesize → process → persist → cleanup."""

from __future__ import annotations

import json
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio_context.processor import (
    AudioContextPacket,
    persist_packet,
    process_audio_chunk,
)
from db import get_conn

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
SMOKE_SOURCE = "audio_context_smoke"
SAMPLE_RATE = 16000


def _load_existing_wav() -> tuple[np.ndarray, int] | None:
    candidate_dir = Path.home() / ".daybook" / "recall_audio"
    if not candidate_dir.exists():
        return None
    for wav_path in sorted(candidate_dir.glob("*.wav")):
        if "silent" in wav_path.name.lower():
            continue
        try:
            with wave.open(str(wav_path), "rb") as wf:
                if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
                    continue
                sr = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if samples.size / sr >= 1.0:
                print(f"[smoke] loaded real wav: {wav_path.name} ({samples.size / sr:.1f}s @ {sr}Hz)")
                return samples, sr
        except Exception:
            continue
    return None


def _synthesize_speech_like() -> tuple[np.ndarray, int]:
    """3s silence + 2s formant-modulated chirp + 3s silence."""
    sr = SAMPLE_RATE
    rng = np.random.default_rng(42)

    silence_a = np.zeros(int(3.0 * sr), dtype=np.float32)
    silence_b = np.zeros(int(3.0 * sr), dtype=np.float32)

    voiced_dur = 2.0
    t = np.linspace(0, voiced_dur, int(voiced_dur * sr), endpoint=False, dtype=np.float32)
    # F0 contour around 140 Hz (male-ish) with vibrato.
    f0 = 140.0 + 8.0 * np.sin(2 * np.pi * 5.0 * t)
    phase = 2 * np.pi * np.cumsum(f0) / sr
    voiced = 0.6 * np.sin(phase)
    # Add a couple of harmonics to look speech-like.
    voiced += 0.3 * np.sin(2 * phase)
    voiced += 0.15 * np.sin(3 * phase)
    # AM envelope to simulate syllables.
    voiced *= 0.4 + 0.6 * (np.sin(2 * np.pi * 3.5 * t) ** 2)
    voiced += 0.01 * rng.standard_normal(voiced.size).astype(np.float32)
    voiced = voiced.astype(np.float32) * 0.4

    audio = np.concatenate([silence_a, voiced, silence_b])
    return audio, sr


def _cleanup(row_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM sensor_readings WHERE id = %s AND source = %s",
            (row_id, SMOKE_SOURCE),
        )
        conn.commit()


def run() -> int:
    real = _load_existing_wav()
    if real is not None:
        audio, sr = real
        scenario = "real wav"
    else:
        audio, sr = _synthesize_speech_like()
        scenario = "synthetic 3s silence + 2s voiced + 3s silence"

    print(f"[smoke] scenario: {scenario}")
    print(f"[smoke] audio: shape={audio.shape}, dtype={audio.dtype}, sr={sr}")

    started = datetime.now(timezone.utc)
    packet: AudioContextPacket = process_audio_chunk(audio, sr, started_at=started)

    print()
    print("=== AudioContextPacket ===")
    print(f"started_at      : {packet.started_at.isoformat()}")
    print(f"duration_ms     : {packet.duration_ms}")
    print(f"vad_active      : {packet.vad_active}")
    print(f"speakers        : {packet.speakers}")
    print(f"prosody.tone    : {packet.prosody.tone}")
    print(f"prosody.energy  : {packet.prosody.energy}")
    print(f"prosody.pitch_mu: {packet.prosody.pitch_mean_hz} Hz")
    print(f"prosody.pitch_sd: {packet.prosody.pitch_std_hz} Hz")
    print()
    print("payload:")
    print(json.dumps(packet.payload, indent=2))

    assert packet.duration_ms > 0, "duration_ms must be positive"
    assert "vad_segments" in packet.payload
    assert "tone" in packet.payload
    if real is None:
        # synthetic test: middle 3.0-5.0s region should be detected as speech.
        assert packet.vad_active, "VAD should detect synthetic voiced region"
        starts = [s["start_ms"] for s in packet.payload["vad_segments"]]
        assert any(2500 <= s <= 3500 for s in starts), (
            f"expected voiced region near t=3000ms, got starts={starts}"
        )
        print("[smoke] VAD correctly located synthetic voiced region.")

    row_id = persist_packet(packet, user_id=DEFAULT_USER_ID, source=SMOKE_SOURCE)
    print(f"[smoke] persisted row id: {row_id}")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT kind, source, payload FROM sensor_readings WHERE id = %s",
            (row_id,),
        )
        row = cur.fetchone()
    assert row is not None, "row should exist after persist"
    assert row[0] == "audio_segment"
    assert row[1] == SMOKE_SOURCE
    assert row[2]["vad_active"] == packet.vad_active
    print(f"[smoke] verified row: kind={row[0]} source={row[1]}")

    _cleanup(row_id)
    print(f"[smoke] cleaned up row {row_id}")
    print()
    print("[smoke] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
