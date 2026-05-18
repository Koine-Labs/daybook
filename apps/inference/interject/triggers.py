"""Trigger registry — each trigger is a callable that may end in decide()."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .decider import InterjectDecision


@dataclass
class Trigger:
    name: str
    function: Callable[..., InterjectDecision]


TRIGGER_REGISTRY: dict[str, Trigger] = {}


def register(name: str):
    """Decorator that adds a trigger function to the global registry."""

    def decorator(fn: Callable[..., InterjectDecision]):
        TRIGGER_REGISTRY[name] = Trigger(name=name, function=fn)
        return fn

    return decorator
