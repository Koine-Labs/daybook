# apps/inference/output/participant.py
"""L6 Output bus participant — TOPIC_ACTION → TOPIC_OUTPUT.

Subscribes the inbound action topic; for each ActionDecision it selects a
channel from the active meta_context (#14, #3), renders the utterance text via
an injectable Renderer (StubRenderer by default — no LLM in test paths), and
publishes an OutputDirective on TOPIC_OUTPUT via core/layer.py's forward helper
so trace_id / meta_context / consent_scope / i_model_id are inherited.

Hold / silent policy (documented + consistent):
- action == "hold": emit NO directive (the decision was to stay silent).
- channel == CHANNEL_SILENT (e.g. deep sleep, #14): emit a directive marked
  silent (channel="visual", text=None) so the trace remains followable to L6
  WITHOUT producing any voice — never drop the trace, never speak over a sleeper.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.bus.bus import TOPIC_ACTION, TOPIC_OUTPUT, MessageBus
from core.layer import forward_envelope
from core.nodes import role_for
from core.protocol.enums import MetaContext, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import ActionDecision, OutputDirective

from output.channels import ChannelChoice, select_channel
from output.renderer import Renderer, StubRenderer

SOURCE_ROLE = role_for("L6.output")


def _sub_state_of(decision: ActionDecision, env: MessageEnvelope) -> str | None:
    """Best-effort finer sleep/waking sub-state for channel refinement.

    The top-level meta_context is on the envelope (#14); the finer tag (e.g.
    'deep', 'rem', 'awake-in-bed') may ride in the decision's gate_trace.
    """
    sub = decision.gate_trace.get("sub_state")
    return str(sub) if sub is not None else None


def _build_directive(
    decision: ActionDecision, choice: ChannelChoice, text: str | None
) -> OutputDirective:
    """Construct the OutputDirective. Silent choices carry no text + visual channel."""
    if choice.is_silent:
        return OutputDirective(
            user_id=decision.user_id,
            created_at=datetime.now(timezone.utc),
            channel="visual",  # OutputDirective has no 'silent' literal; visual + no text = silent
            mode=decision.mode,
            text=None,
            delivery={"silent": True, "reason": choice.reason},
            i_model_id=decision.i_model_id,
        )
    return OutputDirective(
        user_id=decision.user_id,
        created_at=datetime.now(timezone.utc),
        channel=choice.channel,  # type: ignore[arg-type]  # "voice" within Literal
        mode=decision.mode,
        text=text,
        delivery={**choice.delivery, "reason": choice.reason},
        i_model_id=decision.i_model_id,
    )


class OutputParticipant:
    """L6 organ: action → (channel, rendered text) → OutputDirective."""

    def __init__(self, bus: MessageBus, *, renderer: Renderer | None = None) -> None:
        self._bus = bus
        self._renderer: Renderer = renderer or StubRenderer()

    def _handle(self, env: MessageEnvelope) -> None:
        decision = env.payload
        if not isinstance(decision, ActionDecision):
            return  # not ours; ignore foreign payloads on the topic

        # Hold = stay silent. The decision itself was to not act → emit nothing.
        if decision.action == "hold":
            return

        meta = env.meta_context if isinstance(env.meta_context, MetaContext) else MetaContext(env.meta_context)
        choice = select_channel(meta, sub_state=_sub_state_of(decision, env))

        text = None if choice.is_silent else self._renderer.render(decision, mode=decision.mode)
        directive = _build_directive(decision, choice, text)

        out = forward_envelope(
            env,
            ptype=PayloadType.OUTPUT,
            payload=directive,
            source_role=SOURCE_ROLE,
        )
        self._bus.publish(TOPIC_OUTPUT, out)


def register(bus: MessageBus, *, renderer: Renderer | None = None) -> OutputParticipant:
    """Subscribe the L6 participant to TOPIC_ACTION; returns it for test access."""
    participant = OutputParticipant(bus, renderer=renderer)
    bus.subscribe(TOPIC_ACTION, participant._handle)
    return participant
