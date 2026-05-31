"""End-to-end smoke on synthetic labels+beliefs, DB mocked — asserts a combo wins.

Run directly: `python -m ablation.smoke_test`. Also pytest-collectable (DB-free).
"""
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
from ablation.evaluate import evaluate_axis
from ablation.promote import decide_promotions
from ablation.report import render_markdown

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _synthetic_pairs(n: int = 40) -> list[GradedPair]:
    """Truth = 0.5*eeg + 0.5*eog; neither alone explains it, so the combo must win."""
    out: list[GradedPair] = []
    for i in range(n):
        eeg = (i % 5) / 4.0
        eog = ((i * 3) % 7) / 6.0
        truth = 0.5 * eeg + 0.5 * eog
        out.append(
            GradedPair(
                observed_at=_T0 + timedelta(minutes=i),
                truth_value=truth,
                truth_source=LabelSource.SELF_REPORT,
                truth_confidence=0.9,
                belief_inputs={"eeg": eeg, "eog": eog},
            )
        )
    return out


def _run(monkeypatchish=None) -> dict:
    pairs = _synthetic_pairs(40)
    train, evald = pairs[:28], pairs[28:]

    import ablation.evaluate as ev_mod
    import ablation.promote as promote_mod

    orig_build = ev_mod.build_dataset
    orig_avail = ev_mod.available_sources_for_axis
    orig_read = promote_mod.read_existing_promotion
    ev_mod.build_dataset = lambda u, a, c: (train, evald)
    ev_mod.available_sources_for_axis = lambda u, a: ["eeg", "eog"]
    # second-run hysteresis so the combo can actually promote in one shot
    promote_mod.read_existing_promotion = (
        lambda u, a, m, s: {"status": "candidate", "win_streak": 1}
        if tuple(s) == ("eeg", "eog") else None
    )
    try:
        cfg = AblationConfig(min_labels=2, promote_streak=2)
        rows = evaluate_axis("u1", "arousal_inferred", cfg, MacScaffoldBackend(), "smoke")
        decisions = decide_promotions(rows, cfg, "u1", "arousal_inferred", "smoke", metric="brier")
        promoted = [d.source_set for d in decisions if d.status == "promoted"]
        md = render_markdown({"arousal_inferred": rows}, {"arousal_inferred": promoted})
        return {"rows": rows, "decisions": decisions, "promoted": promoted, "markdown": md}
    finally:
        ev_mod.build_dataset = orig_build
        ev_mod.available_sources_for_axis = orig_avail
        promote_mod.read_existing_promotion = orig_read


def test_smoke_combo_wins() -> None:
    result = _run()
    combo = next(d for d in result["decisions"] if d.source_set == ("eeg", "eog"))
    assert combo.beat_components is True
    assert ("eeg", "eog") in result["promoted"]


def main() -> int:
    result = _run()
    print(result["markdown"])
    print("\nPromoted:", result["promoted"])
    assert ("eeg", "eog") in result["promoted"], "expected eeg+eog to win"
    print("\nSMOKE OK — combo beat its components and promoted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
