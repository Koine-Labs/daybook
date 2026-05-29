# apps/inference/prediction/registry.py
"""(axis, meta_context) -> predictor selection for L4.

Selection is two-keyed because commitment #14 says every layer's behavior is
conditioned on the active meta_context: the same axis may want a sleep-tuned
predictor vs a waking-tuned one. A wildcard meta_context ("*") lets a predictor
cover an axis in all contexts. Unregistered (axis, meta_context) pairs select
None, which the interface turns into PREDICTION_OFFLINE.
"""
from __future__ import annotations

from .interface import Predictor
from .predictors.stub import StubPredictor

WILDCARD = "*"

# Axes we currently attempt to predict at all (others -> OFFLINE).
# v1: only the axes L3 actually produces today get a (stub) predictor.
_DEFAULT_STUB = StubPredictor()

_REGISTRY: dict[tuple[str, str], Predictor] = {
    ("meta_context", WILDCARD): _DEFAULT_STUB,
    ("sleep_stage", "sleep"): _DEFAULT_STUB,
    ("audio_social_context", WILDCARD): _DEFAULT_STUB,
}


def register(axis: str, meta_context: str, predictor: Predictor) -> None:
    """Register a predictor for an (axis, meta_context); meta_context may be WILDCARD."""
    _REGISTRY[(axis, meta_context)] = predictor


def select(axis: str, meta_context: str) -> Predictor | None:
    """Return the predictor for (axis, meta_context), preferring exact over wildcard."""
    exact = _REGISTRY.get((axis, meta_context))
    if exact is not None:
        return exact
    return _REGISTRY.get((axis, WILDCARD))


def registered_axes() -> set[str]:
    """Set of axes that have at least one registered predictor (any context)."""
    return {axis for (axis, _ctx) in _REGISTRY}
