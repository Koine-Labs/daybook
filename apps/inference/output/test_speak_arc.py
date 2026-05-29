"""Full waking-empath "Regis speaks" integration arc — signal → … → TTS sink.

Where core/test_pipeline.py proves the reflex arc reaches an OutputDirective and
that the production default renderer is the (LLM-backed) ComposerRenderer, THIS
test closes the loop to the speaker: it drives a single stimulus through the
*real* assembled production pipeline — default L6 ComposerRenderer included —
forces an interject decision (reusing the same interject seam as
core/test_pipeline.py so the arc reaches L6), registers the real TTS sink
(output.speaker.register_speaker) with a RECORDER speak-callable, and asserts the
generated voice OutputDirective is what the sink actually "spoke".

No network, no audio, no DB:
- wisp.composer.compose_utterance is monkeypatched to a deterministic stub (the
  ComposerRenderer imports it lazily, so the real LLM is never touched).
- the TTS sink's speak callable is an in-memory recorder (the real
  audio.streaming path is never imported).
- L3 axis data comes from an in-memory combiner fixture (no sensor_readings DB
  read), mirroring core/test_pipeline.py.

Run from apps/inference with the venv:
  python -m pytest output/test_speak_arc.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from core.bus.bus import (TOPIC_ACTION, TOPIC_OUTPUT, MessageBus)  # noqa: E402
from core.pipeline import assemble_pipeline  # noqa: E402
from core.protocol.enums import (Intent, MetaContext, Modality,  # noqa: E402
                                  PayloadType)
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import (ActionDecision, FeatureSnapshot,  # noqa: E402
                                     OutputDirective)
from fusion.belief_state import AxisEstimate  # noqa: E402
from fusion.participant import AxisCombiner  # noqa: E402
from decision.policy import DecisionContext, gate_trace_dict  # noqa: E402
from output.speaker import register_speaker  # noqa: E402
from sensors import participant as l1  # noqa: E402
from sensors.contract import IntentTaggedReading  # noqa: E402

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
COMPOSED_TEXT = "the wisp leans in, quietly delighted you noticed"
RATIONALE = "speak-arc fixture: gate cleared to exercise the L6 voice path"


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _sample_reading() -> IntentTaggedReading:
    """A representative waking L1 capture (gesture, continuous)."""
    return IntentTaggedReading(
        modality=Modality.GESTURE.value,
        intent=Intent.CONTINUOUS.value,
        kind="mac_activity",
        payload={"active_app": "Cursor", "idle_seconds": 3},
        source="mac.app_activity",
        timestamp=_utc(),
        user_id=USER,
        confidence=0.9,
    )


def _fresh_axis_registry() -> dict[str, AxisCombiner]:
    """One in-memory axis combiner yielding a fresh waking estimate (no DB)."""

    def meta(_packet: FeatureSnapshot, now: datetime) -> AxisEstimate:
        return AxisEstimate(
            axis="meta_context",
            value={"category": "waking/focused", "reason": "speak-arc-fixture"},
            timestamp=now,
            confidence=0.65,
            source="L3.fusion.meta_context.test_fixture",
            meta_context="waking/focused",
        )

    return {"meta_context": meta}


class _InterjectPolicy:
    """Real-shaped L5 policy whose single gate clears → 'interject' (reaches L6)."""

    name = "test_interject"

    def decide(self, ctx: DecisionContext) -> ActionDecision:
        trace = gate_trace_dict([], policy=self.name)
        trace["all_passed"] = True
        return ActionDecision(
            user_id=ctx.user_id,
            decided_at=ctx.now,
            action="interject",
            rationale=RATIONALE,
            mode="companion",
            content_kind="conversation_tease",
            gate_trace=trace,
            i_model_id=ctx.i_model_id,
        )


class _HoldPolicy:
    """Real-shaped L5 policy that HOLDs → L6 emits nothing, sink speaks nothing."""

    name = "test_hold"

    def decide(self, ctx: DecisionContext) -> ActionDecision:
        trace = gate_trace_dict([], policy=self.name)
        trace["all_passed"] = False
        return ActionDecision(
            user_id=ctx.user_id,
            decided_at=ctx.now,
            action="hold",
            rationale="speak-arc fixture: holding, stay silent",
            mode="companion",
            content_kind=None,
            gate_trace=trace,
            i_model_id=ctx.i_model_id,
        )


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


def test_regis_speaks_through_the_full_arc(monkeypatch):
    """signal → real ComposerRenderer (LLM mocked) → OutputDirective → TTS sink.

    Asserts exactly one voice directive reaches TOPIC_OUTPUT with the entry
    trace_id, its text is the mocked composed utterance, and the recorder sink
    captured that exact text (so Regis actually surfaced through the pipeline).
    """
    calls = _patch_composer(monkeypatch)

    bus = MessageBus()
    # No renderer= kwarg → exercises the PRODUCTION default (ComposerRenderer, #8).
    assemble_pipeline(
        bus,
        fusion_registry=_fresh_axis_registry(),
        decision_policy=_InterjectPolicy(),
    )

    outputs: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_OUTPUT, outputs.append)

    spoken: list[str] = []
    register_speaker(bus, speak=spoken.append)  # recorder; real audio path never imported

    env = l1.emit(bus, _sample_reading(), meta_context=MetaContext.WAKING)
    trace = env.trace_id

    # (1) exactly one voice OutputDirective with the SAME trace_id.
    assert len(outputs) == 1, f"expected 1 OutputDirective, got {len(outputs)}"
    out_env = outputs[0]
    assert out_env.type == PayloadType.OUTPUT
    assert out_env.trace_id == trace, "trace_id drifted between L1 entry and L6 output"
    directive = out_env.payload
    assert isinstance(directive, OutputDirective)
    assert directive.channel == "voice"  # waking → voice primary (#3)

    # (2) the directive text IS the (mocked) composed utterance — the real
    #     ComposerRenderer ran, not the StubRenderer.
    assert directive.text == COMPOSED_TEXT

    # (3) the sink spoke exactly that text (the loop closed to TTS).
    assert spoken == [COMPOSED_TEXT], f"sink did not speak the composed text: {spoken!r}"

    # The mocked composer was invoked once, mapped from the L5 decision.
    assert len(calls) == 1
    assert calls[0]["moment_kind"] == "conversation_tease"  # ← decision.content_kind
    assert calls[0]["explicit_context"] == RATIONALE          # ← decision.rationale


def test_hold_decision_emits_no_directive_and_speaks_nothing(monkeypatch):
    """A HOLD at L5 produces no OutputDirective and the TTS sink stays silent."""
    calls = _patch_composer(monkeypatch)  # patched anyway; must never be called on a hold

    bus = MessageBus()
    assemble_pipeline(
        bus,
        fusion_registry=_fresh_axis_registry(),
        decision_policy=_HoldPolicy(),
    )

    actions: list[MessageEnvelope] = []
    outputs: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_ACTION, actions.append)
    bus.subscribe(TOPIC_OUTPUT, outputs.append)

    spoken: list[str] = []
    register_speaker(bus, speak=spoken.append)

    l1.emit(bus, _sample_reading(), meta_context=MetaContext.WAKING)

    # The decision propagated and was a hold...
    assert actions, "trace never reached L5"
    decision = actions[-1].payload
    assert isinstance(decision, ActionDecision)
    assert decision.action == "hold"

    # ...so L6 emitted nothing and the sink never spoke (never compose either).
    assert outputs == [], "hold must not emit an OutputDirective"
    assert spoken == [], "hold must not speak"
    assert calls == [], "hold must not invoke the composer/LLM"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
