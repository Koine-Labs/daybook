from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

APPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(APPS / "inference"))

from voice.continuous import ContinuousProcessor


def test_self_speech_emits_social_and_prosody(monkeypatch):
    writes = []
    proc = ContinuousProcessor(
        user_id="u1",
        identify_speakers=lambda audio, sr: ["self"],
        prosody_of=lambda audio, sr: {"energy": 0.2, "tone": "calm"},
        ambient_of=lambda audio, sr: [],
        write_social=lambda **k: writes.append(("social", k)),
        write_prosody=lambda **k: writes.append(("prosody", k)),
        write_ambient=lambda **k: writes.append(("ambient", k)),
    )
    now = datetime.now(timezone.utc)
    proc.process_window(np.ones(16000, dtype=np.float32), 16000, vad_active=True, now=now)
    kinds = [w[0] for w in writes]
    assert "social" in kinds and "prosody" in kinds
    assert writes[0][1]["speaker"] == "self"


def test_other_voice_emits_social_only(monkeypatch):
    writes = []
    proc = ContinuousProcessor(
        user_id="u1",
        identify_speakers=lambda audio, sr: ["self", "other"],
        prosody_of=lambda audio, sr: {"energy": 0.2, "tone": "calm"},
        ambient_of=lambda audio, sr: [{"class": "Speech", "score": 0.9}],
        write_social=lambda **k: writes.append(("social", k)),
        write_prosody=lambda **k: writes.append(("prosody", k)),
        write_ambient=lambda **k: writes.append(("ambient", k)),
    )
    now = datetime.now(timezone.utc)
    proc.process_window(np.ones(16000, dtype=np.float32), 16000, vad_active=True, now=now)
    kinds = [w[0] for w in writes]
    assert kinds == ["social"]            # privacy gate suppressed prosody + ambient
    assert writes[0][1]["speaker"] == "both"


def test_silence_emits_ambient(monkeypatch):
    writes = []
    proc = ContinuousProcessor(
        user_id="u1",
        identify_speakers=lambda audio, sr: [],
        prosody_of=lambda audio, sr: {"energy": 0.0, "tone": "flat"},
        ambient_of=lambda audio, sr: [{"class": "Silence", "score": 0.95}],
        write_social=lambda **k: writes.append(("social", k)),
        write_prosody=lambda **k: writes.append(("prosody", k)),
        write_ambient=lambda **k: writes.append(("ambient", k)),
    )
    now = datetime.now(timezone.utc)
    proc.process_window(np.zeros(16000, dtype=np.float32), 16000, vad_active=False, now=now)
    kinds = [w[0] for w in writes]
    assert "ambient" in kinds and "prosody" not in kinds
