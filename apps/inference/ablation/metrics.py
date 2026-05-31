"""Scoring metrics — pure numpy, deterministic, DB-free + LLM-free.

Categorical axes: multiclass Brier + log-loss + ECE.
Continuous axes:  Gaussian NLL + CRPS.
Binary-event axes: AUROC + binary Brier.
`LOWER_IS_BETTER` + `is_better` normalize margin sign so promotion (A3) is
direction-agnostic across metric families.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

LOWER_IS_BETTER: set[str] = {
    "brier",
    "nll",
    "crps",
    "log_loss",
    "calibration_error",
    "ece",
}

_EPS = 1e-12


def brier_binary(preds: Sequence[float], labels: Sequence[int]) -> float:
    """Mean squared error between predicted P(y=1) and {0,1} labels."""
    p = np.asarray(preds, dtype=float)
    y = np.asarray(labels, dtype=float)
    return float(np.mean((p - y) ** 2))


def multiclass_brier(probs: Sequence[Sequence[float]], labels: Sequence[int]) -> float:
    """Sum-over-classes squared error against one-hot truth, averaged over rows."""
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=int)
    onehot = np.zeros_like(p)
    onehot[np.arange(len(y)), y] = 1.0
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


def multiclass_log_loss(probs: Sequence[Sequence[float]], labels: Sequence[int]) -> float:
    """Mean negative log-prob of the true class (clipped to avoid inf)."""
    p = np.clip(np.asarray(probs, dtype=float), _EPS, 1.0)
    y = np.asarray(labels, dtype=int)
    true_p = p[np.arange(len(y)), y]
    return float(np.mean(-np.log(true_p)))


def nll_gaussian(
    targets: Sequence[float], means: Sequence[float], sigmas: Sequence[float]
) -> float:
    """Mean Gaussian negative log-likelihood of targets under N(mean, sigma^2)."""
    t = np.asarray(targets, dtype=float)
    m = np.asarray(means, dtype=float)
    s = np.clip(np.asarray(sigmas, dtype=float), _EPS, None)
    nll = 0.5 * np.log(2 * math.pi * s**2) + (t - m) ** 2 / (2 * s**2)
    return float(np.mean(nll))


def crps_gaussian(
    targets: Sequence[float], means: Sequence[float], sigmas: Sequence[float]
) -> float:
    """Closed-form CRPS for a Gaussian forecast (Gneiting & Raftery 2007)."""
    t = np.asarray(targets, dtype=float)
    m = np.asarray(means, dtype=float)
    s = np.clip(np.asarray(sigmas, dtype=float), _EPS, None)
    z = (t - m) / s
    pdf = np.exp(-0.5 * z**2) / math.sqrt(2 * math.pi)
    cdf = 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2)))
    crps = s * (z * (2 * cdf - 1) + 2 * pdf - 1.0 / math.sqrt(math.pi))
    return float(np.mean(crps))


def auroc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """Area under ROC via the rank-sum (Mann–Whitney) identity. NaN if one class."""
    s = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=int)
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=float)
    ranks[order] = np.arange(1, len(s) + 1, dtype=float)
    # average ties
    _assign_tie_ranks(s, ranks)
    rank_sum_pos = float(np.sum(ranks[y == 1]))
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _assign_tie_ranks(values: np.ndarray, ranks: np.ndarray) -> None:
    order = np.argsort(values, kind="mergesort")
    sorted_vals = values[order]
    i = 0
    n = len(values)
    while i < n:
        j = i
        while j + 1 < n and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        if j > i:
            avg = np.mean(ranks[order[i : j + 1]])
            ranks[order[i : j + 1]] = avg
        i = j + 1


def expected_calibration_error(
    preds: Sequence[float], labels: Sequence[int], n_bins: int = 10
) -> float:
    """Binned |confidence - accuracy| weighted by bin mass (binary preds in [0,1])."""
    p = np.asarray(preds, dtype=float)
    y = np.asarray(labels, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(p)
    for b in range(n_bins):
        lo, hi = edges[b], edges[b + 1]
        if b == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        m = int(np.sum(mask))
        if m == 0:
            continue
        conf = float(np.mean(p[mask]))
        acc = float(np.mean(y[mask]))
        ece += (m / n) * abs(conf - acc)
    return float(ece)


def is_better(metric: str, candidate: float, baseline: float, delta: float = 0.0) -> bool:
    """True if `candidate` beats `baseline` by at least `delta`, sign-normalized."""
    if math.isnan(candidate) or math.isnan(baseline):
        return False
    if metric in LOWER_IS_BETTER:
        return candidate <= baseline - delta
    return candidate >= baseline + delta
