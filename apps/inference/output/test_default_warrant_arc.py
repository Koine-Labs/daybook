"""DEFAULT assembled arc reaches interject+speak on a warranted stimulus.

Where output/test_speak_arc.py proves Regis can speak when an _InterjectPolicy
is INJECTED via the decision_policy= seam, THIS test removes that injection and
proves the *production* DefaultPolicy — the deterministic waking warrant — can
itself drive the assembled arc to interject and speak, on a real social-context
transition, and stays silent (HOLD) when not warranted.

No network, no audio, no DB:
- wisp.composer.compose_utterance is monkeypatched to a deterministic stub (the
  default ComposerRenderer imports it lazily, so the real LLM is never touched).
- the TTS sink's speak callable is an in-memory recorder.
- L3 axis data is an in-memory audio_social_context combiner fixture (no DB).

A transition needs TWO observations (Predictions are snapshots, not deltas —
the policy remembers the last social category per user), so each test drives
two stimuli on one bus, flipping a mutable category holder the combiner reads.
The arc's L5 is the real registry-held DefaultPolicy singleton, so its per-user
state persists across the two stimuli; each test resets that singleton's state
first for isolation.

Run from apps/inference with the venv:
  python -m pytest output/test_default_warrant_arc.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

import pytest  # noqa: E402

from core.bus.bus import (TOPIC_ACTION, TOPIC_OUTPUT, MessageBus)  # noqa: E402
from core.pipeline import assemble_pipeline  # noqa: E402
from core.protocol.enums import (Intent, MetaContext, Modality,  # noqa: E402
                                  PayloadType)
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import (ActionDecision, FeatureSnapshot,  # noqa: E402
                                     OutputDirective)
from fusion.belief_state import AxisEstimate  # noqa: E402
from fusion.participant import AxisCombiner  # noqa: E402
from output.speaker import register_speaker  # noqa: E402
from sensors import participant as l1  # noqa: E402
from sensors.contract import IntentTaggedReading  # noqa: E402

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
COMPOSED_TEXT = "the wisp leans in — someone's here now, then"


def _utc() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _reset_default_policy():
    """Reset the registry-held DefaultPolicy state so per-user memory doesn't leak
    between tests (the assembled arc uses the shared singleton via select_policy)."""
    from decision.registry import get_policy

    policy = get_policy("default")
    policy._last_category.clear()
    policy._last_interjection_at.clear()
    yield
    policy._last_category.clear()
    policy._last_interjection_at.clear()


def _audio_reading() -> IntentTaggedReading:
    """A waking continuous AUDIO capture (the live social signal's modality, #10)."""
    return IntentTaggedReading(
        modality=Modality.AUDIO.value,
        intent=Intent.CONTINUOUS.value,
        kind="audio_social_context",
        payload={"speaker": "user", "num_speakers": 1, "vad_active": True},
        source="mic_listener_v1",
        timestamp=_utc(),
        user_id=USER,
    )


def _social_registry(holder: dict[str, str]) -> dict[str, AxisCombiner]:
    """ONE in-memory combiner yielding a fresh audio_social_context estimate whose
    category is read live from a mutable holder (so a test can flip it between
    stimuli). Registers ONLY this axis so L4 emits exactly one Prediction/stimulus."""

    def social(_packet: FeatureSnapshot, now: datetime) -> AxisEstimate:
        return AxisEstimate(
            axis="audio_social_context",
            value={"category": holder["cat"]},
            timestamp=now,
            confidence=0.8,
            source="L3.fusion.audio_social_context.test_fixture",
            fresh_for_seconds=300,
        )

    return {"audio_social_context": social}


def _patch_composer(monkeypatch) -> list[dict[str, object]]:
    """Monkeypatch the lazily-imported composer to a deterministic stub (no LLM)."""
    import wisp.composer as composer  # module import is side-effect-free (no LLM call)

    calls: list[dict[str, object]] = []

    def _fake_compose(*, user_id, moment_kind, explicit_context="", **kwargs):
        calls.append(
            {"user_id": user_id, "moment_kind": moment_kind, "explicit_context": explicit_context}
        )
        return composer.ComposedUtterance(
            text=COMPOSED_TEXT,
            mode="companion",
            moment_kind=moment_kind,
            model="test-model",
            backend="test-backend",
        )

    monkeypatch.setattr(composer, "compose_utterance", _fake_compose)
    return calls


def _build_arc(monkeypatch, holder: dict[str, str]):
    """Assemble the DEFAULT arc (no decision_policy=), recorder speaker, collectors."""
    calls = _patch_composer(monkeypatch)

    bus = MessageBus()
    # No decision_policy= → the REAL DefaultPolicy runs. No renderer= → the
    # production ComposerRenderer (#8) runs (LLM mocked above).
    assemble_pipeline(bus, fusion_registry=_social_registry(holder))

    actions: list[MessageEnvelope] = []
    outputs: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_ACTION, actions.append)
    bus.subscribe(TOPIC_OUTPUT, outputs.append)

    spoken: list[str] = []
    register_speaker(bus, speak=spoken.append)  # recorder; real audio never imported

    return bus, calls, actions, outputs, spoken


def test_default_policy_social_transition_interjects_and_speaks(monkeypatch):
    """alone → with_other through the DEFAULT arc → exactly one voice directive spoken."""
    holder = {"cat": "alone"}
    bus, calls, actions, outputs, spoken = _build_arc(monkeypatch, holder)

    # Stimulus 1: 'alone' — first observation establishes a baseline → HOLD.
    l1.emit(bus, _audio_reading(), meta_context=MetaContext.WAKING)
    assert outputs == [], "first observation must not emit a directive"
    assert spoken == [], "first observation must not speak"
    assert actions and actions[-1].payload.action == "hold"

    # Stimulus 2: flip to 'with_other' — a transition → INTERJECT → speak.
    holder["cat"] = "with_other"
    env = l1.emit(bus, _audio_reading(), meta_context=MetaContext.WAKING)
    trace = env.trace_id

    # exactly ONE OutputDirective (only this stimulus warranted), voice/companion.
    assert len(outputs) == 1, f"expected 1 OutputDirective, got {len(outputs)}"
    out_env = outputs[0]
    assert out_env.type == PayloadType.OUTPUT
    assert out_env.trace_id == trace, "trace_id drifted L1→L6"
    directive = out_env.payload
    assert isinstance(directive, OutputDirective)
    assert directive.channel == "voice"      # waking → voice primary (#3)
    assert directive.mode == "companion"     # waking posture (#5)
    assert directive.text == COMPOSED_TEXT   # the (mocked) ComposerRenderer ran

    # the sink spoke exactly that text (the loop closed to TTS).
    assert spoken == [COMPOSED_TEXT], f"sink did not speak: {spoken!r}"

    # the L5 ActionDecision was a real default-policy interject with all gates clear.
    decision: ActionDecision = actions[-1].payload
    assert decision.action == "interject"
    assert decision.gate_trace["policy"] == "default"
    assert decision.gate_trace["all_passed"] is True
    assert all(g["passed"] for g in decision.gate_trace["gates"])

    # the composer was invoked exactly once, mapped from the L5 decision.
    assert len(calls) == 1
    assert calls[0]["moment_kind"] == "conversation_tease"

    # Arc-level cooldown: a THIRD warranted transition (with_other → alone) within
    # the 300s cooldown window must be rate-limited → no new directive, no new speech,
    # no new compose. Makes the rate-limit defense self-contained at the arc level.
    holder["cat"] = "alone"
    l1.emit(bus, _audio_reading(), meta_context=MetaContext.WAKING)
    assert len(outputs) == 1, "cooldown must suppress the second warranted directive"
    assert spoken == [COMPOSED_TEXT], "cooldown must suppress the second speech"
    assert len(calls) == 1, "cooldown must suppress the second compose"
    held = actions[-1].payload
    assert held.action == "hold"
    rl = next(g for g in held.gate_trace["gates"] if g["name"] == "rate-limit")
    assert rl["passed"] is False and "cooldown" in rl["detail"].lower()


def test_default_arc_no_transition_stays_silent(monkeypatch):
    """Two 'alone' stimuli through the DEFAULT arc → never speaks, never composes."""
    holder = {"cat": "alone"}
    bus, calls, actions, outputs, spoken = _build_arc(monkeypatch, holder)

    l1.emit(bus, _audio_reading(), meta_context=MetaContext.WAKING)
    l1.emit(bus, _audio_reading(), meta_context=MetaContext.WAKING)  # same category

    assert outputs == [], "no transition must not emit a directive"
    assert spoken == [], "no transition must not speak"
    assert calls == [], "no transition must not invoke the composer/LLM"
    assert actions, "trace never reached L5"
    assert all(a.payload.action == "hold" for a in actions)


def test_default_arc_wrong_meta_context_stays_silent(monkeypatch):
    """A real alone→with_other flip but under UNKNOWN meta_context → Gate A fails → silent."""
    holder = {"cat": "alone"}
    bus, calls, actions, outputs, spoken = _build_arc(monkeypatch, holder)

    l1.emit(bus, _audio_reading(), meta_context=MetaContext.UNKNOWN)
    holder["cat"] = "with_other"
    l1.emit(bus, _audio_reading(), meta_context=MetaContext.UNKNOWN)

    assert outputs == [], "non-waking context must not emit a directive"
    assert spoken == [], "non-waking context must not speak"
    assert calls == [], "non-waking context must not compose"
    assert actions and all(a.payload.action == "hold" for a in actions)
    # the meta-context gate is the one that blocked.
    last = actions[-1].payload
    meta_gate = next(g for g in last.gate_trace["gates"] if g["name"] == "meta-context")
    assert meta_gate["passed"] is False


def test_default_arc_non_waking_then_waking_first_window_stays_silent(monkeypatch):
    """Regression: a social observation under a non-WAKING meta_context must NOT
    leak a baseline that fabricates a transition on the first true WAKING window.

    Sequence: observe 'alone' under UNKNOWN (routes to the same default policy, but
    its meta-context gate blocks the action AND must block the baseline write), then
    flip to 'with_other' under WAKING. With the leak fixed the first waking window is
    a first observation → HOLD: no directive, no speech, no compose. A SECOND waking
    'alone' would then be the real transition (asserted below)."""
    holder = {"cat": "alone"}
    bus, calls, actions, outputs, spoken = _build_arc(monkeypatch, holder)

    # Non-waking observation establishes nothing (baseline must not leak).
    l1.emit(bus, _audio_reading(), meta_context=MetaContext.UNKNOWN)
    # First WAKING window, DIFFERENT category — must stay silent (no fabricated transition).
    holder["cat"] = "with_other"
    l1.emit(bus, _audio_reading(), meta_context=MetaContext.WAKING)

    assert outputs == [], "first waking window must not emit a directive off a leaked baseline"
    assert spoken == [], "first waking window must not speak off a leaked baseline"
    assert calls == [], "first waking window must not compose off a leaked baseline"
    assert actions and all(a.payload.action == "hold" for a in actions)
    # the first waking window held on the salient gate (first observation), not meta-context.
    last = actions[-1].payload
    assert last.gate_trace["policy"] == "default"
    assert next(g for g in last.gate_trace["gates"] if g["name"] == "meta-context")["passed"] is True
    salient = next(g for g in last.gate_trace["gates"] if g["name"] == "salient-fresh-signal")
    assert salient["passed"] is False and "first observation" in salient["detail"]

    # A SECOND waking observation that actually differs from the (now real) waking
    # baseline IS a genuine transition → it interjects and speaks.
    holder["cat"] = "alone"
    l1.emit(bus, _audio_reading(), meta_context=MetaContext.WAKING)
    assert spoken == [COMPOSED_TEXT], "the genuine waking transition should speak"
    assert actions[-1].payload.action == "interject"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
