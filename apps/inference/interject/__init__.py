"""Auto-interjection decider — Regis->user without explicit invocation.

The inverse of the gesture system. Triggers fire in response to events
(post-recall, mood shift, novel scene, etc.); the decider runs a composite
score against a high threshold and either speaks (via wisp.composer /
voice_chain) or holds silence. Either way, the decision is logged to
interject_decisions for later analysis + learning.

Public surface:
  - InterjectContext, InterjectDecision dataclasses
  - decide(ctx, persist=True) -> InterjectDecision
  - TRIGGER_REGISTRY, register(name) decorator
  - post_recall_trigger (concrete first trigger)
"""

from .decider import InterjectContext, InterjectDecision, decide
from .triggers import TRIGGER_REGISTRY, Trigger, register

__all__ = [
    "InterjectContext",
    "InterjectDecision",
    "decide",
    "TRIGGER_REGISTRY",
    "Trigger",
    "register",
]
