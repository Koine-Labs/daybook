"""Promotion logic — beats-best-component (A3) + delta margin + hysteresis (A5).

A combo is only promoted if its metric beats the best metric among its GRADED
strict subsets by `delta` (A3), AND it wins on `promote_streak` consecutive runs
(A5). A previously promoted set that regresses below its components is demoted.
`read_existing_promotion` is a module-level name so tests monkeypatch the DB read.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from .config import AblationConfig
from .metrics import is_better
from .source_sets import SourceSet
from .store import (  # noqa: F401  (re-export so tests monkeypatch promote.read_existing_promotion)
    PromotionRow,
    read_existing_promotion,
)

logger = logging.getLogger(__name__)


@dataclass
class PromotionDecision:
    source_set: SourceSet
    status: str               # 'promoted' | 'candidate' | 'demoted'
    metric_name: str
    metric_value: float | None
    component_best: float | None
    margin: float | None
    beat_components: bool
    n_eval_pairs: int
    win_streak: int


def _strict_subsets(source_set: SourceSet) -> list[SourceSet]:
    out: list[SourceSet] = []
    for size in range(1, len(source_set)):
        out.extend(combinations(source_set, size))
    return out


def decide_promotions(
    results: list,
    cfg: AblationConfig,
    user_id: str | None,
    axis: str,
    run_id: str,
    *,
    metric: str = "brier",
) -> list[PromotionDecision]:
    """Decide promote/hold/demote per fully-graded set; subsets supply the margin."""
    graded = [r for r in results if r.dropped_reason is None and metric in r.metrics]
    score_by_set: dict[SourceSet, float] = {
        tuple(r.source_set): float(r.metrics[metric]) for r in graded
    }

    decisions: list[PromotionDecision] = []
    for r in graded:
        cset = tuple(r.source_set)
        score = score_by_set[cset]
        subset_scores = [
            score_by_set[s] for s in _strict_subsets(cset) if s in score_by_set
        ]
        if subset_scores:
            component_best = _best(metric, subset_scores)
            beat = is_better(metric, score, component_best, delta=cfg.delta)
            margin = _margin(metric, score, component_best)
        else:
            # No graded strict subset → cannot establish "beats its components".
            component_best = None
            beat = False
            margin = None

        existing = read_existing_promotion(user_id, axis, None, cset)
        prev_streak = existing["win_streak"] if existing else 0
        prev_status = existing["status"] if existing else "candidate"

        if beat:
            win_streak = prev_streak + 1
            status = "promoted" if win_streak >= cfg.promote_streak else "candidate"
        else:
            win_streak = 0
            status = "demoted" if prev_status == "promoted" else "candidate"

        decisions.append(
            PromotionDecision(
                source_set=cset, status=status, metric_name=metric,
                metric_value=score, component_best=component_best, margin=margin,
                beat_components=beat, n_eval_pairs=r.n_eval_pairs, win_streak=win_streak,
            )
        )
    return decisions


def _best(metric: str, scores: list[float]) -> float:
    from .metrics import LOWER_IS_BETTER

    return min(scores) if metric in LOWER_IS_BETTER else max(scores)


def _margin(metric: str, score: float, component_best: float) -> float:
    """Signed improvement, normalized so positive always means 'better'."""
    from .metrics import LOWER_IS_BETTER

    if metric in LOWER_IS_BETTER:
        return component_best - score
    return score - component_best


def decisions_to_rows(
    decisions: list[PromotionDecision],
    user_id: str | None,
    axis: str,
    run_id: str,
) -> list[PromotionRow]:
    """Convert decisions to PromotionRows for store.write_promotions."""
    return [
        PromotionRow(
            user_id=user_id, axis=axis, meta_context=None, source_set=d.source_set,
            weights={}, status=d.status, metric_name=d.metric_name,
            metric_value=d.metric_value, component_best=d.component_best, margin=d.margin,
            n_eval_pairs=d.n_eval_pairs, win_streak=d.win_streak, promoted_run_id=run_id,
        )
        for d in decisions
    ]
