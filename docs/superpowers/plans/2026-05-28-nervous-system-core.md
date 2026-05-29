# Daybook Nervous System — Core (Protocol + Bus + Node Roles) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the typed message protocol, the in-process bus (behind a Transport seam), and the node-role body map that let a single stimulus travel L1→L6, so the six layer skeletons can later be built and split across devices without internal change.

**Architecture:** Dataclass message payloads (matching the existing `FeatureSnapshot`/`AxisEstimate` style) wrapped in a `MessageEnvelope` that carries routing + meta-context + consent + a `trace_id`. A synchronous `InProcessBus` delivers envelopes by topic via a `Transport` interface; today everything runs in one process, later a `NetworkTransport` slots underneath unchanged. A declarative placement map records each component's eventual node.

**Tech Stack:** Python 3.11 (dataclasses, `from __future__ import annotations`), pytest. TypeScript mirror in `packages/shared` (tsc). No new third-party deps.

**Scope:** This plan is the *Core only* — the nerves, not the organs. The six layer skeletons (sensors/features/fusion/prediction/decision/output) are separate follow-on plans that build against the protocol this plan freezes. `NetworkTransport`, schema-versioning machinery, and full `from_dict` deserialization are explicitly deferred (in-process delivery passes Python objects; no wire decode needed yet).

**Prerequisites:** On branch `feat/nervous-system-skeleton` (already created). All Python steps run from the inference dir with the venv active:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference" && source .venv/bin/activate
```

---

### Task 1: Protocol enums

**Files:**
- Create: `apps/inference/core/__init__.py`
- Create: `apps/inference/core/protocol/__init__.py`
- Create: `apps/inference/core/protocol/enums.py`
- Test: `apps/inference/core/protocol/test_enums.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/inference/core/protocol/test_enums.py
from core.protocol.enums import Intent, MetaContext, Modality, NodeRole, PayloadType


def test_enum_values_are_json_friendly_strings():
    assert NodeRole.WISP_EDGE.value == "wisp_edge"
    assert MetaContext.WAKING.value == "waking"
    assert Modality.BCI.value == "bci"
    assert Intent.CONTINUOUS.value == "continuous"
    assert PayloadType.SIGNAL.value == "signal"


def test_payload_type_covers_six_layer_boundaries():
    assert {p.value for p in PayloadType} == {
        "signal", "feature", "belief", "prediction", "action", "output"
    }


def test_modality_covers_commitment_10_set():
    assert {m.value for m in Modality} == {
        "voice", "text", "gesture", "biometric", "audio", "vision", "bci"
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest core/protocol/test_enums.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core'`

- [ ] **Step 3: Create the package + enums**

```python
# apps/inference/core/__init__.py
"""Daybook nervous system — protocol, bus, and node-role map."""
```

```python
# apps/inference/core/protocol/__init__.py
"""Typed message protocol: envelope + per-layer payloads + enums."""
```

```python
# apps/inference/core/protocol/enums.py
"""Enumerations used across the message protocol. All str-valued for clean JSON."""
from __future__ import annotations

from enum import Enum


class NodeRole(str, Enum):
    """Eventual physical home of a component in the distributed system."""

    WISP_EDGE = "wisp_edge"
    PHONE_RELAY = "phone_relay"
    DESKTOP_COMPUTE = "desktop_compute"
    CLOUD = "cloud"


class MetaContext(str, Enum):
    """Top-level context that biases every layer (commitment #14)."""

    WAKING = "waking"
    SLEEP = "sleep"
    UNKNOWN = "unknown"


class Modality(str, Enum):
    """Signal type at the L1 boundary (commitment #10, modality axis)."""

    VOICE = "voice"
    TEXT = "text"
    GESTURE = "gesture"
    BIOMETRIC = "biometric"
    AUDIO = "audio"
    VISION = "vision"
    BCI = "bci"


class Intent(str, Enum):
    """Communication-intent at the L1 boundary (commitment #10, intent axis)."""

    EXPLICIT = "explicit"
    CONTINUOUS = "continuous"


class PayloadType(str, Enum):
    """Discriminator naming which layer boundary an envelope's payload crosses."""

    SIGNAL = "signal"        # L1 -> L2
    FEATURE = "feature"      # L2 -> L3
    BELIEF = "belief"        # L3 -> L4
    PREDICTION = "prediction"  # L4 -> L5
    ACTION = "action"        # L5 -> L6
    OUTPUT = "output"        # L6 -> channel
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest core/protocol/test_enums.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/inference/core/__init__.py apps/inference/core/protocol/__init__.py apps/inference/core/protocol/enums.py apps/inference/core/protocol/test_enums.py
git commit -m "feat(core): protocol enums (NodeRole, MetaContext, Modality, Intent, PayloadType)"
```

---

### Task 2: Payload dataclasses (the four new ones + re-exports)

**Files:**
- Create: `apps/inference/core/protocol/payloads.py`
- Test: `apps/inference/core/protocol/test_payloads.py`

Reuses the existing `FeatureSnapshot` (`apps/inference/features/snapshot.py`) and `BeliefState`/`AxisEstimate` (`apps/inference/fusion/belief_state.py`) — the L2 and L3 payloads. Defines the four payloads that don't exist yet: `SignalPacket`, `Prediction`, `ActionDecision`, `OutputDirective`.

- [ ] **Step 1: Write the failing test**

```python
# apps/inference/core/protocol/test_payloads.py
import json
from datetime import datetime, timezone

import pytest

from core.protocol.payloads import (ActionDecision, FeaturePacket, OutputDirective,
                                     Prediction, SignalPacket)


def _utc():
    return datetime.now(timezone.utc)


def test_signal_packet_serializes_to_json():
    sig = SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                       intent="continuous", kind="speech_final",
                       payload={"text": "mm"}, source="mac.mic")
    d = sig.to_dict()
    json.dumps(d)  # must not raise
    assert d["modality"] == "audio" and isinstance(d["timestamp"], str)


def test_signal_packet_rejects_naive_datetime():
    with pytest.raises(ValueError):
        SignalPacket(user_id="u", timestamp=datetime(2026, 5, 28), modality="audio",
                     intent="continuous", kind="x", payload={}, source="s")


def test_signal_packet_rejects_out_of_range_confidence():
    with pytest.raises(ValueError):
        SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                     intent="continuous", kind="x", payload={}, source="s",
                     confidence=1.5)


def test_prediction_carries_action_seam_and_provenance():
    p = Prediction(user_id="u", axis="arousal_inferred", made_at=_utc(),
                   horizon_seconds=1800, distribution={"calm": 0.7}, model_id="stub.v0")
    assert p.action is None and p.provenance == "placeholder" and p.cold_start is False
    json.dumps(p.to_dict())


def test_action_decision_and_output_directive_serialize():
    dec = ActionDecision(user_id="u", decided_at=_utc(), action="hold",
                         rationale="nothing worth saying")
    out = OutputDirective(user_id="u", created_at=_utc(), channel="voice", text="hey")
    json.dumps(dec.to_dict())
    json.dumps(out.to_dict())
    assert dec.gate_trace == {} and out.delivery == {}


def test_feature_packet_is_feature_snapshot_alias():
    fp = FeaturePacket(user_id="u", timestamp=_utc(), modality="audio",
                       source="mac.mic", payload={"rms": 0.1})
    assert fp.to_dict()["modality"] == "audio"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest core/protocol/test_payloads.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.protocol.payloads'`

- [ ] **Step 3: Write the payloads module**

```python
# apps/inference/core/protocol/payloads.py
"""Per-layer message payloads.

L2 (FeatureSnapshot) and L3 (BeliefState/AxisEstimate) payloads are reused from
their owning modules and re-exported here so the protocol has one import home.
The four payloads that don't exist elsewhere are defined here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

from features.snapshot import FeatureSnapshot
from fusion.belief_state import AxisEstimate, BeliefState

# L2 payload is the FeatureSnapshot itself; alias keeps the protocol name explicit.
FeaturePacket = FeatureSnapshot

__all__ = [
    "SignalPacket", "FeaturePacket", "FeatureSnapshot", "BeliefState", "AxisEstimate",
    "Prediction", "ActionDecision", "OutputDirective",
]


def _require_utc(name: str, ts: datetime) -> None:
    if ts.tzinfo is None:
        raise ValueError(f"{name} must be tz-aware UTC")


@dataclass
class SignalPacket:
    """L1 -> L2. Intent- and modality-tagged signal (commitment #10).

    Semantic-first (#11): only meaningful extractions ride here, never raw bytes.
    """

    user_id: str
    timestamp: datetime               # tz-aware UTC
    modality: str                     # a Modality value
    intent: str                       # an Intent value
    kind: str                         # e.g. 'speech_final', 'hr_30s', 'mac_activity'
    payload: dict[str, Any]
    source: str                       # e.g. 'mac.mic', 'watch.hr_30s'
    confidence: float | None = None
    i_model_id: str | None = None     # commitment #1

    def __post_init__(self) -> None:
        _require_utc("SignalPacket.timestamp", self.timestamp)
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class Prediction:
    """L4 -> L5. Forecast for (axis, horizon, action), with provenance (#15/#16)."""

    user_id: str
    axis: str
    made_at: datetime                 # tz-aware UTC
    horizon_seconds: int
    distribution: dict[str, Any]      # categorical probs or {mean, variance}
    model_id: str
    confidence: float | None = None
    action: dict[str, Any] | None = None  # None = baseline; non-null = counterfactual
    provenance: Literal["placeholder", "calibrated"] = "placeholder"
    cold_start: bool = False
    i_model_id: str | None = None

    def __post_init__(self) -> None:
        _require_utc("Prediction.made_at", self.made_at)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["made_at"] = self.made_at.isoformat()
        return d


@dataclass
class ActionDecision:
    """L5 -> L6. Chosen action + rationale + safety-gate trace."""

    user_id: str
    decided_at: datetime              # tz-aware UTC
    action: Literal["interject", "hold"]
    rationale: str
    mode: Literal["witness", "companion"] | None = None
    content_kind: str | None = None
    gate_trace: dict[str, Any] = field(default_factory=dict)
    i_model_id: str | None = None

    def __post_init__(self) -> None:
        _require_utc("ActionDecision.decided_at", self.decided_at)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decided_at"] = self.decided_at.isoformat()
        return d


@dataclass
class OutputDirective:
    """L6 -> channel. Rendered intent + channel + delivery params (voice primary, #3)."""

    user_id: str
    created_at: datetime              # tz-aware UTC
    channel: Literal["voice", "haptic", "visual"]
    mode: Literal["witness", "companion"] | None = None
    text: str | None = None
    delivery: dict[str, Any] = field(default_factory=dict)
    i_model_id: str | None = None

    def __post_init__(self) -> None:
        _require_utc("OutputDirective.created_at", self.created_at)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest core/protocol/test_payloads.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/inference/core/protocol/payloads.py apps/inference/core/protocol/test_payloads.py
git commit -m "feat(core): message payloads (SignalPacket, Prediction, ActionDecision, OutputDirective) + L2/L3 re-exports"
```

---

### Task 3: Wire codec + MessageEnvelope

**Files:**
- Create: `apps/inference/core/protocol/codec.py`
- Create: `apps/inference/core/protocol/envelope.py`
- Test: `apps/inference/core/protocol/test_envelope.py`

The codec centralizes payload→dict serialization (the wire seam). `BeliefState` has no `to_dict`, so the codec serializes it explicitly without touching `fusion/`.

- [ ] **Step 1: Write the failing test**

```python
# apps/inference/core/protocol/test_envelope.py
import json
import uuid
from datetime import datetime, timezone

import pytest

from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import (ActionDecision, BeliefState, FeaturePacket,
                                     OutputDirective, Prediction, SignalPacket)
from fusion.belief_state import AxisEstimate


def _utc():
    return datetime.now(timezone.utc)


def _env(ptype, payload):
    return MessageEnvelope(id=str(uuid.uuid4()), type=ptype,
                           source_role=NodeRole.WISP_EDGE, occurred_at=_utc(),
                           meta_context=MetaContext.WAKING, consent_scope="personal_use",
                           trace_id=str(uuid.uuid4()), payload=payload)


def test_envelope_rejects_naive_occurred_at():
    with pytest.raises(ValueError):
        MessageEnvelope(id="i", type=PayloadType.SIGNAL, source_role=NodeRole.WISP_EDGE,
                        occurred_at=datetime(2026, 5, 28), meta_context=MetaContext.WAKING,
                        consent_scope="p", trace_id="t",
                        payload=SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                                             intent="continuous", kind="x", payload={}, source="s"))


def test_envelope_serializes_every_payload_type():
    bs = BeliefState(user_id="u")
    bs.update(AxisEstimate(axis="arousal_inferred", value={"label": "calm"},
                           timestamp=_utc(), confidence=0.5, source="L3.stub"))
    cases = {
        PayloadType.SIGNAL: SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                                         intent="continuous", kind="x", payload={}, source="s"),
        PayloadType.FEATURE: FeaturePacket(user_id="u", timestamp=_utc(), modality="audio",
                                           source="s", payload={"rms": 0.1}),
        PayloadType.BELIEF: bs,
        PayloadType.PREDICTION: Prediction(user_id="u", axis="a", made_at=_utc(),
                                           horizon_seconds=60, distribution={"x": 1.0},
                                           model_id="m"),
        PayloadType.ACTION: ActionDecision(user_id="u", decided_at=_utc(), action="hold",
                                           rationale="r"),
        PayloadType.OUTPUT: OutputDirective(user_id="u", created_at=_utc(), channel="voice"),
    }
    for ptype, payload in cases.items():
        d = _env(ptype, payload).to_dict()
        json.dumps(d)  # whole envelope must be JSON-serializable
        assert d["type"] == ptype.value
        assert d["source_role"] == "wisp_edge"
        assert "payload" in d


def test_belief_payload_serializes_estimates():
    bs = BeliefState(user_id="u")
    bs.update(AxisEstimate(axis="sleep_stage", value={"label": "rem"}, timestamp=_utc(),
                           confidence=0.7, source="apple_health"))
    d = _env(PayloadType.BELIEF, bs).to_dict()
    assert d["payload"]["estimates"]["sleep_stage"]["value"] == {"label": "rem"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest core/protocol/test_envelope.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.protocol.envelope'`

- [ ] **Step 3: Write the codec then the envelope**

```python
# apps/inference/core/protocol/codec.py
"""Payload <-> dict serialization (the wire seam).

In-process delivery passes Python objects untouched; this codec exists for the
future NetworkTransport and for tests that prove every payload is JSON-ready.
BeliefState is serialized explicitly here so fusion/ stays untouched.
"""
from __future__ import annotations

from typing import Any

from core.protocol.enums import PayloadType
from fusion.belief_state import AxisEstimate, BeliefState


def _axis_to_dict(est: AxisEstimate) -> dict[str, Any]:
    return {
        "axis": est.axis,
        "value": est.value,
        "timestamp": est.timestamp.isoformat(),
        "confidence": est.confidence,
        "source": est.source,
        "meta_context": est.meta_context,
        "i_model_id": est.i_model_id,
        "fresh_for_seconds": est.fresh_for_seconds,
    }


def _belief_to_dict(bs: BeliefState) -> dict[str, Any]:
    return {
        "user_id": bs.user_id,
        "estimates": {ax: _axis_to_dict(e) for ax, e in bs.estimates.items()},
    }


def payload_to_dict(ptype: PayloadType, payload: Any) -> dict[str, Any]:
    """Serialize a payload to a JSON-ready dict, dispatched by its type."""
    if ptype == PayloadType.BELIEF:
        return _belief_to_dict(payload)
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    raise TypeError(f"no serializer for payload type {ptype}")
```

```python
# apps/inference/core/protocol/envelope.py
"""MessageEnvelope — the wrapper every message rides in across layers and nodes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Union

from core.protocol.codec import payload_to_dict
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.payloads import (ActionDecision, BeliefState, FeatureSnapshot,
                                     OutputDirective, Prediction, SignalPacket)

Payload = Union[SignalPacket, FeatureSnapshot, BeliefState, Prediction,
                ActionDecision, OutputDirective]


@dataclass
class MessageEnvelope:
    """Routing + context + consent wrapper around one layer payload.

    Carries meta_context (#14), consent_scope (#11), i_model_id (#1), and a
    trace_id so one stimulus can be followed through all six layers.
    """

    id: str
    type: PayloadType
    source_role: NodeRole
    occurred_at: datetime             # tz-aware UTC
    meta_context: MetaContext
    consent_scope: str
    trace_id: str
    payload: Payload
    schema_version: int = 1
    target_role: NodeRole | None = None
    i_model_id: str | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("MessageEnvelope.occurred_at must be tz-aware UTC")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "schema_version": self.schema_version,
            "source_role": self.source_role.value,
            "target_role": self.target_role.value if self.target_role else None,
            "occurred_at": self.occurred_at.isoformat(),
            "meta_context": self.meta_context.value,
            "consent_scope": self.consent_scope,
            "trace_id": self.trace_id,
            "i_model_id": self.i_model_id,
            "payload": payload_to_dict(self.type, self.payload),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest core/protocol/test_envelope.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/inference/core/protocol/codec.py apps/inference/core/protocol/envelope.py apps/inference/core/protocol/test_envelope.py
git commit -m "feat(core): MessageEnvelope + wire codec (JSON-serializable for all 6 payload types)"
```

---

### Task 4: Transport interface + InProcessTransport

**Files:**
- Create: `apps/inference/core/bus/__init__.py`
- Create: `apps/inference/core/bus/transport.py`
- Test: `apps/inference/core/bus/test_transport.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/inference/core/bus/test_transport.py
import uuid
from datetime import datetime, timezone

from core.bus.transport import InProcessTransport
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import SignalPacket


def _signal_env(trace="t"):
    sig = SignalPacket(user_id="u", timestamp=datetime.now(timezone.utc),
                       modality="audio", intent="continuous", kind="x",
                       payload={}, source="s")
    return MessageEnvelope(id=str(uuid.uuid4()), type=PayloadType.SIGNAL,
                           source_role=NodeRole.WISP_EDGE,
                           occurred_at=datetime.now(timezone.utc),
                           meta_context=MetaContext.WAKING, consent_scope="p",
                           trace_id=trace, payload=sig)


def test_registered_handler_receives_sent_envelope():
    t = InProcessTransport()
    got = []
    t.register("topic.a", got.append)
    env = _signal_env()
    t.send("topic.a", env)
    assert got == [env]


def test_send_to_topic_with_no_handlers_is_noop():
    t = InProcessTransport()
    t.send("topic.empty", _signal_env())  # must not raise


def test_multiple_handlers_all_receive():
    t = InProcessTransport()
    a, b = [], []
    t.register("topic.a", a.append)
    t.register("topic.a", b.append)
    t.send("topic.a", _signal_env())
    assert len(a) == 1 and len(b) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest core/bus/test_transport.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.bus'`

- [ ] **Step 3: Write the package + transport**

```python
# apps/inference/core/bus/__init__.py
"""Message bus + transport seam."""
```

```python
# apps/inference/core/bus/transport.py
"""Transport seam: how envelopes are physically delivered.

Today: InProcessTransport (synchronous, single process). Later: a NetworkTransport
(broker / HTTP relay) implements the same interface so layers never change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Callable

from core.protocol.envelope import MessageEnvelope

Handler = Callable[[MessageEnvelope], None]


class Transport(ABC):
    """Delivers envelopes to handlers registered on a topic."""

    @abstractmethod
    def register(self, topic: str, handler: Handler) -> None: ...

    @abstractmethod
    def send(self, topic: str, env: MessageEnvelope) -> None: ...


class InProcessTransport(Transport):
    """In-memory synchronous delivery: send() calls each handler inline."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def register(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)

    def send(self, topic: str, env: MessageEnvelope) -> None:
        for handler in list(self._handlers.get(topic, [])):
            handler(env)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest core/bus/test_transport.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/inference/core/bus/__init__.py apps/inference/core/bus/transport.py apps/inference/core/bus/test_transport.py
git commit -m "feat(core): Transport seam + InProcessTransport"
```

---

### Task 5: MessageBus + topic constants

**Files:**
- Create: `apps/inference/core/bus/bus.py`
- Test: `apps/inference/core/bus/test_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/inference/core/bus/test_bus.py
import uuid
from datetime import datetime, timezone

from core.bus.bus import (TOPIC_FEATURE, TOPIC_SIGNAL, MessageBus)
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import SignalPacket


def _signal_env():
    sig = SignalPacket(user_id="u", timestamp=datetime.now(timezone.utc),
                       modality="audio", intent="continuous", kind="x",
                       payload={}, source="s")
    return MessageEnvelope(id=str(uuid.uuid4()), type=PayloadType.SIGNAL,
                           source_role=NodeRole.WISP_EDGE,
                           occurred_at=datetime.now(timezone.utc),
                           meta_context=MetaContext.WAKING, consent_scope="p",
                           trace_id="t", payload=sig)


def test_publish_reaches_subscriber_on_same_topic():
    bus = MessageBus()
    got = []
    bus.subscribe(TOPIC_SIGNAL, got.append)
    bus.publish(TOPIC_SIGNAL, _signal_env())
    assert len(got) == 1


def test_topics_are_isolated():
    bus = MessageBus()
    got = []
    bus.subscribe(TOPIC_FEATURE, got.append)
    bus.publish(TOPIC_SIGNAL, _signal_env())
    assert got == []


def test_topic_constants_cover_all_six_boundaries():
    from core.bus import bus as busmod
    names = {busmod.TOPIC_SIGNAL, busmod.TOPIC_FEATURE, busmod.TOPIC_BELIEF,
             busmod.TOPIC_PREDICTION, busmod.TOPIC_ACTION, busmod.TOPIC_OUTPUT}
    assert len(names) == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest core/bus/test_bus.py -v`
Expected: FAIL — `ImportError: cannot import name 'MessageBus'`

- [ ] **Step 3: Write the bus**

```python
# apps/inference/core/bus/bus.py
"""MessageBus — the publish/subscribe API layers use, over a Transport."""
from __future__ import annotations

from core.bus.transport import Handler, InProcessTransport, Transport
from core.protocol.envelope import MessageEnvelope

# One topic per layer boundary.
TOPIC_SIGNAL = "l1.signal"
TOPIC_FEATURE = "l2.feature"
TOPIC_BELIEF = "l3.belief"
TOPIC_PREDICTION = "l4.prediction"
TOPIC_ACTION = "l5.action"
TOPIC_OUTPUT = "l6.output"


class MessageBus:
    """Ergonomic publish/subscribe over a pluggable Transport."""

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport = transport or InProcessTransport()

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._transport.register(topic, handler)

    def publish(self, topic: str, env: MessageEnvelope) -> None:
        self._transport.send(topic, env)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest core/bus/test_bus.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/inference/core/bus/bus.py apps/inference/core/bus/test_bus.py
git commit -m "feat(core): MessageBus + per-boundary topic constants"
```

---

### Task 6: Node-role placement map

**Files:**
- Create: `apps/inference/core/nodes.py`
- Test: `apps/inference/core/test_nodes.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/inference/core/test_nodes.py
import pytest

from core.nodes import PLACEMENT, role_for
from core.protocol.enums import NodeRole


def test_every_layer_has_a_placement():
    for component in ("L1.capture", "L2.features", "L3.fusion",
                      "L4.prediction", "L5.decision", "L6.output"):
        assert isinstance(role_for(component), NodeRole)


def test_heavy_compute_lives_on_desktop():
    assert role_for("L4.prediction") == NodeRole.DESKTOP_COMPUTE
    assert role_for("embeddings") == NodeRole.DESKTOP_COMPUTE


def test_llm_lives_in_cloud_and_capture_on_wisp():
    assert role_for("llm") == NodeRole.CLOUD
    assert role_for("L1.capture") == NodeRole.WISP_EDGE


def test_unknown_component_raises():
    with pytest.raises(KeyError):
        role_for("nope")
    assert PLACEMENT  # map is non-empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest core/test_nodes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.nodes'`

- [ ] **Step 3: Write the placement map**

```python
# apps/inference/core/nodes.py
"""Node-role body map: where each component eventually runs.

Today every role runs in one process (the Mac). This map is the destination
written as code and is what a future NetworkTransport will route by. Generalizes
apps/AI_PI_CONTRACT.md across four nodes.
"""
from __future__ import annotations

from core.protocol.enums import NodeRole

PLACEMENT: dict[str, NodeRole] = {
    "L1.capture": NodeRole.WISP_EDGE,
    "L2.features": NodeRole.WISP_EDGE,
    "L3.fusion": NodeRole.DESKTOP_COMPUTE,
    "L4.prediction": NodeRole.DESKTOP_COMPUTE,
    "L5.decision": NodeRole.DESKTOP_COMPUTE,
    "L6.output": NodeRole.WISP_EDGE,
    "llm": NodeRole.CLOUD,
    "embeddings": NodeRole.DESKTOP_COMPUTE,
}


def role_for(component: str) -> NodeRole:
    """Return the eventual NodeRole of a component; raise KeyError if unmapped."""
    try:
        return PLACEMENT[component]
    except KeyError as exc:
        raise KeyError(f"no node-role placement for component {component!r}") from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest core/test_nodes.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/inference/core/nodes.py apps/inference/core/test_nodes.py
git commit -m "feat(core): node-role placement map (role_for)"
```

---

### Task 7: End-to-end reflex arc (the one-command L1→L6 run)

**Files:**
- Create: `apps/inference/core/smoke_test.py`

Wires six inline stub handlers (one per boundary) onto the bus and proves a single `SignalPacket` produces an `OutputDirective` carrying the same `trace_id`. This is the spec's definition-of-done #2. Stubs live in the test, not in the layer packages — the real organs are separate plans.

- [ ] **Step 1: Write the failing test**

```python
# apps/inference/core/smoke_test.py
"""End-to-end reflex arc through the bus — proves the nerves carry a full L1->L6
trace. Run: python -m core.smoke_test (from apps/inference)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.bus.bus import (TOPIC_ACTION, TOPIC_BELIEF, TOPIC_FEATURE, TOPIC_OUTPUT,
                          TOPIC_PREDICTION, TOPIC_SIGNAL, MessageBus)
from core.protocol.enums import (Intent, MetaContext, Modality, NodeRole, PayloadType)
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import (ActionDecision, FeatureSnapshot, OutputDirective,
                                     Prediction, SignalPacket)
from fusion.belief_state import AxisEstimate, BeliefState

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _utc():
    return datetime.now(timezone.utc)


def _env(ptype, payload, trace, role):
    return MessageEnvelope(id=str(uuid.uuid4()), type=ptype, source_role=role,
                           occurred_at=_utc(), meta_context=MetaContext.WAKING,
                           consent_scope="mic_continuous_v1", trace_id=trace,
                           payload=payload)


def run_reflex_arc() -> MessageEnvelope:
    bus = MessageBus()
    received: list[MessageEnvelope] = []

    def l2(env):  # L1 signal -> L2 feature
        sig = env.payload
        snap = FeatureSnapshot(user_id=sig.user_id, timestamp=sig.timestamp,
                               modality=sig.modality, source=sig.source,
                               payload={"echo": sig.payload}, intent=sig.intent)
        bus.publish(TOPIC_FEATURE, _env(PayloadType.FEATURE, snap, env.trace_id,
                                        NodeRole.WISP_EDGE))

    def l3(env):  # L2 feature -> L3 belief
        snap = env.payload
        bs = BeliefState(user_id=snap.user_id)
        bs.update(AxisEstimate(axis="arousal_inferred", value={"label": "calm"},
                               timestamp=snap.timestamp, confidence=0.5, source="L3.stub"))
        bus.publish(TOPIC_BELIEF, _env(PayloadType.BELIEF, bs, env.trace_id,
                                       NodeRole.DESKTOP_COMPUTE))

    def l4(env):  # L3 belief -> L4 prediction
        bs = env.payload
        pred = Prediction(user_id=bs.user_id, axis="arousal_inferred", made_at=_utc(),
                          horizon_seconds=1800, distribution={"calm": 0.7, "tense": 0.3},
                          model_id="stub.v0")
        bus.publish(TOPIC_PREDICTION, _env(PayloadType.PREDICTION, pred, env.trace_id,
                                           NodeRole.DESKTOP_COMPUTE))

    def l5(env):  # L4 prediction -> L5 action
        pred = env.payload
        dec = ActionDecision(user_id=pred.user_id, decided_at=_utc(), action="hold",
                             rationale="stub: nothing worth saying",
                             gate_trace={"novelty": "below_threshold"})
        bus.publish(TOPIC_ACTION, _env(PayloadType.ACTION, dec, env.trace_id,
                                       NodeRole.DESKTOP_COMPUTE))

    def l6(env):  # L5 action -> L6 output
        dec = env.payload
        out = OutputDirective(user_id=dec.user_id, created_at=_utc(), channel="voice",
                              mode="companion",
                              text=None if dec.action == "hold" else "…")
        bus.publish(TOPIC_OUTPUT, _env(PayloadType.OUTPUT, out, env.trace_id,
                                       NodeRole.WISP_EDGE))

    bus.subscribe(TOPIC_SIGNAL, l2)
    bus.subscribe(TOPIC_FEATURE, l3)
    bus.subscribe(TOPIC_BELIEF, l4)
    bus.subscribe(TOPIC_PREDICTION, l5)
    bus.subscribe(TOPIC_ACTION, l6)
    bus.subscribe(TOPIC_OUTPUT, received.append)

    trace = str(uuid.uuid4())
    sig = SignalPacket(user_id=USER, timestamp=_utc(), modality=Modality.AUDIO.value,
                       intent=Intent.CONTINUOUS.value, kind="speech_final",
                       payload={"text": "mm"}, source="mac.mic")
    bus.publish(TOPIC_SIGNAL, _env(PayloadType.SIGNAL, sig, trace, NodeRole.WISP_EDGE))

    assert len(received) == 1, f"expected 1 output, got {len(received)}"
    assert received[0].trace_id == trace, "trace_id not preserved across the arc"
    return received[0]


def test_reflex_arc_preserves_trace_and_reaches_l6():
    out = run_reflex_arc()
    assert out.type == PayloadType.OUTPUT
    assert isinstance(out.payload, OutputDirective)
    assert out.payload.channel == "voice"


if __name__ == "__main__":
    env = run_reflex_arc()
    print(f"reflex arc OK — trace {env.trace_id} reached L6 "
          f"({env.payload.channel}, mode={env.payload.mode})")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest core/smoke_test.py -v`
Expected: FAIL initially only if a prior task's symbol is missing; since Tasks 1–6 are done, this should be the first run. If any import is wrong it fails here.

- [ ] **Step 3: No new implementation needed**

The reflex arc uses only Core modules from Tasks 1–6. If Step 2 fails, fix the offending import/signature to match the earlier task definitions — do not invent new symbols.

- [ ] **Step 4: Run test + the one-command run to verify both pass**

Run: `python -m pytest core/smoke_test.py -v`
Expected: PASS (1 passed)

Run: `python -m core.smoke_test`
Expected: prints `reflex arc OK — trace <uuid> reached L6 (voice, mode=companion)`

- [ ] **Step 5: Commit**

```bash
git add apps/inference/core/smoke_test.py
git commit -m "feat(core): end-to-end reflex arc — single trace_id flows L1->L6 through the bus"
```

---

### Task 8: TypeScript protocol mirror + fix duplicate import

**Files:**
- Create: `packages/shared/src/protocol.ts`
- Modify: `packages/shared/src/index.ts`
- Modify: `packages/shared/src/types.ts:30` (remove duplicate `IModelID` import that breaks `tsc`)

- [ ] **Step 1: Verify the current TS compile failure**

Run: `npx tsc --noEmit -p "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/packages/shared"`
Expected: FAIL — duplicate identifier `IModelID` (imported twice in `types.ts`).
(If `tsc` is missing: run `pnpm install` at the repo root first.)

- [ ] **Step 2: Fix the duplicate import in types.ts**

In `packages/shared/src/types.ts`, the import block lists `IModelID,` twice. Delete the **second** occurrence (the line near `IntentID,`), keeping the first. The corrected block imports `IModelID` exactly once.

- [ ] **Step 3: Create the protocol mirror**

```typescript
// packages/shared/src/protocol.ts
/**
 * Daybook nervous-system message protocol — TS mirror of
 * apps/inference/core/protocol/*. Field names are camelCase here; the Python
 * side is snake_case. JSON on the wire uses the Python (snake_case) names.
 */
import type { ISODateTime, UUID } from "./types";

export type NodeRole = "wisp_edge" | "phone_relay" | "desktop_compute" | "cloud";
export type MetaContext = "waking" | "sleep" | "unknown";
export type Modality =
  | "voice" | "text" | "gesture" | "biometric" | "audio" | "vision" | "bci";
export type Intent = "explicit" | "continuous";
export type PayloadType =
  | "signal" | "feature" | "belief" | "prediction" | "action" | "output";

export interface SignalPacket {
  userId: UUID;
  timestamp: ISODateTime;
  modality: Modality;
  intent: Intent;
  kind: string;
  payload: Record<string, unknown>;
  source: string;
  confidence?: number | null;
  iModelId?: UUID | null;
}

/** L2 payload — mirror of FeatureSnapshot. */
export interface FeaturePacket {
  userId: UUID;
  timestamp: ISODateTime;
  modality: string;
  source: string;
  payload: Record<string, unknown>;
  intent: Intent;
  confidence?: number | null;
  durationMs?: number | null;
  metaContextHint?: string | null;
  iModelId?: UUID | null;
}

export interface AxisEstimate {
  axis: string;
  value: Record<string, unknown>;
  timestamp: ISODateTime;
  confidence: number | null;
  source: string;
  metaContext?: string | null;
  iModelId?: UUID | null;
  freshForSeconds: number;
}

export interface BeliefState {
  userId: UUID;
  estimates: Record<string, AxisEstimate>;
}

export interface Prediction {
  userId: UUID;
  axis: string;
  madeAt: ISODateTime;
  horizonSeconds: number;
  distribution: Record<string, unknown>;
  modelId: string;
  confidence?: number | null;
  action?: Record<string, unknown> | null;
  provenance: "placeholder" | "calibrated";
  coldStart: boolean;
  iModelId?: UUID | null;
}

export interface ActionDecision {
  userId: UUID;
  decidedAt: ISODateTime;
  action: "interject" | "hold";
  rationale: string;
  mode?: "witness" | "companion" | null;
  contentKind?: string | null;
  gateTrace: Record<string, unknown>;
  iModelId?: UUID | null;
}

export interface OutputDirective {
  userId: UUID;
  createdAt: ISODateTime;
  channel: "voice" | "haptic" | "visual";
  mode?: "witness" | "companion" | null;
  text?: string | null;
  delivery: Record<string, unknown>;
  iModelId?: UUID | null;
}

export type Payload =
  | SignalPacket | FeaturePacket | BeliefState | Prediction
  | ActionDecision | OutputDirective;

export interface MessageEnvelope {
  id: UUID;
  type: PayloadType;
  schemaVersion: number;
  sourceRole: NodeRole;
  targetRole?: NodeRole | null;
  occurredAt: ISODateTime;
  metaContext: MetaContext;
  consentScope: string;
  traceId: UUID;
  iModelId?: UUID | null;
  payload: Payload;
}
```

- [ ] **Step 4: Export it from the package index**

Add this line to `packages/shared/src/index.ts` (after the existing exports):

```typescript
export * from "./protocol";
```

- [ ] **Step 5: Verify tsc compiles**

Run: `npx tsc --noEmit -p "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/packages/shared"`
Expected: PASS (no output, exit 0)

- [ ] **Step 6: Commit**

```bash
git add packages/shared/src/protocol.ts packages/shared/src/index.ts packages/shared/src/types.ts
git commit -m "feat(shared): TS mirror of the message protocol + fix duplicate IModelID import"
```

---

### Task 9: Full Core verification + STATUS.md update

**Files:**
- Modify: `docs/STATUS.md` (prepend a dated entry; do not create new docs)

- [ ] **Step 1: Run the whole Core suite + type checks**

Run (from `apps/inference`, venv active):
```bash
python -m pytest core/ -v
```
Expected: PASS — all of: test_enums (3), test_payloads (6), test_envelope (3), bus/test_transport (3), bus/test_bus (3), test_nodes (4), smoke_test (1).

Run: `python -m core.smoke_test`
Expected: `reflex arc OK — trace <uuid> reached L6 (voice, mode=companion)`

Run: `npx tsc --noEmit -p "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/packages/shared"`
Expected: exit 0.

- [ ] **Step 2: Confirm the existing suite still passes (no regressions)**

Run (from `apps/inference`):
```bash
python -m pytest audio_context/test_privacy.py audio_context/test_speaker_id.py audio_context/test_ambient.py features/ fusion/ test_consent.py -q
```
Expected: PASS (same count as before — Core added code, touched no existing module).

- [ ] **Step 3: Prepend a dated STATUS.md entry**

Add at the top of `docs/STATUS.md` (under the title line), keeping it to one tight block:

```markdown
## 2026-05-28 — Nervous-system Core (protocol + bus + node roles)

**Shipped (branch `feat/nervous-system-skeleton`):**
- `apps/inference/core/protocol/` — `MessageEnvelope` + 6 payloads (`SignalPacket`, `FeaturePacket`=`FeatureSnapshot`, `BeliefState`, `Prediction`, `ActionDecision`, `OutputDirective`) as dataclasses; enums for NodeRole / MetaContext / Modality / Intent / PayloadType; JSON wire-codec.
- `apps/inference/core/bus/` — `MessageBus` over a `Transport` seam (`InProcessTransport` today; NetworkTransport later). Six per-boundary topics.
- `apps/inference/core/nodes.py` — node-role placement map (Wisp/phone/desktop/cloud).
- `apps/inference/core/smoke_test.py` — **one command runs a single `trace_id` end-to-end L1→L6** through the bus (stub handlers). `python -m core.smoke_test`.
- `packages/shared/src/protocol.ts` — TS mirror; fixed a pre-existing duplicate-import `tsc` break in `types.ts`.
- **Verified:** full `core/` suite green; existing suite unchanged (no working module touched).

**Next:** the six layer skeletons build against this frozen protocol (separate plans), wrapping existing code (voice loop → L1+L6, composer → L6 renderer, 3 fusion axes → L3 registry) or dropping protocol-speaking stubs. Per `docs/superpowers/specs/2026-05-28-daybook-nervous-system-skeleton-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add docs/STATUS.md
git commit -m "docs(status): nervous-system Core shipped — protocol + bus + node roles, reflex arc green"
```

---

## Self-Review

**Spec coverage** (against `2026-05-28-daybook-nervous-system-skeleton-design.md`):
- §3a Protocol (envelope + 6 payloads + enums) → Tasks 1–3. ✓
- §3b Bus + Transport seam → Tasks 4–5. ✓
- §3c Node roles → Task 6. ✓
- §3d Layer skeletons → **deferred to follow-on plans** (this plan is Core only; stubs in the smoke prove the contract). Stated in Scope. ✓
- §3 wire format = dataclasses → JSON → Tasks 2–3 (`to_dict`), JSON-serializability tested. ✓
- §4 file structure (`core/protocol`, `core/bus`, `core/nodes.py`) → Tasks 1–6. ✓
- §6 commitments at contract level: #1 `i_model_id` on every payload+envelope, #3 voice channel, #10 modality+intent on `SignalPacket`, #11 `consent_scope` on envelope, #14 `meta_context` on envelope, #16 `action` on `Prediction` → Tasks 2–3. ✓
- §7 DoD #1 type-checks/compiles → Tasks 8–9; #2 one-command L1→L6 → Task 7; #3 smoke per layer → Core smoke (per-layer smokes come with the layer plans); #4 TS mirror → Task 8; #5 STATUS update → Task 9. ✓
- §8 deferred (NetworkTransport, versioning machinery, full `from_dict`, layer fills) → explicit in Scope. ✓

**Placeholder scan:** none — every step has complete file content or an exact command. Task 7 Step 3 deliberately has no new code (the arc reuses Tasks 1–6); that is a correctness note, not a placeholder.

**Type consistency:** `MessageEnvelope` constructor args, payload field names (`made_at`, `decided_at`, `created_at`, `gate_trace`, `delivery`), topic constants, `role_for`, and `payload_to_dict(ptype, payload)` are used identically across Tasks 3–9. `FeaturePacket` is an alias of `FeatureSnapshot` throughout. TS field names are camelCase mirrors (documented in the file header).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-28-nervous-system-core.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
