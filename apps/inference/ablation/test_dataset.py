"""Dataset join (D1) — ledger labels ↔ beliefs, leakage guard, prior exclusion.

read_labels and get_conn are monkeypatched; no DATABASE_URL, no LLM.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelSource
from labels.record import LabelRecord
from ablation.config import AblationConfig
from ablation import dataset as ds_mod
from ablation.dataset import GradedPair, build_dataset

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _label(axis: str, source: LabelSource, minutes: int, value=0.5) -> LabelRecord:
    return LabelRecord(
        user_id="u1",
        axis=axis,
        value=value,
        source=source,
        observed_at=_T0 + timedelta(minutes=minutes),
        confidence=0.9,
    )


@contextmanager
def _fake_conn(belief_rows):
    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params=None): self._sql = sql
        def fetchall(self): return belief_rows
    class _Conn:
        def cursor(self): return _Cur()
    yield _Conn()


def _belief_row(source: str, minutes: int, value):
    # (axis, value, confidence, source, timestamp, meta_context, i_model_id)
    return ("arousal_inferred", {"value": value}, 0.8, source,
            _T0 + timedelta(minutes=minutes), None, None)


def test_build_dataset_matches_within_tol(monkeypatch) -> None:
    labels = [_label("arousal_inferred", LabelSource.SELF_REPORT, 0)]
    # belief 1 minute before the label -> within 300s tol
    beliefs = [_belief_row("eeg", -1, 0.5)]
    monkeypatch.setattr(ds_mod, "read_labels", lambda *a, **k: labels)
    monkeypatch.setattr(ds_mod, "get_conn", lambda: _fake_conn(beliefs))
    cfg = AblationConfig(tol_window_s=300)
    train, evald = build_dataset("u1", "arousal_inferred", cfg)
    all_pairs = train + evald
    assert len(all_pairs) == 1
    assert "eeg" in all_pairs[0].belief_inputs


def test_belief_outside_tol_excluded(monkeypatch) -> None:
    labels = [_label("arousal_inferred", LabelSource.SELF_REPORT, 0)]
    # belief 10 minutes before -> outside 300s tol -> no inputs matched
    beliefs = [_belief_row("eeg", -10, 0.5)]
    monkeypatch.setattr(ds_mod, "read_labels", lambda *a, **k: labels)
    monkeypatch.setattr(ds_mod, "get_conn", lambda: _fake_conn(beliefs))
    cfg = AblationConfig(tol_window_s=300)
    train, evald = build_dataset("u1", "arousal_inferred", cfg)
    pairs = train + evald
    # pair exists (label present) but no belief inputs joined
    assert len(pairs) == 1
    assert pairs[0].belief_inputs == {}


def test_time_holdout_split_no_overlap(monkeypatch) -> None:
    labels = [
        _label("arousal_inferred", LabelSource.SELF_REPORT, i) for i in range(10)
    ]
    beliefs = [_belief_row("eeg", i, 0.5) for i in range(10)]
    monkeypatch.setattr(ds_mod, "read_labels", lambda *a, **k: labels)
    monkeypatch.setattr(ds_mod, "get_conn", lambda: _fake_conn(beliefs))
    cfg = AblationConfig(tol_window_s=300)
    train, evald = build_dataset("u1", "arousal_inferred", cfg)
    assert len(train) > 0 and len(evald) > 0
    train_times = {p.observed_at for p in train}
    eval_times = {p.observed_at for p in evald}
    # leakage guard: no timestamp in both halves
    assert train_times.isdisjoint(eval_times)
    # older → train, newer → eval
    assert max(p.observed_at for p in train) <= min(p.observed_at for p in evald)


def test_priors_excluded_from_truth(monkeypatch) -> None:
    captured = {}
    def _capture_read(user_id, **kw):
        captured["sources"] = kw.get("sources")
        return []
    monkeypatch.setattr(ds_mod, "read_labels", _capture_read)
    monkeypatch.setattr(ds_mod, "get_conn", lambda: _fake_conn([]))
    cfg = AblationConfig()
    build_dataset("u1", "arousal_inferred", cfg)
    requested = set(captured["sources"])
    # only the four truth tiers are requested; priors never asked for
    assert LabelSource.GROUND_TRUTH in requested
    assert LabelSource.CLINICIAN in requested
    assert LabelSource.SELF_REPORT in requested
    assert LabelSource.OBSERVED_OUTCOME in requested
    assert LabelSource.HEURISTIC not in requested
    assert LabelSource.LITERATURE_PRIOR not in requested
    assert LabelSource.DEMOGRAPHIC_PRIOR not in requested
    assert LabelSource.LLM_LITERATURE_BOOTSTRAP not in requested


def test_db_absent_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr(ds_mod, "read_labels", lambda *a, **k: [])
    def _raise():
        raise RuntimeError("no DB")
    monkeypatch.setattr(ds_mod, "get_conn", _raise)
    cfg = AblationConfig()
    train, evald = build_dataset("u1", "arousal_inferred", cfg)
    assert train == [] and evald == []


def test_graded_pair_shape() -> None:
    p = GradedPair(
        observed_at=_T0,
        truth_value=0.5,
        truth_source=LabelSource.SELF_REPORT,
        truth_confidence=0.9,
        belief_inputs={"eeg": 0.5},
    )
    assert p.truth_source == LabelSource.SELF_REPORT
