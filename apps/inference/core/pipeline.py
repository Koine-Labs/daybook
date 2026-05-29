# apps/inference/core/pipeline.py
"""Assemble the full L1->L6 reflex arc onto one MessageBus — the real wiring.

Where core/smoke_test.py used inline stub handlers, this is the production
assembly: it imports each layer's real bus participant and registers it on the
shared bus so a single SignalPacket emitted at L1 propagates through L2 features,
L3 fusion, L4 prediction, L5 decision, and L6 output. L1 is the producer entry
point (sensors.participant.emit) and has no input topic to subscribe to.

The two optional injection seams (fusion_registry, decision_policy) default to
None, in which case the pure production participants run. They exist so a caller
can drive a deterministic, DB- and network-free arc through the *real* layer code
(the FusionParticipant and the real L5 DecisionContext/forward machinery), the
same way each layer's own smoke test drives its real participant with in-memory
inputs. They never change production behavior when omitted.
"""
from __future__ import annotations

from core.bus.bus import TOPIC_PREDICTION, MessageBus
from core.layer import forward_envelope
from core.protocol.enums import PayloadType
from core.protocol.envelope import MessageEnvelope

import features.participant as l2
import fusion.participant as l3
import prediction.participant as l4
import decision.participant as l5
import output.participant as l6
from decision.policy import Policy
from output.renderer import Renderer


def _register_decision_with_policy(bus: MessageBus, policy: Policy) -> None:
    """Subscribe an L5 handler that forces `policy`, reusing the real L5 machinery."""

    def _handler(env: MessageEnvelope) -> None:
        ctx = l5._context_from(env)
        decision = policy.decide(ctx)
        out = forward_envelope(
            env,
            ptype=PayloadType.ACTION,
            payload=decision,
            source_role=l5.SOURCE_ROLE,
        )
        bus.publish(l5.TOPIC_ACTION, out)

    bus.subscribe(TOPIC_PREDICTION, _handler)


def assemble_pipeline(
    bus: MessageBus,
    *,
    fusion_registry: dict[str, l3.AxisCombiner] | None = None,
    decision_policy: Policy | None = None,
    renderer: Renderer | None = None,
) -> None:
    """Register every layer participant (L2-L6) on one bus; L1 emits separately.

    With all keyword args omitted this wires the pure production participants.
    The injection seams let a caller drive the real layer code deterministically.
    """
    l2.register(bus)

    fusion_participant = (
        l3.FusionParticipant(registry=fusion_registry)
        if fusion_registry is not None
        else None
    )
    l3.register(bus, participant=fusion_participant)

    l4.register(bus)

    if decision_policy is not None:
        _register_decision_with_policy(bus, decision_policy)
    else:
        l5.register(bus)

    l6.register(bus, renderer=renderer)


if __name__ == "__main__":
    from core.test_pipeline import run_pipeline_arc, run_silent_hold_arc

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
