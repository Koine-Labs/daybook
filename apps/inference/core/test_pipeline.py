"""End-to-end reflex arc through the REAL assembled pipeline (not inline stubs).

Builds one MessageBus, runs core.pipeline.assemble_pipeline, then uses the L1
producer (sensors.participant.emit) to inject a single IntentTaggedReading. The
stimulus traverses the actual L2->L6 participant code; we assert the same
trace_id is observable at every boundary and that the arc terminates either at
an OutputDirective on TOPIC_OUTPUT (interject path) or as a documented
silent-hold (the real default policies HOLD -> L6 emits nothing).

Determinism without DB/network: the real L3 axes read sensor_readings (DB), so
the test injects an in-memory axis combiner producing one fresh AxisEstimate.
This still runs the real FusionParticipant, real L4 StubPredictor, real L5
DecisionContext/forward machinery, and real L6 channel-selection + StubRenderer.
Only the leaf axis-data source is in-memory — the same technique each layer's
own smoke test uses. No network/LLM is touched: the production assembly now
defaults L6 to the generative ComposerRenderer (#8), so these tests INJECT
StubRenderer to keep the arc deterministic and offline. The one renderer-default
test monkeypatches wisp.composer.compose_utterance instead of calling it.

Run from apps/inference with the venv:
  python -m pytest core/test_pipeline.py -v && python -m core.pipeline
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from arbitration.blend import BlendResult, CalibrationState  # noqa: E402
from core.bus.bus import (TOPIC_ACTION, TOPIC_BELIEF, TOPIC_FEATURE,  # noqa: E402
                          TOPIC_OUTPUT, TOPIC_PREDICTION, TOPIC_SIGNAL, MessageBus)
from core.pipeline import assemble_pipeline  # noqa: E402
from core.protocol.enums import (Intent, MetaContext, Modality, NodeRole,  # noqa: E402
                                  PayloadType)
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import (ActionDecision, FeatureSnapshot,  # noqa: E402
                                     OutputDirective, Prediction, SignalPacket)
from fusion.belief_state import AxisEstimate  # noqa: E402
from fusion.participant import AxisCombiner  # noqa: E402
import fusion.participant as l3  # noqa: E402
from output.renderer import StubRenderer  # noqa: E402
from sensors import participant as l1  # noqa: E402
from sensors.contract import IntentTaggedReading  # noqa: E402
from decision.policy import DecisionContext, gate_trace_dict  # noqa: E402

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _sample_reading() -> IntentTaggedReading:
    """A representative L1 capture: background mac activity (gesture, continuous)."""
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
    """One in-memory axis combiner yielding a fresh estimate (no DB)."""

    def meta(_packet: FeatureSnapshot, now: datetime) -> AxisEstimate:
        return AxisEstimate(
            axis="meta_context",
            value={"category": "waking/focused", "reason": "pipeline-arc-fixture"},
            timestamp=now,
            confidence=0.65,
            source="L3.fusion.meta_context.test_fixture",
            meta_context="waking/focused",
        )

    return {"meta_context": meta}


class _InterjectPolicy:
    """Real-shaped policy whose single gate clears, so L5 returns 'interject'."""

    name = "test_interject"

    def decide(self, ctx: DecisionContext) -> ActionDecision:
        trace = gate_trace_dict([], policy=self.name)
        trace["all_passed"] = True
        return ActionDecision(
            user_id=ctx.user_id,
            decided_at=ctx.now,
            action="interject",
            rationale="test fixture: gate cleared to exercise the L6 emit path",
            mode="companion",
            content_kind="conversation_tease",
            gate_trace=trace,
            i_model_id=ctx.i_model_id,
        )


def _collectors(bus: MessageBus) -> dict[str, list[MessageEnvelope]]:
    """Subscribe a per-topic collector so the trace is observable at every boundary."""
    seen: dict[str, list[MessageEnvelope]] = {
        TOPIC_SIGNAL: [], TOPIC_FEATURE: [], TOPIC_BELIEF: [],
        TOPIC_PREDICTION: [], TOPIC_ACTION: [], TOPIC_OUTPUT: [],
    }
    for topic, sink in seen.items():
        bus.subscribe(topic, sink.append)
    return seen


def run_pipeline_arc() -> MessageEnvelope:
    """Drive a full L1->L6 arc that reaches an OutputDirective on TOPIC_OUTPUT."""
    bus = MessageBus()
    assemble_pipeline(
        bus,
        fusion_registry=_fresh_axis_registry(),
        decision_policy=_InterjectPolicy(),
        renderer=StubRenderer(),  # production default is ComposerRenderer (LLM); inject to stay offline
    )
    seen = _collectors(bus)

    env = l1.emit(bus, _sample_reading(), meta_context=MetaContext.WAKING)
    trace = env.trace_id

    # Same stimulus observed at every boundary -> a real arc, not just endpoints.
    for topic in (TOPIC_SIGNAL, TOPIC_FEATURE, TOPIC_BELIEF,
                  TOPIC_PREDICTION, TOPIC_ACTION, TOPIC_OUTPUT):
        assert seen[topic], f"trace never reached {topic}"
        assert all(e.trace_id == trace for e in seen[topic]), f"trace_id drifted at {topic}"

    assert len(seen[TOPIC_OUTPUT]) == 1, f"expected 1 output, got {len(seen[TOPIC_OUTPUT])}"
    return seen[TOPIC_OUTPUT][0]


def run_silent_hold_arc() -> tuple[str, ActionDecision]:
    """Drive the honest DEFAULT arc: real policies HOLD -> L6 emits nothing."""
    bus = MessageBus()
    assemble_pipeline(
        bus,
        fusion_registry=_fresh_axis_registry(),
        renderer=StubRenderer(),  # default is now ComposerRenderer; the hold path renders nothing anyway, but keep offline
    )
    seen = _collectors(bus)

    env = l1.emit(bus, _sample_reading(), meta_context=MetaContext.WAKING)
    trace = env.trace_id

    # Trace propagates through to the L5 decision...
    assert seen[TOPIC_ACTION], "trace never reached L5"
    action: ActionDecision = seen[TOPIC_ACTION][-1].payload
    # ...where the real default policy HOLDs, so L6 publishes no directive.
    assert action.action == "hold"
    assert seen[TOPIC_OUTPUT] == [], "hold must not emit an OutputDirective (silent hold)"
    return trace, action


def test_full_arc_reaches_output_with_same_trace_id():
    out = run_pipeline_arc()
    assert out.type == PayloadType.OUTPUT
    assert isinstance(out.payload, OutputDirective)
    assert out.payload.channel == "voice"          # waking -> voice primary (#3)
    assert out.payload.text is not None            # StubRenderer produced text (no LLM)
    assert out.source_role == NodeRole.WISP_EDGE


def test_arc_inherits_meta_context_and_consent_end_to_end():
    out = run_pipeline_arc()
    assert out.meta_context == MetaContext.WAKING   # #14 carried L1->L6
    assert out.consent_scope                         # #11 consent travelled with the data


def test_each_boundary_payload_is_the_expected_type():
    bus = MessageBus()
    assemble_pipeline(
        bus,
        fusion_registry=_fresh_axis_registry(),
        decision_policy=_InterjectPolicy(),
        renderer=StubRenderer(),  # production default is ComposerRenderer (LLM); inject to stay offline
    )
    seen = _collectors(bus)
    l1.emit(bus, _sample_reading(), meta_context=MetaContext.WAKING)

    assert isinstance(seen[TOPIC_SIGNAL][0].payload, SignalPacket)
    assert isinstance(seen[TOPIC_FEATURE][0].payload, FeatureSnapshot)
    assert isinstance(seen[TOPIC_PREDICTION][0].payload, Prediction)
    assert isinstance(seen[TOPIC_ACTION][0].payload, ActionDecision)
    assert isinstance(seen[TOPIC_OUTPUT][0].payload, OutputDirective)


def test_default_arc_is_a_documented_silent_hold():
    trace, action = run_silent_hold_arc()
    assert action.action == "hold"
    assert action.gate_trace["all_passed"] is False  # real safety gates blocked
    assert isinstance(trace, str)


def test_production_default_renderer_is_composer_and_maps_decision(monkeypatch):
    """Production assembly (no renderer injected) defaults L6 to ComposerRenderer (#8).

    Drives the interject arc through the DEFAULT renderer — proving the generative
    Regis voice is now wired-AND-default, not just available. The LLM is never
    touched: we monkeypatch wisp.composer.compose_utterance (which ComposerRenderer
    imports lazily) to a recorder returning a known ComposedUtterance-like stub, then
    assert the emitted OutputDirective.text is that stub text and that compose_utterance
    was called with moment_kind/explicit_context derived from the L5 decision.
    """
    import wisp.composer as composer  # safe: module import is side-effect-free (no LLM call)

    calls: list[dict[str, object]] = []

    def _fake_compose(*, user_id, moment_kind, explicit_context="", **kwargs):
        calls.append({
            "user_id": user_id,
            "moment_kind": moment_kind,
            "explicit_context": explicit_context,
        })
        return composer.ComposedUtterance(
            text="the wisp flickers, amused",
            mode="companion",
            moment_kind=moment_kind,
            model="test-model",
            backend="test-backend",
        )

    monkeypatch.setattr(composer, "compose_utterance", _fake_compose)

    bus = MessageBus()
    # NOTE: no renderer= kwarg -> exercises the production default (ComposerRenderer).
    assemble_pipeline(
        bus,
        fusion_registry=_fresh_axis_registry(),
        decision_policy=_InterjectPolicy(),
    )
    seen = _collectors(bus)
    l1.emit(bus, _sample_reading(), meta_context=MetaContext.WAKING)

    assert len(seen[TOPIC_OUTPUT]) == 1, "production default renderer never emitted a directive"
    directive: OutputDirective = seen[TOPIC_OUTPUT][0].payload
    assert directive.text == "the wisp flickers, amused"  # came from the (mocked) composer, not the stub

    assert len(calls) == 1, "compose_utterance should be called exactly once per interject"
    # ComposerRenderer maps decision.content_kind -> moment_kind, decision.rationale -> explicit_context.
    # The L5 policy here emits content_kind='conversation_tease' + a fixed rationale.
    assert calls[0]["moment_kind"] == "conversation_tease"
    assert calls[0]["explicit_context"] == (
        "test fixture: gate cleared to exercise the L6 emit path"
    )


def _calib(axis: str) -> BlendResult:
    return BlendResult(
        axis=axis, w_personal=0.25, w_population=0.75,
        calibration_state=CalibrationState.CALIBRATING, e_personal=2.0,
        evidence_by_tier={}, population_value=0.0, population_variance=1.0,
        demographics_applied=False, population_seeded=False,
    )


def test_assemble_pipeline_calibration_reader_enriches_belief():
    """The default-arc seam (#4): a fused estimate carries the same calibration
    stamps (calibration_state + w_personal) that state/declare's arc gets via
    apply_calibration — proving the reader threads through assemble_pipeline."""
    calls: list[tuple[str, str]] = []

    def reader(user_id: str, axis: str) -> BlendResult:
        calls.append((user_id, axis))
        return _calib(axis)

    bus = MessageBus()
    assemble_pipeline(
        bus,
        fusion_registry=_fresh_axis_registry(),
        calibration_reader=reader,
        renderer=StubRenderer(),
    )
    seen = _collectors(bus)
    l1.emit(bus, _sample_reading(), meta_context=MetaContext.WAKING)

    assert seen[TOPIC_BELIEF], "trace never reached L3"
    est = seen[TOPIC_BELIEF][0].payload.estimates["meta_context"]
    assert est.value["calibration_state"] == "calibrating"
    assert est.value["w_personal"] == 0.25
    assert (USER, "meta_context") in calls


def test_assemble_pipeline_without_reader_belief_unenriched():
    """Regression pin: omitting calibration_reader is byte-identical to today."""
    bus = MessageBus()
    assemble_pipeline(bus, fusion_registry=_fresh_axis_registry(), renderer=StubRenderer())
    seen = _collectors(bus)
    l1.emit(bus, _sample_reading(), meta_context=MetaContext.WAKING)

    est = seen[TOPIC_BELIEF][0].payload.estimates["meta_context"]
    assert "calibration_state" not in est.value
    assert "w_personal" not in est.value


def test_assemble_pipeline_forwards_reader_with_default_registry(monkeypatch):
    captured: dict[str, object] = {}
    real_register = l3.register

    def recording_register(bus, *, participant=None, calibration_reader=None):
        captured["participant"] = participant
        captured["calibration_reader"] = calibration_reader
        return real_register(bus, participant=participant, calibration_reader=calibration_reader)

    monkeypatch.setattr(l3, "register", recording_register)

    def reader(user_id: str, axis: str) -> BlendResult:
        return _calib(axis)

    bus = MessageBus()
    assemble_pipeline(bus, calibration_reader=reader, renderer=StubRenderer())

    assert captured["participant"] is None
    assert captured["calibration_reader"] is reader


if __name__ == "__main__":
    out = run_pipeline_arc()
    print(
        f"reflex arc OK — trace {out.trace_id} reached L6 "
        f"(channel={out.payload.channel}, mode={out.payload.mode}, "
        f"text={out.payload.text!r})"
    )
    hold_trace, action = run_silent_hold_arc()
    print(
        f"silent-hold arc OK — trace {hold_trace} held at L5 "
        f"(action={action.action}, policy={action.gate_trace.get('policy')}) "
        f"-> no OutputDirective emitted (documented silent hold)"
    )
