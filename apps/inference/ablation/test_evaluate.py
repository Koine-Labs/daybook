"""evaluate_axis — every candidate yields a row; dropped reasons are explicit (A4)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelSource
from ablation.backend import MacScaffoldBackend
from ablation.config import AblationConfig
from ablation.dataset import GradedPair
from ablation import evaluate as ev_mod
from ablation.evaluate import evaluate_axis

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _pairs(n: int, with_input: bool = True):
    out = []
    for i in range(n):
        val = i / max(1, n - 1)
        inputs = {"eeg": val, "eog": val} if with_input else {}
        out.append(
            GradedPair(
                observed_at=_T0 + timedelta(minutes=i),
                truth_value=val,
                truth_source=LabelSource.SELF_REPORT,
                truth_confidence=0.9,
                belief_inputs=inputs,
            )
        )
    return out


def test_every_candidate_yields_a_row(monkeypatch) -> None:
    train, evald = _pairs(14)[:10], _pairs(14)[10:]
    monkeypatch.setattr(ev_mod, "build_dataset", lambda u, a, c: (train, evald))
    monkeypatch.setattr(ev_mod, "available_sources_for_axis", lambda u, a: ["eeg", "eog"])
    cfg = AblationConfig(max_set_size=3, min_labels=1)
    rows = evaluate_axis("u1", "arousal_inferred", cfg, MacScaffoldBackend(), "run1")
    sets = {r.source_set for r in rows}
    # power set of {eeg,eog}: 3 candidates, all present
    assert sets == {("eeg",), ("eog",), ("eeg", "eog")}


def test_capped_sets_get_dropped_reason(monkeypatch) -> None:
    train, evald = _pairs(14)[:10], _pairs(14)[10:]
    monkeypatch.setattr(ev_mod, "build_dataset", lambda u, a, c: (train, evald))
    monkeypatch.setattr(
        ev_mod, "available_sources_for_axis", lambda u, a: ["eeg", "eog", "mic"]
    )
    cfg = AblationConfig(max_set_size=2, min_labels=1)
    rows = evaluate_axis("u1", "arousal_inferred", cfg, MacScaffoldBackend(), "run1")
    capped = [r for r in rows if r.dropped_reason == "capped_by_max_set_size"]
    assert any(r.source_set == ("eeg", "eog", "mic") for r in capped)
    # capped rows still carry the grader field (NOT NULL in DB)
    for r in capped:
        assert r.grader


def test_insufficient_data_reason(monkeypatch) -> None:
    train, evald = _pairs(4)[:3], _pairs(4)[3:]  # only 1 eval pair
    monkeypatch.setattr(ev_mod, "build_dataset", lambda u, a, c: (train, evald))
    monkeypatch.setattr(ev_mod, "available_sources_for_axis", lambda u, a: ["eeg"])
    cfg = AblationConfig(max_set_size=1, min_labels=8)
    rows = evaluate_axis("u1", "arousal_inferred", cfg, MacScaffoldBackend(), "run1")
    assert all(r.dropped_reason == "insufficient_data" for r in rows)


def test_no_matched_pairs_reason(monkeypatch) -> None:
    monkeypatch.setattr(ev_mod, "build_dataset", lambda u, a, c: ([], []))
    monkeypatch.setattr(ev_mod, "available_sources_for_axis", lambda u, a: ["eeg"])
    cfg = AblationConfig(min_labels=1)
    rows = evaluate_axis("u1", "arousal_inferred", cfg, MacScaffoldBackend(), "run1")
    assert all(r.dropped_reason == "no_matched_pairs" for r in rows)


def test_graded_rows_have_metrics(monkeypatch) -> None:
    train, evald = _pairs(14)[:10], _pairs(14)[10:]
    monkeypatch.setattr(ev_mod, "build_dataset", lambda u, a, c: (train, evald))
    monkeypatch.setattr(ev_mod, "available_sources_for_axis", lambda u, a: ["eeg"])
    cfg = AblationConfig(max_set_size=1, min_labels=1)
    rows = evaluate_axis("u1", "arousal_inferred", cfg, MacScaffoldBackend(), "run1")
    graded = [r for r in rows if r.dropped_reason is None]
    assert graded
    for r in graded:
        assert "brier" in r.metrics
        assert r.n_eval_pairs > 0
