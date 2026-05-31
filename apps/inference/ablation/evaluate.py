"""The evaluation loop — per axis × candidate source_set → one ablation_results row.

Nothing is silently skipped (A4): capped sets, zero-pair sets, and under-sized
sets each get a row with the right `dropped_reason`. Graded sets get metrics keyed
by the axis type. Truth provenance is read only via the frozen ledger (A2).
`build_dataset` and `available_sources_for_axis` are module-level names so tests
monkeypatch them.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from .backend import AblationBackend
from .config import AblationConfig
from .dataset import GradedPair, build_dataset
from .grader import select_truth_grader
from .metrics import brier_binary, expected_calibration_error, nll_gaussian
from .source_sets import SourceSet, enumerate_candidates
from .store import AblationResultRow

logger = logging.getLogger(__name__)

# Per-axis declared inputs — the fallback source universe when history is thin.
_DECLARED_INPUTS: dict[str, list[str]] = {
    "arousal_inferred": ["ecg_watch", "eeg"],
    "affect_prosody": ["mic"],
    "meta_context": ["eeg", "ecg_watch", "mic", "vision"],
    "sleep_stage": ["eeg", "eog", "ecg_watch"],
}


def available_sources_for_axis(user_id: str, axis: str) -> list[str]:
    """Sources that ever wrote a belief for this axis ∪ the axis's declared inputs."""
    declared = list(_DECLARED_INPUTS.get(axis, []))
    seen: set[str] = set(declared)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT source FROM user_state_estimate "
                "WHERE user_id = %s AND axis = %s",
                (user_id, axis),
            )
            for (source,) in cur.fetchall():
                if source:
                    seen.add(source.strip().lower())
    except Exception as exc:  # noqa: BLE001 — crash-safe; declared inputs still usable
        logger.warning("available_sources_for_axis DB read failed: %s", exc)
    return sorted(seen)


def _score(
    axis: str, source_set: SourceSet, evald: list[GradedPair], backend, params
) -> dict[str, float]:
    """Reconstruct each eval pair and score against truth (continuous v1 metrics)."""
    preds: list[float] = []
    targets: list[float] = []
    for p in evald:
        out = backend.reconstruct_belief(axis, source_set, p, params)
        preds.append(float(out))
        tv = p.truth_value
        if isinstance(tv, dict):
            tv = tv.get("value", 0.0)
        targets.append(float(tv))
    sigmas = [0.25] * len(preds)
    return {
        "brier": brier_binary(preds, [round(t) for t in targets]),
        "nll": nll_gaussian(targets, preds, sigmas),
        "calibration_error": expected_calibration_error(
            preds, [round(t) for t in targets], n_bins=5
        ),
    }


def evaluate_axis(
    user_id: str,
    axis: str,
    cfg: AblationConfig,
    backend: AblationBackend,
    run_id: str,
) -> list[AblationResultRow]:
    """Evaluate every candidate source set for one axis; return result rows."""
    available = available_sources_for_axis(user_id, axis)
    candidates, dropped = enumerate_candidates(available, cfg)
    train, evald = build_dataset(user_id, axis, cfg)
    grader = select_truth_grader(train + evald)
    label_sources = sorted({p.truth_source.value for p in (train + evald)})

    rows: list[AblationResultRow] = []

    def _row(source_set: SourceSet, **kw) -> AblationResultRow:
        base = dict(
            run_id=run_id, user_id=user_id, axis=axis, meta_context=None,
            source_set=source_set, metrics={}, n_train_pairs=len(train),
            n_eval_pairs=len(evald), grader=grader, label_sources=label_sources,
            beat_components=None, dropped_reason=None,
        )
        base.update(kw)
        return AblationResultRow(**base)  # type: ignore[arg-type]

    # capped sets first (A4 — reported, not skipped)
    for cset, reason in dropped:
        rows.append(_row(cset, n_train_pairs=0, n_eval_pairs=0, dropped_reason=reason))

    for cset in candidates:
        if not evald:
            rows.append(_row(cset, n_train_pairs=0, n_eval_pairs=0,
                             dropped_reason="no_matched_pairs"))
            continue
        if len(evald) < cfg.min_labels:
            rows.append(_row(cset, dropped_reason="insufficient_data"))
            continue
        params = backend.fit(axis, cset, train)
        metrics = _score(axis, cset, evald, backend, params)
        rows.append(_row(cset, metrics=metrics))
    return rows
