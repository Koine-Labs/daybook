"""MetaContextArbiter — fail-safe default, hysteresis, both transitions, bus wiring."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from core.bus.bus import TOPIC_BELIEF, MessageBus  # noqa: E402
from core.protocol.enums import MetaContext, NodeRole, PayloadType  # noqa: E402
from core.protocol.envelope import MessageEnvelope  # noqa: E402

from fusion.belief_state import AxisEstimate, BeliefState  # noqa: E402
from fusion.meta_arbiter import (  # noqa: E402
    MetaContextArbiter,
    register,
    sleep_evidence,
    strong_waking_evidence,
)

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _entry(value: dict[str, Any]) -> dict[str, Any]:
    return {"value": value, "confidence": 0.9, "source": "test", "timestamp": "t"}


def _sleeping(label: str = "deep") -> dict[str, dict[str, Any]]:
    return {
        "sleep_stage": _entry({"label": label, "active": True}),
        "meta_context": _entry({"category": "waking/idle"}),
    }


def _waking(category: str = "waking/focused") -> dict[str, dict[str, Any]]:
    return {"meta_context": _entry({"category": category})}


def test_fail_safe_default_is_waking():
    arb = MetaContextArbiter()
    assert arb.current_meta() == (MetaContext.WAKING, None)
    assert arb.current_meta_context() is MetaContext.WAKING


def test_sleep_entry_requires_sustained_evidence():
    arb = MetaContextArbiter(sleep_entry_observations=3)
    assert arb.observe(_sleeping())[0] is MetaContext.WAKING
    assert arb.observe(_sleeping())[0] is MetaContext.WAKING
    meta, sub = arb.observe(_sleeping(label="rem"))
    assert meta is MetaContext.SLEEP
    assert sub == "rem"


def test_contrary_blip_resets_sleep_streak():
    arb = MetaContextArbiter(sleep_entry_observations=3)
    arb.observe(_sleeping())
    arb.observe(_sleeping())
    arb.observe(_waking())
    arb.observe(_sleeping())
    arb.observe(_sleeping())
    assert arb.current_meta_context() is MetaContext.WAKING
    arb.observe(_sleeping())
    assert arb.current_meta_context() is MetaContext.SLEEP


def test_sleep_exit_on_single_strong_waking_evidence():
    arb = MetaContextArbiter(initial=MetaContext.SLEEP)
    meta, sub = arb.observe(_waking("waking/communicating"))
    assert meta is MetaContext.WAKING
    assert sub == "communicating"


def test_conversation_is_strong_waking_evidence():
    arb = MetaContextArbiter(initial=MetaContext.SLEEP)
    snap = {"audio_social_context": _entry({"category": "with_other"})}
    assert arb.observe(snap)[0] is MetaContext.WAKING


def test_idle_alone_does_not_exit_sleep():
    arb = MetaContextArbiter(initial=MetaContext.SLEEP)
    arb.observe({"meta_context": _entry({"category": "waking/idle"})})
    assert arb.current_meta_context() is MetaContext.SLEEP


def test_empty_snapshot_keeps_current_state():
    awake = MetaContextArbiter()
    assert awake.observe({})[0] is MetaContext.WAKING
    asleep = MetaContextArbiter(initial=MetaContext.SLEEP)
    assert asleep.observe({})[0] is MetaContext.SLEEP


def test_active_app_blocks_sleep_entry():
    arb = MetaContextArbiter(sleep_entry_observations=1)
    snap = {
        "sleep_stage": _entry({"label": "core", "active": True}),
        "meta_context": _entry({"category": "waking/focused"}),
    }
    assert arb.observe(snap)[0] is MetaContext.WAKING


def test_inactive_stage_is_not_sleep_evidence():
    arb = MetaContextArbiter(sleep_entry_observations=1)
    snap = {"sleep_stage": _entry({"label": "in_bed", "active": False})}
    assert arb.observe(snap)[0] is MetaContext.WAKING


def test_waking_sub_context_tracks_meta_axis():
    arb = MetaContextArbiter()
    _, sub = arb.observe(_waking("waking/focused"))
    assert sub == "focused"
    _, sub = arb.observe(_waking("waking/browsing"))
    assert sub == "browsing"


def test_sub_context_resets_across_transition():
    arb = MetaContextArbiter(sleep_entry_observations=1)
    arb.observe(_waking("waking/focused"))
    meta, sub = arb.observe(_sleeping(label="core"))
    assert meta is MetaContext.SLEEP
    assert sub == "core"


def test_evidence_helpers():
    assert sleep_evidence(_sleeping())
    assert not sleep_evidence(_waking())
    assert strong_waking_evidence(_waking())
    assert not strong_waking_evidence(_sleeping())


def _sleep_belief(now: datetime, *, age_seconds: int = 0) -> BeliefState:
    belief = BeliefState(user_id=USER)
    belief.update(
        AxisEstimate(
            axis="sleep_stage",
            value={"label": "deep", "active": True},
            timestamp=now - timedelta(seconds=age_seconds),
            confidence=0.95,
            source="apple_health_sleep_stage",
            fresh_for_seconds=600,
        )
    )
    return belief


def test_observe_belief_counts_fresh_sleep_evidence():
    now = datetime.now(timezone.utc)
    arb = MetaContextArbiter(sleep_entry_observations=1)
    meta, sub = arb.observe_belief(_sleep_belief(now), now=now)
    assert meta is MetaContext.SLEEP
    assert sub == "deep"


def test_observe_belief_ignores_stale_estimates():
    now = datetime.now(timezone.utc)
    arb = MetaContextArbiter(sleep_entry_observations=1)
    meta, _ = arb.observe_belief(_sleep_belief(now, age_seconds=3600), now=now)
    assert meta is MetaContext.WAKING


def _belief_env(payload: Any, now: datetime) -> MessageEnvelope:
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.BELIEF,
        source_role=NodeRole.DESKTOP_COMPUTE,
        occurred_at=now,
        meta_context=MetaContext.UNKNOWN,
        consent_scope="continuous_sensing",
        trace_id=str(uuid.uuid4()),
        payload=payload,
        i_model_id=None,
    )


def test_register_feeds_arbiter_from_belief_topic():
    now = datetime.now(timezone.utc)
    bus = MessageBus()
    arb = register(bus, arbiter=MetaContextArbiter(sleep_entry_observations=2))
    bus.publish(TOPIC_BELIEF, _belief_env(_sleep_belief(now), now))
    assert arb.current_meta_context() is MetaContext.WAKING
    bus.publish(TOPIC_BELIEF, _belief_env(_sleep_belief(now), now))
    assert arb.current_meta_context() is MetaContext.SLEEP


def test_register_ignores_non_belief_payloads():
    now = datetime.now(timezone.utc)
    bus = MessageBus()
    arb = register(bus, arbiter=MetaContextArbiter(sleep_entry_observations=1))
    bus.publish(TOPIC_BELIEF, _belief_env("not-a-belief-state", now))
    assert arb.current_meta() == (MetaContext.WAKING, None)
