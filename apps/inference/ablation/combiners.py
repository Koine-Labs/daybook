"""Restrict a belief reconstruction to a source set (pure numpy, no DB/LLM).

v1 combiner: a per-source linear map fit by least squares over the restricted
inputs, clamped to [0,1]. This is the deterministic stand-in for L3's live
combiners (which the harness re-runs over restricted source sets, commitment #9);
the JEPA encoder replaces it behind the AblationBackend protocol later.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from .source_sets import SourceSet

_NEUTRAL = 0.5


def _design_matrix(
    source_set: SourceSet, inputs_list: Sequence[dict]
) -> np.ndarray:
    """Rows = samples, cols = [sources..., bias]; missing source → neutral 0.5."""
    rows = []
    for inputs in inputs_list:
        row = [float(inputs.get(s, _NEUTRAL)) for s in source_set]
        row.append(1.0)
        rows.append(row)
    return np.asarray(rows, dtype=float)


def fit_linear(
    source_set: SourceSet, inputs_list: Sequence[dict], targets: Sequence[float]
) -> list[float]:
    """Least-squares weights (len = |source_set| + 1 bias). Deterministic."""
    if not inputs_list:
        # degenerate: neutral passthrough (zero weights, neutral bias)
        return [0.0] * len(source_set) + [_NEUTRAL]
    x = _design_matrix(source_set, inputs_list)
    y = np.asarray(targets, dtype=float)
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    return [float(c) for c in coef]


def reconstruct_linear(
    source_set: SourceSet, inputs: dict, weights: Sequence[float]
) -> float:
    """Apply fitted weights to one sample, clamped to [0,1]."""
    w = np.asarray(weights, dtype=float)
    feats = [float(inputs.get(s, _NEUTRAL)) for s in source_set]
    feats.append(1.0)
    val = float(np.dot(w, np.asarray(feats, dtype=float)))
    return max(0.0, min(1.0, val))
