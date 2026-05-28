from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio_context import writer


class _Cur:
    def __init__(self): self.calls = []
    def execute(self, sql, params): self.calls.append((sql, params))
    def fetchone(self): return ("row-id",)
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Conn:
    def __init__(self): self.cur_obj = _Cur(); self.committed = False
    def cursor(self): return self.cur_obj
    def commit(self): self.committed = True
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _patch(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(writer, "get_conn", lambda: conn)
    return conn


def test_write_social_context_stamps_consent(monkeypatch):
    conn = _patch(monkeypatch)
    now = datetime.now(timezone.utc)
    rid = writer.write_social_context("u1", now, speaker="other", num_speakers=2, vad_active=True)
    assert rid == "row-id"
    sql, params = conn.cur_obj.calls[0]
    assert "kind" in sql  # kind column present; the value is parameterized, not interpolated
    assert "audio_social_context" in params  # kind passed as a bound param
    assert "mic_continuous_v1" in params  # consent_scope present
    assert conn.committed


def test_write_prosody_and_ambient(monkeypatch):
    conn = _patch(monkeypatch)
    now = datetime.now(timezone.utc)
    writer.write_prosody("u1", now, {"energy": 0.1, "tone": "calm"})
    writer.write_ambient("u1", now, [{"class": "Speech", "score": 0.8}])
    kinds = [p for _sql, p in conn.cur_obj.calls]
    assert any("audio_prosody" in params for params in kinds)
    assert any("audio_ambient" in params for params in kinds)
