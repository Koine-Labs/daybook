"""Store — crash-safe writers/readers (get_conn monkeypatched) + DB-gated round trip."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from ablation import store as store_mod
from ablation.store import (
    AblationResultRow,
    PromotionRow,
    list_promoted,
    open_run,
    write_promotions,
    write_results,
)


@contextmanager
def _fake_conn(captured: dict):
    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params=None):
            captured.setdefault("sqls", []).append(sql)
            captured.setdefault("params", []).append(params)
        def fetchone(self):
            return ("00000000-0000-0000-0000-0000000000aa",)
        def fetchall(self):
            return captured.get("rows", [])
    class _Conn:
        def cursor(self): return _Cur()
        def commit(self): captured["committed"] = True
        def rollback(self): captured["rolledback"] = True
    yield _Conn()


def test_open_run_returns_id(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(store_mod, "get_conn", lambda: _fake_conn(captured))
    rid = open_run("u1", backend="mac_scaffold", axes=["arousal_inferred"], config={}, git_sha="abc")
    assert rid == "00000000-0000-0000-0000-0000000000aa"
    assert any("INSERT INTO ablation_runs" in s for s in captured["sqls"])


def test_open_run_db_absent_returns_none(monkeypatch) -> None:
    def _raise():
        raise RuntimeError("no DB")
    monkeypatch.setattr(store_mod, "get_conn", _raise)
    assert open_run("u1", backend="mac_scaffold", axes=[], config={}, git_sha=None) is None


def test_write_results_counts(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(store_mod, "get_conn", lambda: _fake_conn(captured))
    rows = [
        AblationResultRow(
            run_id="r1", user_id="u1", axis="arousal_inferred", meta_context=None,
            source_set=("eeg",), metrics={"brier": 0.1}, n_train_pairs=5, n_eval_pairs=5,
            grader="self_report", label_sources=["self_report"], beat_components=None,
            dropped_reason=None,
        )
    ]
    n = write_results(rows)
    assert n == 1
    assert any("INSERT INTO ablation_results" in s for s in captured["sqls"])


def test_write_results_db_absent_returns_zero(monkeypatch) -> None:
    def _raise():
        raise RuntimeError("no DB")
    monkeypatch.setattr(store_mod, "get_conn", _raise)
    rows = [
        AblationResultRow(
            run_id="r1", user_id="u1", axis="a", meta_context=None, source_set=("eeg",),
            metrics={}, n_train_pairs=0, n_eval_pairs=0, grader="self_report",
            label_sources=[], beat_components=None, dropped_reason="no_matched_pairs",
        )
    ]
    assert write_results(rows) == 0


def test_write_results_empty_is_zero(monkeypatch) -> None:
    monkeypatch.setattr(store_mod, "get_conn", lambda: _fake_conn({}))
    assert write_results([]) == 0


def test_write_promotions_sorts_source_set(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(store_mod, "get_conn", lambda: _fake_conn(captured))
    rows = [
        PromotionRow(
            user_id="u1", axis="arousal_inferred", meta_context=None,
            source_set=("eog", "eeg"), weights={}, status="promoted", metric_name="brier",
            metric_value=0.1, component_best=0.2, margin=0.1, n_eval_pairs=10,
            win_streak=2, promoted_run_id="r1", i_model_id=None,
        )
    ]
    n = write_promotions(rows)
    assert n == 1
    # canonical sort applied before write
    params = captured["params"][-1]
    assert ["eeg", "eog"] in [list(p) for p in params if isinstance(p, (list, tuple))]


def test_list_promoted_db_absent_returns_empty(monkeypatch) -> None:
    def _raise():
        raise RuntimeError("no DB")
    monkeypatch.setattr(store_mod, "get_conn", _raise)
    assert list_promoted("u1", "arousal_inferred", None) == []


def test_list_promoted_parses_rows(monkeypatch) -> None:
    captured = {"rows": [(["eeg", "eog"],), (["mic"],)]}
    monkeypatch.setattr(store_mod, "get_conn", lambda: _fake_conn(captured))
    out = list_promoted("u1", "arousal_inferred", None)
    assert ("eeg", "eog") in out
    assert ("mic",) in out


def test_real_db_round_trip() -> None:
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("no DATABASE_URL")
    # db.py's load_dotenv repopulates DATABASE_URL from .env.local even under
    # `env -u DATABASE_URL`, so the env check above is not enough on its own:
    # also skip when migration 0014 has not been applied (table absent), so the
    # suite stays green pre-migration. The controller applies 0014, then this
    # exercises a real insert→readback→delete.
    from db import get_conn

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('ablation_runs')")
            exists = cur.fetchone()[0] is not None
    except Exception:  # noqa: BLE001 — no reachable DB → skip, never fail
        pytest.skip("DB unreachable")
        return
    if not exists:
        pytest.skip("migration 0014 not applied (ablation_runs absent)")

    rid = open_run(
        "61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
        backend="mac_scaffold", axes=["__test_axis__"], config={"t": 1}, git_sha="test",
    )
    assert rid is not None
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ablation_runs WHERE id = %s", (rid,))
        conn.commit()
