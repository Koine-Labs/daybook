"""The D1 join: ledger truth labels ↔ user_state_estimate beliefs (offline only).

Truth is read EXCLUSIVELY through the frozen `labels.read_labels` and scoped to
the four grading tiers (A2) — priors are never requested. Beliefs are joined as
the latest per-source row at-or-before each label within ±tol_window_s. The
time-holdout split keeps older→train, newer→eval with NO timestamp overlap
(leakage guard). Crash-safe: a missing/unreachable DB yields ([], []).

`read_labels` and `get_conn` are module-level names so tests monkeypatch them; the
imports themselves stay inside no function because they touch no DB at import.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402
from labels import LabelSource, read_labels  # noqa: E402
from labels.record import LabelRecord  # noqa: E402

from .config import AblationConfig

logger = logging.getLogger(__name__)

_TRUTH_TIERS = [
    LabelSource.GROUND_TRUTH,
    LabelSource.CLINICIAN,
    LabelSource.SELF_REPORT,
    LabelSource.OBSERVED_OUTCOME,
]

_EVAL_FRACTION = 0.3  # newest 30% of labels → eval, rest → train


@dataclass
class GradedPair:
    """One label joined to the per-source beliefs that were live near its moment."""

    observed_at: datetime
    truth_value: Any
    truth_source: LabelSource
    truth_confidence: float
    belief_inputs: dict[str, Any]


def _load_belief_rows(user_id: str, axis: str) -> list[tuple[str, Any, datetime]]:
    """Return [(source, value, timestamp)] for the axis, oldest→newest. [] if DB absent."""
    sql = (
        "SELECT axis, value, confidence, source, timestamp, meta_context, i_model_id "
        "FROM user_state_estimate WHERE user_id = %s AND axis = %s "
        "ORDER BY timestamp ASC"
    )
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (user_id, axis))
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — crash-safe: log and return []
        logger.warning("belief load failed (DB absent or error): %s", exc)
        return []
    out: list[tuple[str, Any, datetime]] = []
    for _axis, value, _conf, source, ts, _meta, _imodel in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        scalar = value.get("value") if isinstance(value, dict) else value
        out.append((source or "unknown", scalar, ts))
    return out


def _match_beliefs(
    label_at: datetime, beliefs: list[tuple[str, Any, datetime]], tol: timedelta
) -> dict[str, Any]:
    """Latest belief per source at-or-before label_at within tol. {} if none match."""
    inputs: dict[str, tuple[datetime, Any]] = {}
    for source, value, ts in beliefs:
        if ts > label_at:
            continue
        if label_at - ts > tol:
            continue
        prev = inputs.get(source)
        if prev is None or ts > prev[0]:
            inputs[source] = (ts, value)
    return {src: val for src, (_ts, val) in inputs.items()}


def build_dataset(
    user_id: str, axis: str, cfg: AblationConfig
) -> tuple[list[GradedPair], list[GradedPair]]:
    """Join ledger truth ↔ beliefs, split time-holdout (older→train, newer→eval)."""
    labels: list[LabelRecord] = read_labels(user_id, axis=axis, sources=list(_TRUTH_TIERS))
    if not labels:
        return [], []
    beliefs = _load_belief_rows(user_id, axis)
    tol = timedelta(seconds=cfg.tol_window_s)

    pairs: list[GradedPair] = []
    for lab in labels:
        inputs = _match_beliefs(lab.observed_at, beliefs, tol)
        pairs.append(
            GradedPair(
                observed_at=lab.observed_at,
                truth_value=lab.value,
                truth_source=lab.source,
                truth_confidence=lab.confidence,
                belief_inputs=inputs,
            )
        )
    pairs.sort(key=lambda p: p.observed_at)

    if len(pairs) < 2:
        return pairs, []
    n_eval = max(1, int(round(len(pairs) * _EVAL_FRACTION)))
    split = len(pairs) - n_eval
    return pairs[:split], pairs[split:]
