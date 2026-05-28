from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio_context.privacy import PrivacyGate


def test_self_only_allows_everything():
    g = PrivacyGate(buffer_seconds=30)
    now = datetime.now(timezone.utc)
    d = g.evaluate(speakers=["self"], now=now)
    assert d.social_context == "self"
    assert d.allow_prosody and d.allow_ambient and d.allow_stt


def test_other_voice_suppresses_and_marks_both():
    g = PrivacyGate(buffer_seconds=30)
    now = datetime.now(timezone.utc)
    d = g.evaluate(speakers=["self", "other"], now=now)
    assert d.social_context == "both"
    assert not d.allow_prosody and not d.allow_ambient and not d.allow_stt
    assert d.suppressed_until == now + timedelta(seconds=30)


def test_suppression_persists_through_buffer_after_other_leaves():
    g = PrivacyGate(buffer_seconds=30)
    t0 = datetime.now(timezone.utc)
    g.evaluate(speakers=["other"], now=t0)                       # triggers suppression
    d = g.evaluate(speakers=["self"], now=t0 + timedelta(seconds=10))  # within buffer
    assert not d.allow_prosody and not d.allow_ambient
    d2 = g.evaluate(speakers=["self"], now=t0 + timedelta(seconds=31)) # past buffer
    assert d2.allow_prosody and d2.allow_ambient


def test_unknown_speaker_treated_as_other():
    g = PrivacyGate(buffer_seconds=30)
    now = datetime.now(timezone.utc)
    d = g.evaluate(speakers=["unknown"], now=now)
    assert d.social_context == "other"
    assert not d.allow_prosody


def test_silence_allows_ambient_only():
    g = PrivacyGate(buffer_seconds=30)
    now = datetime.now(timezone.utc)
    d = g.evaluate(speakers=[], now=now)
    assert d.social_context == "none"
    assert d.allow_ambient and not d.allow_prosody  # prosody needs voiced self-speech
