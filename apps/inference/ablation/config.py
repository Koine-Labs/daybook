"""AblationConfig — harness knobs with env overrides (config-only desktop swap, A6)."""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from typing import Any

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


@dataclass(frozen=True)
class AblationConfig:
    """Knobs for one ablation run; frozen so a run's config is an immutable record."""

    max_set_size: int = 3          # cap on |source_set|; REPORTED, never silent (A4)
    delta: float = 0.0             # margin a set must beat its best component by (A3)
    min_labels: int = 8            # min graded eval pairs or dropped_reason='insufficient_data'
    tol_window_s: int = 300        # ±window for the label↔belief as-of join
    promote_streak: int = 2        # consecutive wins before promotion (A5 hysteresis)
    split: str = "time_holdout"    # 'time_holdout' (older→train, newer→eval); no overlap
    backend: str = "mac_scaffold"  # 'mac_scaffold' | 'desktop_gpu'
    greedy: bool = False           # forward-selection instead of full power-set when K large


_INT_ENV = {
    "max_set_size": "ABLATION_MAX_SET_SIZE",
    "min_labels": "ABLATION_MIN_LABELS",
    "tol_window_s": "ABLATION_TOL_WINDOW_S",
    "promote_streak": "ABLATION_PROMOTE_STREAK",
}
_FLOAT_ENV = {"delta": "ABLATION_DELTA"}
_STR_ENV = {"split": "ABLATION_SPLIT", "backend": "ABLATION_BACKEND"}
_BOOL_ENV = {"greedy": "ABLATION_GREEDY"}


def _truthy(s: str) -> bool:
    return s.strip().lower() in ("1", "true", "yes", "on")


def config_from_env(**overrides: Any) -> AblationConfig:
    """Build a config from defaults, layering env vars, then explicit kwargs on top."""
    values: dict[str, Any] = {f.name: f.default for f in fields(AblationConfig)}
    for name, env in _INT_ENV.items():
        raw = os.environ.get(env)
        if raw is not None:
            values[name] = int(raw)
    for name, env in _FLOAT_ENV.items():
        raw = os.environ.get(env)
        if raw is not None:
            values[name] = float(raw)
    for name, env in _STR_ENV.items():
        raw = os.environ.get(env)
        if raw is not None:
            values[name] = raw
    for name, env in _BOOL_ENV.items():
        raw = os.environ.get(env)
        if raw is not None:
            values[name] = _truthy(raw)
    values.update(overrides)
    return AblationConfig(**values)
