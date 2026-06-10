"""runner — end-to-end on synthetic data, DB mocked; promotion needs the streak."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelSource
from ablation.config import AblationConfig
from ablation.dataset import GradedPair
from ablation import runner as runner_mod
from ablation import promote as promote_mod
from ablation import evaluate as ev_mod
from ablation.runner import run_ablation

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_pairs(n: int, combo_helps: bool):
    """Synthetic: truth tracks eeg; eog adds signal only when combo_helps."""
    out = []
    for i in range(n):
        t = i / (n - 1)
        # combo_helps must give the pair a wide, BLAS-independent margin: each
        # source carries half the truth plus an alternating residual the other
        # cancels. Identical sources (the old t*0.5 both) made combo-vs-single
        # a floating-point coin flip — promoted on macOS Accelerate, not on
        # Ubuntu OpenBLAS.
        d = 0.15 if i % 2 == 0 else -0.15
        eeg = t if not combo_helps else (t * 0.5 + d)
        eog = 0.5 if not combo_helps else (t * 0.5 - d)
        out.append(
            GradedPair(
                observed_at=_T0 + timedelta(minutes=i),
                truth_value=t,
                truth_source=LabelSource.SELF_REPORT,
                truth_confidence=0.9,
                belief_inputs={"eeg": eeg, "eog": eog},
            )
        )
    return out


def _patch_common(monkeypatch, combo_helps=True):
    pairs = _make_pairs(40, combo_helps)
    split = 28
    monkeypatch.setattr(ev_mod, "build_dataset", lambda u, a, c: (pairs[:split], pairs[split:]))
    monkeypatch.setattr(ev_mod, "available_sources_for_axis", lambda u, a: ["eeg", "eog"])
    # DB writes all no-op (crash-safe paths return ids/counts but we mock store)
    monkeypatch.setattr(runner_mod, "open_run", lambda *a, **k: "run-xyz")
    monkeypatch.setattr(runner_mod, "close_run", lambda *a, **k: True)
    monkeypatch.setattr(runner_mod, "write_results", lambda rows: len(rows))
    monkeypatch.setattr(runner_mod, "write_promotions", lambda rows: len(rows))


def test_run_returns_report_and_manifest(monkeypatch) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(promote_mod, "read_existing_promotion", lambda *a, **k: None)
    cfg = AblationConfig(min_labels=2, promote_streak=2)
    out = run_ablation("u1", ["arousal_inferred"], cfg, dry_run=True)
    assert "manifest" in out
    assert "markdown" in out
    assert "arousal_inferred" in out["manifest"]["axes"]


def test_winning_set_not_promoted_on_first_run(monkeypatch) -> None:
    _patch_common(monkeypatch, combo_helps=True)
    monkeypatch.setattr(promote_mod, "read_existing_promotion", lambda *a, **k: None)
    cfg = AblationConfig(min_labels=2, promote_streak=2)
    out = run_ablation("u1", ["arousal_inferred"], cfg, dry_run=True)
    promoted = out["manifest"]["axes"]["arousal_inferred"]["promoted"]
    # first run: streak=1 < 2, so the combo is a candidate, not promoted yet
    assert ("eeg", "eog") not in [tuple(s) for s in promoted]


def test_winning_set_promotes_after_streak(monkeypatch) -> None:
    _patch_common(monkeypatch, combo_helps=True)
    # second run: prior streak=1 -> this win makes streak=2 == promote_streak
    monkeypatch.setattr(
        promote_mod, "read_existing_promotion",
        lambda u, a, m, s: {"status": "candidate", "win_streak": 1}
        if tuple(s) == ("eeg", "eog") else None,
    )
    cfg = AblationConfig(min_labels=2, promote_streak=2)
    out = run_ablation("u1", ["arousal_inferred"], cfg, dry_run=True)
    promoted = [tuple(s) for s in out["manifest"]["axes"]["arousal_inferred"]["promoted"]]
    assert ("eeg", "eog") in promoted


def test_dry_run_does_not_write_promotions(monkeypatch) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(promote_mod, "read_existing_promotion", lambda *a, **k: None)
    wrote = {"called": False}
    monkeypatch.setattr(runner_mod, "write_promotions", lambda rows: wrote.update(called=True))
    cfg = AblationConfig(min_labels=2)
    run_ablation("u1", ["arousal_inferred"], cfg, dry_run=True)
    assert wrote["called"] is False
