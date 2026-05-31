"""DB-free tests for the impure seams: arbiter.recompute_axis + read.get_calibration.

get_conn and ledger.read_labels are monkeypatched; no DATABASE_URL, no LLM.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

import arbitration.arbiter as arbiter_mod
import arbitration.read as read_mod
from arbitration import BlendResult, CalibrationState
from labels import LabelRecord, LabelSource

NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)


class _FakeCursor:
    def __init__(self, scripted):
        self._scripted = scripted  # list of fetchone/fetchall returns, consumed per-execute
        self.executed = []
        self._last = None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._last = self._scripted.pop(0) if self._scripted else None

    def fetchone(self):
        return self._last

    def fetchall(self):
        return self._last or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch(monkeypatch, mod, cursor):
    @contextmanager
    def fake_get_conn():
        yield _FakeConn(cursor)

    monkeypatch.setattr(mod, "get_conn", fake_get_conn)


def _rec(source, axis="arousal"):
    return LabelRecord(
        user_id="u", axis=axis, value=0.5, source=source,
        observed_at=NOW, confidence=1.0,
    )


# --- recompute_axis --------------------------------------------------------

def test_recompute_axis_db_absent_is_crash_safe_returns_blendresult(monkeypatch):
    # get_conn raises (no DB) -> must not crash; returns a default cold_start result.
    @contextmanager
    def boom():
        raise RuntimeError("no DB")
        yield  # pragma: no cover

    monkeypatch.setattr(arbiter_mod, "get_conn", boom)
    monkeypatch.setattr(arbiter_mod, "read_labels", lambda *a, **k: [])

    res = arbiter_mod.recompute_axis("u", "arousal", now=NOW)
    assert isinstance(res, BlendResult)
    assert res.w_personal == 0.0
    assert res.calibration_state is CalibrationState.COLD_START


def test_recompute_axis_blends_personal_evidence(monkeypatch):
    # profile row present; ledger returns strong self-report evidence.
    profile_row = (
        0.1,    # population_value
        0.8,    # population_variance
        "lit",  # literature_source
        8.0,    # e_half
        0.5, 0.25, 6.0, 4.0,  # e_cs_enter, e_cs_exit, e_cal_enter, e_cal_exit
        None,   # tier_trust json
        None,   # tier_halflife_s json
        None,   # prev calibration_state (no axis_calibration row yet)
    )
    cursor = _FakeCursor([
        profile_row,   # SELECT cold_start_profiles
        None,          # SELECT axis_calibration prev state
        None,          # SELECT user_demographics
        None,          # UPSERT axis_calibration RETURNING
        None,          # INSERT history
    ])
    _patch(monkeypatch, arbiter_mod, cursor)
    monkeypatch.setattr(
        arbiter_mod, "read_labels",
        lambda *a, **k: [_rec(LabelSource.SELF_REPORT) for _ in range(20)],
    )

    res = arbiter_mod.recompute_axis("u", "arousal", now=NOW)
    assert res.w_personal > 0.0
    assert res.population_value == 0.1
    assert res.population_variance == 0.8
    # an UPSERT and at least one execute happened
    assert any("axis_calibration" in sql for sql, _ in cursor.executed)


def test_recompute_axis_seeds_defaults_when_no_profile(monkeypatch):
    cursor = _FakeCursor([
        None,   # SELECT cold_start_profiles -> none
        None,   # SELECT axis_calibration prev
        None,   # SELECT user_demographics
        None,   # UPSERT
        None,   # history
    ])
    _patch(monkeypatch, arbiter_mod, cursor)
    monkeypatch.setattr(arbiter_mod, "read_labels", lambda *a, **k: [])

    res = arbiter_mod.recompute_axis("u", "novel_axis", now=NOW)
    assert res.axis == "novel_axis"
    assert res.calibration_state is CalibrationState.COLD_START


# --- read.get_calibration --------------------------------------------------

def test_get_calibration_reads_materialized_row(monkeypatch):
    row = (
        0.6,                 # w_personal
        "calibrating",       # calibration_state
        3.0,                 # e_personal
        0.1,                 # population_value (joined from profile or stored)
        0.8,                 # population_variance
        False,               # demographics_applied
    )
    cursor = _FakeCursor([row])
    _patch(monkeypatch, read_mod, cursor)

    res = read_mod.get_calibration("u", "arousal")
    assert res.w_personal == 0.6
    assert res.w_population == pytest.approx(0.4)
    assert res.calibration_state is CalibrationState.CALIBRATING
    assert res.population_value == 0.1


def test_get_calibration_missing_row_lazily_seeds_cold_start(monkeypatch):
    cursor = _FakeCursor([
        None,   # SELECT axis_calibration -> none
        None,   # SELECT cold_start_profiles for population fallback -> none
    ])
    _patch(monkeypatch, read_mod, cursor)

    res = read_mod.get_calibration("u", "arousal")
    assert res.w_personal == 0.0
    assert res.calibration_state is CalibrationState.COLD_START


def test_get_calibration_db_absent_is_crash_safe(monkeypatch):
    @contextmanager
    def boom():
        raise RuntimeError("no DB")
        yield  # pragma: no cover

    monkeypatch.setattr(read_mod, "get_conn", boom)
    res = read_mod.get_calibration("u", "arousal")
    assert isinstance(res, BlendResult)
    assert res.w_personal == 0.0
    assert res.calibration_state is CalibrationState.COLD_START
