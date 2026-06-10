"""Tests for the waking arc's DB-gated calibration wiring (#4 -> default arc)."""
from __future__ import annotations

import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

import db  # noqa: E402
from core.bus.bus import MessageBus  # noqa: E402
from runtime import waking_arc  # noqa: E402


def test_calibration_reader_is_none_without_database_url(monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_URL", None)
    assert waking_arc._calibration_reader() is None


def test_calibration_reader_is_get_calibration_when_db_configured(monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://fake/db")
    from arbitration import get_calibration

    assert waking_arc._calibration_reader() is get_calibration


def test_build_waking_arc_passes_reader_when_db_configured(monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://fake/db")
    captured: dict[str, object] = {}

    def recording_assemble(bus: MessageBus, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(waking_arc, "assemble_pipeline", recording_assemble)
    waking_arc.build_waking_arc()
    from arbitration import get_calibration

    assert captured["calibration_reader"] is get_calibration


def test_build_waking_arc_passes_no_reader_without_database_url(monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_URL", None)
    captured: dict[str, object] = {}

    def recording_assemble(bus: MessageBus, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(waking_arc, "assemble_pipeline", recording_assemble)
    waking_arc.build_waking_arc()

    assert captured["calibration_reader"] is None
