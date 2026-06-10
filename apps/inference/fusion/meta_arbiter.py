"""Meta-context switching authority — the single live (meta, sub) source of truth (#14).

The live meta-context was producer-stamped (waking_arc hardcoded WAKING); nothing
could ever flip Waking<->Sleep. This arbiter owns the authoritative pair: it
watches L3 BeliefState snapshots and flips with HYSTERESIS — SLEEP entry needs
N consecutive sleep-evidence observations (active sleep stage + no active waking
signal), SLEEP exit needs only strong waking evidence (active device use or live
conversation). Fail-safe default is WAKING. Producers/sinks read it through the
bound-method seam `arbiter.current_meta_context` instead of a hardcoded constant.
Pure and DB-free — safe for the L1-L6 import graph.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from core.bus.bus import TOPIC_BELIEF, MessageBus
from core.protocol.enums import MetaContext
from core.protocol.envelope import MessageEnvelope

from .belief_state import BeliefState

DEFAULT_SLEEP_ENTRY_OBSERVATIONS = 5
DEFAULT_WAKE_EXIT_OBSERVATIONS = 1

_IDLE_CATEGORIES = {"waking/idle", "offline"}

Snapshot = Mapping[str, Mapping[str, Any]]


def _axis_value(snapshot: Snapshot, axis: str) -> Mapping[str, Any] | None:
    entry = snapshot.get(axis)
    if entry is None:
        return None
    value = entry.get("value")
    return value if isinstance(value, Mapping) else None


def sleep_evidence(snapshot: Snapshot) -> bool:
    """SLEEP-entry evidence: an active sleep stage with no active waking signal."""
    stage = _axis_value(snapshot, "sleep_stage")
    if stage is None or not stage.get("active"):
        return False
    meta = _axis_value(snapshot, "meta_context")
    if meta is None:
        return True
    return str(meta.get("category", "")) in _IDLE_CATEGORIES


def strong_waking_evidence(snapshot: Snapshot) -> bool:
    """SLEEP-exit evidence: active device use or a live conversation."""
    meta = _axis_value(snapshot, "meta_context")
    if meta is not None:
        category = str(meta.get("category", ""))
        if category.startswith("waking/") and category not in _IDLE_CATEGORIES:
            return True
    social = _axis_value(snapshot, "audio_social_context")
    return social is not None and social.get("category") == "with_other"


class MetaContextArbiter:
    """Stateful (meta, sub) authority with asymmetric hysteresis; defaults WAKING."""

    def __init__(
        self,
        *,
        initial: MetaContext = MetaContext.WAKING,
        sleep_entry_observations: int = DEFAULT_SLEEP_ENTRY_OBSERVATIONS,
        wake_exit_observations: int = DEFAULT_WAKE_EXIT_OBSERVATIONS,
    ) -> None:
        if sleep_entry_observations < 1 or wake_exit_observations < 1:
            raise ValueError("hysteresis windows must be >= 1 observation")
        self.sleep_entry_observations = sleep_entry_observations
        self.wake_exit_observations = wake_exit_observations
        self._meta = initial
        self._sub: str | None = None
        self._sleep_streak = 0
        self._wake_streak = 0

    def current_meta(self) -> tuple[MetaContext, str | None]:
        """The authoritative (meta, sub) pair."""
        return (self._meta, self._sub)

    def current_meta_context(self) -> MetaContext:
        """The producer/sink read seam — pass this bound method, not a constant."""
        return self._meta

    def observe(self, snapshot: Snapshot) -> tuple[MetaContext, str | None]:
        """Fold one freshness-filtered BeliefState snapshot into the state machine."""
        if self._meta is MetaContext.SLEEP:
            if strong_waking_evidence(snapshot):
                self._wake_streak += 1
                if self._wake_streak >= self.wake_exit_observations:
                    self._flip_to(MetaContext.WAKING)
            else:
                self._wake_streak = 0
        else:
            if sleep_evidence(snapshot):
                self._sleep_streak += 1
                if self._sleep_streak >= self.sleep_entry_observations:
                    self._flip_to(MetaContext.SLEEP)
            else:
                self._sleep_streak = 0
        self._sub = self._sub_for(snapshot)
        return self.current_meta()

    def observe_belief(
        self, belief: BeliefState, *, now: datetime | None = None
    ) -> tuple[MetaContext, str | None]:
        """Observe a BeliefState through its freshness gate (stale axes drop out)."""
        return self.observe(belief.snapshot(now=now))

    def _flip_to(self, meta: MetaContext) -> None:
        self._meta = meta
        self._sub = None
        self._sleep_streak = 0
        self._wake_streak = 0

    def _sub_for(self, snapshot: Snapshot) -> str | None:
        if self._meta is MetaContext.SLEEP:
            stage = _axis_value(snapshot, "sleep_stage")
            if stage is not None and stage.get("label"):
                return str(stage["label"])
        else:
            meta = _axis_value(snapshot, "meta_context")
            if meta is not None and meta.get("category"):
                category = str(meta["category"])
                if category.startswith("waking/"):
                    return category.split("/", 1)[1]
                if category not in _IDLE_CATEGORIES:
                    return category
        return self._sub


def register(bus: MessageBus, *, arbiter: MetaContextArbiter | None = None) -> MetaContextArbiter:
    """Subscribe an arbiter to TOPIC_BELIEF so every L3 BeliefState updates it."""
    arb = arbiter or MetaContextArbiter()

    def _handler(env: MessageEnvelope) -> None:
        payload = getattr(env, "payload", None)
        if isinstance(payload, BeliefState):
            arb.observe_belief(payload)

    bus.subscribe(TOPIC_BELIEF, _handler)
    return arb
