"""decide_promotions — beats-best-component, delta margin, hysteresis (A3, A5)."""
from __future__ import annotations

import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from ablation.config import AblationConfig
from ablation import promote as promote_mod
from ablation.promote import decide_promotions
from ablation.store import AblationResultRow


def _res(source_set, brier, dropped=None):
    return AblationResultRow(
        run_id="r1", user_id="u1", axis="arousal_inferred", meta_context=None,
        source_set=tuple(source_set), metrics=({} if dropped else {"brier": brier}),
        n_train_pairs=10, n_eval_pairs=10, grader="self_report",
        label_sources=["self_report"], beat_components=None, dropped_reason=dropped,
    )


def test_combo_beats_components(monkeypatch) -> None:
    monkeypatch.setattr(promote_mod, "read_existing_promotion", lambda *a, **k: None)
    results = [
        _res(("eeg",), 0.30),
        _res(("eog",), 0.25),
        _res(("eeg", "eog"), 0.10),  # beats best component (0.25)
    ]
    cfg = AblationConfig(delta=0.0, promote_streak=2)
    decisions = decide_promotions(results, cfg, "u1", "arousal_inferred", "r1", metric="brier")
    combo = next(d for d in decisions if d.source_set == ("eeg", "eog"))
    assert combo.beat_components is True
    assert combo.component_best == 0.25


def test_combo_does_not_beat_components(monkeypatch) -> None:
    monkeypatch.setattr(promote_mod, "read_existing_promotion", lambda *a, **k: None)
    results = [
        _res(("eeg",), 0.10),
        _res(("eog",), 0.25),
        _res(("eeg", "eog"), 0.15),  # worse than best component (0.10)
    ]
    cfg = AblationConfig(delta=0.0)
    decisions = decide_promotions(results, cfg, "u1", "arousal_inferred", "r1", metric="brier")
    combo = next(d for d in decisions if d.source_set == ("eeg", "eog"))
    assert combo.beat_components is False
    assert combo.status != "promoted"


def test_delta_margin_required(monkeypatch) -> None:
    monkeypatch.setattr(promote_mod, "read_existing_promotion", lambda *a, **k: None)
    results = [
        _res(("eeg",), 0.20),
        _res(("eog",), 0.22),
        _res(("eeg", "eog"), 0.18),  # only 0.02 better; delta=0.05 not met
    ]
    cfg = AblationConfig(delta=0.05)
    decisions = decide_promotions(results, cfg, "u1", "arousal_inferred", "r1", metric="brier")
    combo = next(d for d in decisions if d.source_set == ("eeg", "eog"))
    assert combo.beat_components is False


def test_singleton_has_no_components(monkeypatch) -> None:
    monkeypatch.setattr(promote_mod, "read_existing_promotion", lambda *a, **k: None)
    results = [_res(("eeg",), 0.10)]
    cfg = AblationConfig(delta=0.0)
    decisions = decide_promotions(results, cfg, "u1", "arousal_inferred", "r1", metric="brier")
    # a set with no graded strict subsets cannot "beat its components" -> not promoted
    d = decisions[0]
    assert d.beat_components is False


def test_hysteresis_promotes_on_streak(monkeypatch) -> None:
    # existing candidate with win_streak=1; this win makes streak=2 == promote_streak
    monkeypatch.setattr(
        promote_mod, "read_existing_promotion",
        lambda *a, **k: {"status": "candidate", "win_streak": 1},
    )
    results = [_res(("eeg",), 0.30), _res(("eog",), 0.25), _res(("eeg", "eog"), 0.10)]
    cfg = AblationConfig(delta=0.0, promote_streak=2)
    decisions = decide_promotions(results, cfg, "u1", "arousal_inferred", "r1", metric="brier")
    combo = next(d for d in decisions if d.source_set == ("eeg", "eog"))
    assert combo.win_streak == 2
    assert combo.status == "promoted"


def test_hysteresis_holds_candidate_before_streak(monkeypatch) -> None:
    monkeypatch.setattr(promote_mod, "read_existing_promotion", lambda *a, **k: None)
    results = [_res(("eeg",), 0.30), _res(("eog",), 0.25), _res(("eeg", "eog"), 0.10)]
    cfg = AblationConfig(delta=0.0, promote_streak=3)
    decisions = decide_promotions(results, cfg, "u1", "arousal_inferred", "r1", metric="brier")
    combo = next(d for d in decisions if d.source_set == ("eeg", "eog"))
    assert combo.win_streak == 1
    assert combo.status == "candidate"


def test_demotes_on_regression(monkeypatch) -> None:
    # was promoted; now loses -> win_streak resets, status flips to demoted
    monkeypatch.setattr(
        promote_mod, "read_existing_promotion",
        lambda *a, **k: {"status": "promoted", "win_streak": 4},
    )
    results = [_res(("eeg",), 0.10), _res(("eog",), 0.12), _res(("eeg", "eog"), 0.30)]
    cfg = AblationConfig(delta=0.0)
    decisions = decide_promotions(results, cfg, "u1", "arousal_inferred", "r1", metric="brier")
    combo = next(d for d in decisions if d.source_set == ("eeg", "eog"))
    assert combo.win_streak == 0
    assert combo.status == "demoted"


def test_dropped_sets_excluded_from_decisions(monkeypatch) -> None:
    monkeypatch.setattr(promote_mod, "read_existing_promotion", lambda *a, **k: None)
    results = [
        _res(("eeg",), 0.10),
        _res(("eeg", "eog", "mic"), 0.0, dropped="capped_by_max_set_size"),
    ]
    cfg = AblationConfig(delta=0.0)
    decisions = decide_promotions(results, cfg, "u1", "arousal_inferred", "r1", metric="brier")
    sets = {d.source_set for d in decisions}
    assert ("eeg", "eog", "mic") not in sets
