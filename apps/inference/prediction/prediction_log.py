# apps/inference/prediction/prediction_log.py
"""L4 prediction_log writer — every non-OFFLINE Prediction becomes a gradeable row.

Crash-safe like fusion/writer.py + labels/ledger.py: a missing/unreachable DB
logs a warning and returns None, never crashes the bus. The connection seam is
injectable (defaults to db.get_conn) so unit tests run DB-free with fakes.
OFFLINE sentinels are skipped at this single chokepoint — "no answer" is not a
forecast and would poison the grading set (#13 outcome labels, #16 flywheel).

Requires migration 0015 (prediction_log reshaped to the L4 forecast schema).
"""
from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Callable, ContextManager

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from core.protocol.payloads import Prediction  # noqa: E402
from fusion.belief_state import AxisEstimate  # noqa: E402

from .interface import OFFLINE_MODEL_ID  # noqa: E402

logger = logging.getLogger(__name__)

ConnFactory = Callable[[], ContextManager[Any]]

# v1 predictors ignore the action branch (#15 naive placeholder), so any
# action-conditioned row is honestly labeled as such until calibration lands.
ACTION_CONDITIONING_NONE = "none"
ACTION_CONDITIONING_NAIVE = "naive_placeholder"

_INSERT_SQL = """
INSERT INTO prediction_log
  (user_id, axis, meta_context, made_at, horizon_seconds, prediction,
   action_conditioned_on, model_id, inputs_used, cold_start,
   action_conditioning_kind, i_model_id)
VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s, %s, %s)
RETURNING id
"""


def _jsonsafe(value: Any) -> Any:
    """Replace non-finite floats with None — Postgres jsonb rejects NaN/Infinity."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _jsonsafe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonsafe(v) for v in value]
    return value


def estimate_inputs(est: AxisEstimate | None) -> dict[str, Any] | None:
    """Pack the L3 AxisEstimate a predictor consumed into the inputs_used shape."""
    if est is None:
        return None
    return {
        "kind": "axis_estimate",
        "axis": est.axis,
        "value": est.value,
        "timestamp": est.timestamp.isoformat(),
        "confidence": est.confidence,
        "source": est.source,
    }


def feature_inputs(features: dict[str, Any]) -> dict[str, Any]:
    """Pack an L2 feature dict (feature-based predictors) into the inputs_used shape."""
    return {"kind": "feature_snapshot", "features": features}


class PredictionLogWriter:
    """Persists L4 Predictions to prediction_log via an injectable conn seam."""

    def __init__(self, conn_factory: ConnFactory | None = None) -> None:
        self._conn_factory: ConnFactory = conn_factory if conn_factory is not None else get_conn

    def write(
        self,
        pred: Prediction,
        *,
        meta_context: str | None = None,
        inputs_used: dict[str, Any] | None = None,
    ) -> str | None:
        """INSERT one prediction; returns its id, or None (OFFLINE / DB absent)."""
        if pred.model_id == OFFLINE_MODEL_ID:
            return None
        prediction = _jsonsafe(
            {
                "distribution": pred.distribution,
                "confidence": pred.confidence,
                "provenance": pred.provenance,
            }
        )
        conditioning = (
            ACTION_CONDITIONING_NONE if pred.action is None else ACTION_CONDITIONING_NAIVE
        )
        try:
            with self._conn_factory() as conn, conn.cursor() as cur:
                cur.execute(
                    _INSERT_SQL,
                    (
                        pred.user_id,
                        pred.axis,
                        meta_context,
                        pred.made_at,
                        pred.horizon_seconds,
                        json.dumps(prediction),
                        None if pred.action is None else json.dumps(_jsonsafe(pred.action)),
                        pred.model_id,
                        None if inputs_used is None else json.dumps(_jsonsafe(inputs_used)),
                        pred.cold_start,
                        conditioning,
                        pred.i_model_id,
                    ),
                )
                new_id = str(cur.fetchone()[0])
                conn.commit()
            return new_id
        except Exception as exc:  # noqa: BLE001 — crash-safe: log and continue
            logger.warning("prediction_log write failed (DB absent or error): %s", exc)
            return None


__all__ = [
    "ACTION_CONDITIONING_NAIVE",
    "ACTION_CONDITIONING_NONE",
    "PredictionLogWriter",
    "estimate_inputs",
    "feature_inputs",
]
