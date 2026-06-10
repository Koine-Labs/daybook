"""Crash-safe persistence for the three ablation tables (mirrors fusion/writer.py).

Writes swallow DB errors with a logged warning and return None/0; reads return [].
A missing/unreachable DB never crashes the harness or the live read seam. The only
hot-path read is `list_promoted` (one SELECT) — L3 fusers call it and degrade to []
when the DB is absent (ARCHITECTURE §8 "hot paths never crash on optional reads").
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from .source_sets import SourceSet, canonical

logger = logging.getLogger(__name__)


@dataclass
class AblationResultRow:
    run_id: str
    user_id: str | None
    axis: str
    meta_context: str | None
    source_set: SourceSet
    metrics: dict[str, Any]
    n_train_pairs: int
    n_eval_pairs: int
    grader: str
    label_sources: list[str]
    beat_components: bool | None
    dropped_reason: str | None


@dataclass
class PromotionRow:
    user_id: str | None
    axis: str
    meta_context: str | None
    source_set: SourceSet
    weights: dict[str, Any]
    status: str
    metric_name: str
    metric_value: float | None
    component_best: float | None
    margin: float | None
    n_eval_pairs: int
    win_streak: int
    promoted_run_id: str | None
    i_model_id: str | None = None


def open_run(
    user_id: str | None,
    *,
    backend: str,
    axes: list[str],
    config: dict[str, Any],
    git_sha: str | None,
) -> str | None:
    """INSERT a 'running' ablation_runs row; return its id, or None when DB absent."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ablation_runs
                  (user_id, backend, axes_evaluated, config, git_sha, status)
                VALUES (%s, %s, %s, %s::jsonb, %s, 'running')
                RETURNING id
                """,
                (user_id, backend, axes, json.dumps(config), git_sha),
            )
            new_id = str(cur.fetchone()[0])
            conn.commit()
        return new_id
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("open_run failed (DB absent or error): %s", exc)
        return None


def close_run(run_id: str, *, status: str, manifest: dict[str, Any]) -> bool:
    """Finalize a run row (finished_at, status, manifest). False when DB absent."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ablation_runs
                   SET status = %s, manifest = %s::jsonb, finished_at = %s
                 WHERE id = %s
                """,
                (status, json.dumps(manifest), datetime.now(timezone.utc), run_id),
            )
            conn.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("close_run failed (DB absent or error): %s", exc)
        return False


def write_results(rows: list[AblationResultRow]) -> int:
    """Atomically write ablation_results rows; return count (0 when DB absent/empty)."""
    if not rows:
        return 0
    try:
        with get_conn() as conn, conn.cursor() as cur:
            try:
                for r in rows:
                    cur.execute(
                        """
                        INSERT INTO ablation_results
                          (run_id, user_id, axis, meta_context, source_set, metrics,
                           n_train_pairs, n_eval_pairs, grader, label_sources,
                           beat_components, dropped_reason)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            r.run_id, r.user_id, r.axis, r.meta_context,
                            list(canonical(list(r.source_set))), json.dumps(r.metrics),
                            r.n_train_pairs, r.n_eval_pairs, r.grader,
                            list(r.label_sources), r.beat_components, r.dropped_reason,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return len(rows)
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("write_results failed (DB absent or error): %s", exc)
        return 0


def write_promotions(rows: list[PromotionRow]) -> int:
    """Upsert promoted_source_sets rows; return count (0 when DB absent/empty)."""
    if not rows:
        return 0
    try:
        with get_conn() as conn, conn.cursor() as cur:
            try:
                for r in rows:
                    cur.execute(
                        """
                        INSERT INTO promoted_source_sets
                          (user_id, axis, meta_context, source_set, weights, status,
                           metric_name, metric_value, component_best, margin,
                           n_eval_pairs, win_streak, promoted_run_id, i_model_id, updated_at)
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, axis, meta_context, source_set)
                        DO UPDATE SET
                           weights = EXCLUDED.weights,
                           status = EXCLUDED.status,
                           metric_name = EXCLUDED.metric_name,
                           metric_value = EXCLUDED.metric_value,
                           component_best = EXCLUDED.component_best,
                           margin = EXCLUDED.margin,
                           n_eval_pairs = EXCLUDED.n_eval_pairs,
                           win_streak = EXCLUDED.win_streak,
                           promoted_run_id = EXCLUDED.promoted_run_id,
                           updated_at = EXCLUDED.updated_at
                        """,
                        (
                            r.user_id, r.axis, r.meta_context,
                            list(canonical(list(r.source_set))), json.dumps(r.weights),
                            r.status, r.metric_name, r.metric_value, r.component_best,
                            r.margin, r.n_eval_pairs, r.win_streak, r.promoted_run_id,
                            r.i_model_id, datetime.now(timezone.utc),
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return len(rows)
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("write_promotions failed (DB absent or error): %s", exc)
        return 0


def read_existing_promotion(
    user_id: str | None, axis: str, meta_context: str | None, source_set: SourceSet
) -> dict[str, Any] | None:
    """Read one promoted_source_sets row (status + win_streak), or None if absent."""
    canon = list(canonical(list(source_set)))
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, win_streak FROM promoted_source_sets
                 WHERE user_id IS NOT DISTINCT FROM %s AND axis = %s
                   AND meta_context IS NOT DISTINCT FROM %s AND source_set = %s
                """,
                (user_id, axis, meta_context, canon),
            )
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("read_existing_promotion failed (DB absent or error): %s", exc)
        return None
    if row is None:
        return None
    return {"status": row[0], "win_streak": row[1]}


def list_promoted(
    user_id: str | None, axis: str, meta_context: str | None
) -> list[SourceSet]:
    """The live-fuser read seam: promoted source sets for (user, axis, meta_context).

    Crash-safe — returns [] when the DB is absent so the hot path never breaks.
    """
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_set FROM promoted_source_sets
                 WHERE user_id IS NOT DISTINCT FROM %s AND axis = %s
                   AND meta_context IS NOT DISTINCT FROM %s AND status = 'promoted'
                 ORDER BY metric_value ASC NULLS LAST
                """,
                (user_id, axis, meta_context),
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("list_promoted failed (DB absent or error): %s", exc)
        return []
    return [tuple(r[0]) for r in rows]
