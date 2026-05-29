# NetworkTransport design — distributed L1–L6 bus over WebSocket

Date: 2026-05-29
Status: design (implementation-ready)
Branch context: feat/fill-l6-composer (this spec lands its own branch)

## Goal

Let a second process put a `MessageEnvelope` onto the laptop's bus and receive
directives back, so the L1–L6 bus transparently spans two processes. This is the
keystone of the distributed waking-MVP: **MacBook = inference hub** (WebSocket
server), **Pi/ESP32 (or a second local process) = sensor satellites** (WebSocket
clients). Layers never learn the difference — `NetworkTransport` implements the
existing `Transport` ABC unchanged.

Net effect to prove: a `SignalPacket` published on `TOPIC_SIGNAL` on the
satellite fires the hub's `TOPIC_SIGNAL` handler (signals up), and an
`OutputDirective` published on `TOPIC_OUTPUT` on the hub fires the satellite's
`TOPIC_OUTPUT` handler (directives down) — `trace_id` preserved end to end.

## Frozen contracts this builds against (verified, do not change)

- `Transport` ABC: `register(topic: str, handler: Handler) -> None` +
  `send(topic: str, env: MessageEnvelope) -> None`; `Handler = Callable[[MessageEnvelope], None]` (sync). `InProcessTransport.send` calls each handler inline over a snapshot of the list.
- `MessageBus` wraps a `Transport`; `subscribe`→`register`, `publish`→`send`. Six topics: `TOPIC_SIGNAL=l1.signal`, `TOPIC_FEATURE=l2.feature`, `TOPIC_BELIEF=l3.belief`, `TOPIC_PREDICTION=l4.prediction`, `TOPIC_ACTION=l5.action`, `TOPIC_OUTPUT=l6.output`.
- `MessageEnvelope.to_dict()` emits: `id, type(.value), schema_version, source_role(.value), target_role(.value|None), occurred_at(.isoformat()), meta_context(.value), consent_scope, trace_id, i_model_id, payload(payload_to_dict(type, payload))`. `__post_init__` rejects naive `occurred_at`.
- `codec.payload_to_dict(ptype, payload)`: `BELIEF` → `_belief_to_dict` (explicit, so `fusion/` stays untouched); everything else → `payload.to_dict()`.
- Enums (all `str`-valued): `PayloadType{signal,feature,belief,prediction,action,output}`, `NodeRole{wisp_edge,phone_relay,desktop_compute,cloud}`, `MetaContext{waking,sleep,unknown}`, `Modality`, `Intent`.
- Payload dataclasses + tz-aware fields: `SignalPacket.timestamp`, `FeatureSnapshot.timestamp` (aka `FeaturePacket`), `AxisEstimate.timestamp`, `Prediction.made_at`, `ActionDecision.decided_at`, `OutputDirective.created_at`. `BeliefState{user_id, estimates: dict[str, AxisEstimate]}`.
- Auth convention (`apps/api/auth.py`): env var **`DAYBOOK_API_KEY`** (in `apps/inference/.env.local`, gitignored), header **`X-API-Key`**.
- CI (`.github/workflows/ci.yml`): `python -m pytest core sensors features fusion prediction decision output -q` from `apps/inference`, **no DATABASE_URL**, base deps only (no `[voice]`). `pytest` + `pytest-asyncio` are in `[dev]`. **`websockets>=12.0` is already a base dependency (installed: 16.0).** No pyproject change is required; verify the venv has it and keep the dep line. Tests must live under `core/` to be collected, and must not touch the network or DB.

## Constraints (locked)

- Do NOT modify any L1–L6 layer code (`features/`, `fusion/`, `prediction/`, `decision/`, `output/`, `sensors/`). New code only: inverse codec in `core/protocol/`, `NetworkTransport` + server/client in `core/bus/`, tests, (dep already present).
- `core` must stay **import-safe without a live network and without DATABASE_URL**. The server is started explicitly, never at import. The new inverse-codec module must NOT import `db` (it imports only `fusion.belief_state`, `features.snapshot`, `core.protocol.*` — all DB-free). Add the new codec module to `core/test_import_purity.py::CORE_MODULES` and to the clean-env import list so the DB-free property is regression-guarded.
- Style: `from __future__ import annotations`, full type hints, one-line docstrings, no needless comments. Mirror existing files.
- YAGNI: exactly one peer (2 nodes). No broker, no multi-peer fan-out, no TLS, no topic-subscription negotiation, no message replay/ack/queue persistence.

---

## 1. Inverse codec — `core/protocol/decode.py` (the keystone primitive)

New module `core/protocol/decode.py` (sibling of `codec.py`; keeping the inverse
in its own file leaves the frozen `codec.py` untouched and import-light).
Exposes `envelope_from_dict` + per-payload decoders + `parse_utc`.

### tz-aware datetime parsing

```python
def parse_utc(s: str) -> datetime:
    """Parse an ISO-8601 string to a tz-aware UTC datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"timestamp is not tz-aware: {s!r}")
    return dt.astimezone(timezone.utc)
```

`datetime.fromisoformat` (Py 3.11+) round-trips `.isoformat()` output including
offsets and `+00:00`. Normalizing to UTC keeps the dataclass `__post_init__`
invariant (tz-aware) satisfied and makes round-trip equality exact for UTC inputs
(all our producers emit `datetime.now(timezone.utc)`).

### enum rebuild

Enums are `str`-valued, so `PayloadType(d["type"])`, `NodeRole(...)`,
`MetaContext(...)` reconstruct directly from the stored `.value`. `target_role`
is `None`-safe: `NodeRole(v) if v is not None else None`. Unknown values raise
`ValueError` (caught by the receive loop as a malformed message — see §5).

### per-payload decoders (inverse of each `to_dict`)

One function per `PayloadType`, dispatched by a `dict` keyed on the enum:

- `signal_from_dict` → `SignalPacket(**d, timestamp=parse_utc(d["timestamp"]))` — keep `modality`/`intent`/`kind` as the stored strings (the dataclass stores them as `str`, not enums; no enum rebuild needed there).
- `feature_from_dict` → `FeatureSnapshot(**d, timestamp=parse_utc(...))` (covers `FeaturePacket`, the alias).
- `prediction_from_dict` → `Prediction(**d, made_at=parse_utc(d["made_at"]))`. `provenance` stays a plain string (`Literal` is annotation-only at runtime).
- `action_from_dict` → `ActionDecision(**d, decided_at=parse_utc(...))`.
- `output_from_dict` → `OutputDirective(**d, created_at=parse_utc(...))`.
- `belief_from_dict` → invert `codec._belief_to_dict`: rebuild each `AxisEstimate` from its dict (`timestamp=parse_utc(...)`, all other fields verbatim), then `BeliefState(user_id=..., estimates={ax: AxisEstimate(...)})`. **Invert `_belief_to_dict`, NOT `BeliefState.snapshot()`** — `snapshot()` is lossy (drops `axis`, `i_model_id`, `fresh_for_seconds`, filters stale axes). The wire form is the full `_belief_to_dict` shape.

Each decoder reconstructs by explicit kwargs (not blind `**d`) where a field needs
transformation, to stay robust to extra/unknown keys and to keep the timestamp
transform visible. Naive reconstruction validation is inherited free: every
payload's `__post_init__` re-runs and re-enforces the tz-aware + confidence-range
invariants on decode.

### envelope decoder

```python
def envelope_from_dict(d: dict) -> MessageEnvelope:
    ptype = PayloadType(d["type"])
    payload = _PAYLOAD_DECODERS[ptype](d["payload"])
    return MessageEnvelope(
        id=d["id"], type=ptype,
        source_role=NodeRole(d["source_role"]),
        occurred_at=parse_utc(d["occurred_at"]),
        meta_context=MetaContext(d["meta_context"]),
        consent_scope=d["consent_scope"], trace_id=d["trace_id"],
        payload=payload,
        schema_version=d.get("schema_version", 1),
        target_role=NodeRole(d["target_role"]) if d.get("target_role") else None,
        i_model_id=d.get("i_model_id"),
    )
```

### round-trip guarantee

For every payload type and the envelope:
`x == envelope_from_dict(json.loads(json.dumps(env.to_dict())))`. Dataclass `==`
is field-wise; UTC-normalized timestamps compare equal; enums compare equal;
nested `BeliefState`/`AxisEstimate` compare equal (both plain dataclasses).
`schema_version` mismatch is out of scope for v1 (single version=1); decoder
reads it through but does not branch on it.

---

## 2. `NetworkTransport` — `core/bus/network.py`

Implements the `Transport` ABC unchanged. Composes (does not subclass)
`InProcessTransport` for the local-delivery half + a single peer link for the
remote half.

```python
class NetworkTransport(Transport):
    def __init__(self, link: PeerLink) -> None:
        self._local = InProcessTransport()
        self._link = link

    def register(self, topic, handler) -> None:
        self._local.register(topic, handler)   # delegate verbatim

    def send(self, topic, env) -> None:
        self._local.send(topic, env)            # (1) inline local delivery
        self._link.send_remote(topic, env)      # (2) enqueue to peer; non-blocking
```

`register` is pure delegation → the ABC's local-delivery contract is identical to
`InProcessTransport` (proven by reusing its tests, §6). `send` does the two
halves in order: **local first, inline**, exactly like `InProcessTransport`
(handlers run synchronously, errors-contained per §5); **then** `send_remote`
which only *enqueues* onto the asyncio loop and returns immediately — `send()`
never blocks on the network.

`PeerLink` is the receive→dispatch bridge: when the loop receives a wire message
from the peer it calls `self._local.send(topic, decoded_env)` — i.e. the remote
peer's publish dispatches to *this* node's locally-registered handlers for that
topic. Same code path as a local publish, so receive is symmetric with send.

Topic forwarding is **general** (`send_remote(topic, env)` forwards any topic);
nothing is hardcoded per-topic. Signals-up (`TOPIC_SIGNAL` satellite→hub) and
directives-down (`TOPIC_OUTPUT` hub→satellite) are just two instances of the
same forward.

**Loopback-avoidance:** when a node receives a remote envelope and dispatches it
to local handlers, it must NOT re-forward it back over the link (that would echo
infinitely). The inbound path calls `self._local.send(...)` **directly**, never
`NetworkTransport.send(...)`, so the remote-forward half is structurally
bypassed on receive. This is the single most important correctness invariant.

---

## 3. Hub server + satellite client + background-thread asyncio model

### `PeerLink` abstraction (`core/bus/network.py`)

A `PeerLink` owns: the background thread running an asyncio event loop, the
current peer WebSocket (one peer, may be `None` when disconnected), a thread-safe
`send_remote`, and an `on_message(topic, env)` callback (wired by
`NetworkTransport` to `self._local.send`). Two concrete subclasses:

- **`HubLink`** (laptop): starts a `websockets` server bound to `host:port`
  (LAN, default `0.0.0.0:8787`). Accepts one satellite connection; authenticates
  it; holds the connection; reads frames → `on_message`. Writes frames from the
  send queue.
- **`SatelliteLink`** (Pi/ESP32/2nd process): connects out to
  `ws://<hub-host>:<port>`, sends auth on connect, then read/write loops; on drop,
  reconnects with backoff.

Wire frame (one JSON object per WebSocket text message):
`{"topic": "<topic>", "env": <envelope.to_dict()>}`. Receive: parse JSON →
`topic = msg["topic"]`, `env = envelope_from_dict(msg["env"])` → `on_message`.

### background-thread asyncio model

The event loop runs in a **daemon background thread**, created explicitly by
`start()` — **never at import** (keeps `core` import-safe with no network):

```python
def start(self) -> None:
    self._loop = asyncio.new_event_loop()
    self._thread = threading.Thread(target=self._run_loop, daemon=True)
    self._thread.start()
    self._ready.wait(timeout=...)   # threading.Event set once server/connection is up

def _run_loop(self) -> None:
    asyncio.set_event_loop(self._loop)
    self._loop.run_until_complete(self._serve_or_connect())  # sets self._ready
    self._loop.run_forever()
```

Inbound frames arrive on the loop thread; the loop calls the registered **sync**
handlers (via `on_message` → `self._local.send` → handler). Handlers therefore
run on the background thread — documented; for v1 the hub's L2–L6 participants are
synchronous and side-effect-local, which is fine. (If a handler needs the main
thread later, the seam is `on_message`; out of scope now.)

### thread-safe `send_remote` (non-blocking for the caller)

App code calls `send()` on its own thread (e.g. the satellite's L1 emit thread).
`send_remote` must hand the frame to the loop without blocking on I/O:

```python
def send_remote(self, topic, env) -> None:
    if self._loop is None:
        return                      # link not started → no-op (local delivery already happened)
    frame = json.dumps({"topic": topic, "env": env.to_dict()})
    self._loop.call_soon_threadsafe(self._enqueue, frame)
```

`_enqueue` puts the frame on an `asyncio.Queue` that the writer coroutine drains
and `await ws.send(frame)`s. `call_soon_threadsafe` is the documented thread→loop
bridge; it returns immediately, so `send()` never blocks on the socket. If the
peer is down the frame is dropped (or bounded-buffered, §5) — local delivery has
already happened regardless, satisfying "send() must not block on the network for
the local-delivery half."

### `websockets` API note (installed v16.0)

Use the modern asyncio API: `from websockets.asyncio.server import serve` and
`from websockets.asyncio.client import connect`. (Legacy `websockets.serve`
still works but is deprecated in 16.x.) Server handler signature: `async def
handler(ws)`. Read frames via `async for message in ws`.

### connect / auth / reconnect

- **Auth**: shared key. The satellite sends the key on connect; reuse the
  `X-API-Key` convention. Two equivalent placements — pick the WS-idiomatic one:
  (a) HTTP header `X-API-Key: <key>` on the client handshake (`connect(uri,
  additional_headers={"X-API-Key": key})`), validated server-side in a
  `process_request`/handshake hook; or (b) first WS frame `{"type":"auth","key":
  ...}` validated before any envelope is accepted. **Choose (a)** — it matches
  `apps/api/auth.py` exactly (same header name) and rejects pre-handshake. Key is
  read from env `DAYBOOK_API_KEY` (via `os.environ`, same as `auth.py`); never
  logged, never printed, never written to the spec/tests. Tests inject a dummy
  key explicitly. LAN-local, **no TLS** in v1 (`ws://`, not `wss://`).
- Server: on a connection whose `X-API-Key` ≠ expected key → reject the handshake
  (HTTP 401-equivalent close); never reach the message loop. If no key is
  configured server-side, fail closed (refuse connections) — mirrors `auth.py`'s
  503 fail-closed posture.
- **Reconnect** (satellite only): on connection drop, retry `connect` with capped
  exponential backoff (e.g. 0.5s → 8s) until `stop()` is called. The hub is
  passive (waits for the satellite to reconnect). Reconnect is satellite-side
  only; YAGNI says no session resumption / no buffered replay across reconnects
  in v1 (frames sent while disconnected are dropped).

### lifecycle

`start()` (idempotent), `stop()` (signal loop to close server/connection, then
`loop.call_soon_threadsafe(loop.stop)`, join thread with timeout). `__enter__`/
`__exit__` for use as a context manager in tests.

---

## 4. Where it plugs into the existing assembly (no layer changes)

`pipeline.assemble_pipeline(bus, ...)` already takes a `MessageBus`. To make the
bus span two processes you build the bus over a `NetworkTransport` instead of the
default `InProcessTransport`:

- **Hub process (Mac):** `link = HubLink(host, port, key); link.start();
  bus = MessageBus(NetworkTransport(link)); assemble_pipeline(bus)`. L2–L6
  participants register their handlers on the bus as today. A `SignalPacket`
  arriving from the satellite over the wire is dispatched to the L2 handler the
  same as a local L1 emit.
- **Satellite process (Pi):** `link = SatelliteLink(hub_uri, key); link.start();
  bus = MessageBus(NetworkTransport(link))`. It registers an L6 `TOPIC_OUTPUT`
  handler (the speak sink) and publishes `SignalPacket`s on `TOPIC_SIGNAL`
  (sensors emit). Publishing on `TOPIC_SIGNAL` locally has no local subscriber on
  the satellite, so it just forwards to the hub — correct.

`nodes.PLACEMENT` already encodes the destination roles (L1/L2/L6 → `WISP_EDGE`,
L3/L4/L5 → `DESKTOP_COMPUTE`); `NetworkTransport` is the mechanism that realizes
that split across processes. No change to `pipeline.py` is required for v1 (the
seam is the `transport=` arg to `MessageBus`); an optional thin
`core/bus/distributed.py` helper that constructs hub/satellite buses can be added
but is not required by this spec.

---

## 5. Error handling

- **Dropped connection:** read loop catches `ConnectionClosed` → satellite enters
  reconnect/backoff; hub clears its peer ref and returns to accepting. `send_remote`
  while disconnected is a no-op/bounded-drop (local delivery unaffected).
- **Malformed message:** any exception in JSON parse / `envelope_from_dict` /
  enum rebuild / `parse_utc` is caught in the receive loop, logged (no payload
  contents, no secrets), and the frame is dropped. One bad frame never kills the
  loop or the connection.
- **Handler exceptions contained:** inbound dispatch wraps `on_message` so a
  raising sync handler is caught + logged and does not kill the loop. (Note: the
  frozen `InProcessTransport.send` does NOT swallow handler exceptions; to avoid
  changing that contract or that file, the containment wrapper lives in the
  receive path — `on_message` catches around `self._local.send(...)`. Local
  same-process `send()` keeps `InProcessTransport`'s existing
  raise-through behavior.)
- **send_remote on a stopped/unstarted link:** no-op (guard on `self._loop is
  None`). Local delivery still happened.
- **Backpressure:** bounded `asyncio.Queue` (e.g. maxsize ~1000); on overflow drop
  oldest with a warn-once. v1 traffic (HR every 30s, speech finals) is far under
  this; YAGNI on anything fancier.

---

## 6. Test plan (all under `core/`, network- and DB-free, runs in CI's pytest line)

CI command is `python -m pytest core sensors features fusion prediction decision
output -q` with no DATABASE_URL — every test below lives under `core/` and uses
only an in-test loopback WebSocket on `127.0.0.1` (no external network, no DB, no
audio, no LLM). `pytest-asyncio` is available (in `[dev]`).

**A. Round-trip codec — `core/protocol/test_decode.py`** (pure, no sockets)
- For each payload type (`SignalPacket`, `FeatureSnapshot`/`FeaturePacket`,
  `BeliefState` with ≥2 `AxisEstimate`s, `Prediction`, `ActionDecision`,
  `OutputDirective`): build it, wrap in a `MessageEnvelope`, assert
  `envelope_from_dict(json.loads(json.dumps(env.to_dict()))) == env`.
- `parse_utc` parses `.isoformat()` output to a tz-aware UTC datetime; rejects a
  naive string with `ValueError`.
- Enum rebuild: a tampered `type`/`source_role`/`meta_context` value raises
  `ValueError` (malformed-frame guard).
- `BeliefState` round-trip preserves `i_model_id`, `fresh_for_seconds`, `axis`
  (regression that the inverse uses `_belief_to_dict`, not lossy `snapshot()`).
- Decode re-enforces invariants: a dict with a naive timestamp string for a
  payload field raises on reconstruction (via the payload `__post_init__`).

**B. Two-endpoint in-test relay — `core/bus/test_network.py`** (the keystone proof)
- Spin up a `HubLink` on `127.0.0.1:<ephemeral port>` and a `SatelliteLink`
  connecting to it, both with the same dummy key, inside the test (context
  managers; `stop()` in teardown). Build a `MessageBus(NetworkTransport(link))`
  on each.
- **Signals up:** register a recording handler on the hub bus for `TOPIC_SIGNAL`;
  `satellite_bus.publish(TOPIC_SIGNAL, env)`; poll until the hub handler fires
  (timeout ~2s). Assert it received a `SignalPacket` envelope with the **same
  `trace_id`** and equal payload fields (decoded == original).
- **Local half is synchronous:** also register a handler on the *satellite* bus
  for `TOPIC_SIGNAL`; assert it fired **inline during `publish`** (before any
  await), proving `send()` delivers locally without blocking on the network.
- **Directives down:** register a recording handler on the satellite bus for
  `TOPIC_OUTPUT`; `hub_bus.publish(TOPIC_OUTPUT, output_env)`; poll until the
  satellite handler fires; assert `trace_id` preserved and `OutputDirective`
  fields equal. Proves bidirectional, general (not per-topic-hardcoded) forwarding.
- **No echo / no infinite loop:** publishing on the hub for a topic the hub also
  subscribes to does not bounce back from the satellite (assert handler count == 1).
- **Auth reject:** a `SatelliteLink` with a wrong key fails to establish (handshake
  rejected); hub handler never fires.
- **Malformed frame contained:** feed a non-JSON / bad-enum frame to the receive
  path (e.g. via a small helper that injects a raw frame); assert the loop stays
  alive and a subsequent valid frame still delivers.
- **Handler exception contained (remote path):** a hub `TOPIC_SIGNAL` handler that
  raises does not kill the loop; a second well-behaved handler still receives, and
  the connection stays up for a subsequent publish.
- **Reconnect:** stop the hub, restart it, assert the satellite re-establishes and
  a post-reconnect publish is delivered (small, bounded-timeout; keep it fast).

**C. Transport ABC contract — `core/bus/test_network.py`** (reuse the frozen behavior)
- Parametrize/duplicate the three `test_transport.py` cases against
  `NetworkTransport(NullLink())` where `NullLink.send_remote` is a no-op: a
  registered handler receives the sent envelope; send to an unsubscribed topic is
  a no-op; multiple handlers all receive. Proves `register`/`send`'s **local** half
  is behaviorally identical to `InProcessTransport` (the ABC contract layers rely
  on). `NullLink` keeps this case network-free and instant.

**D. Import purity — extend `core/test_import_purity.py`**
- Add `core.protocol.decode`, `core.bus.network` to `CORE_MODULES` so the clean-env
  subprocess import test guards that the inverse codec + transport import with no
  DATABASE_URL and pull no `db` into the graph. (`core.bus.network` imports
  `websockets` lazily inside `start()`/server-coroutine, or at module top only if
  that stays DB-free — `websockets` is DB-free, so a top-level import is fine; the
  guard is specifically about `db`/DATABASE_URL, which neither module touches.)

---

## 7. File manifest (new + edited)

New:
- `core/protocol/decode.py` — inverse codec (`parse_utc`, per-payload decoders, `envelope_from_dict`).
- `core/bus/network.py` — `NetworkTransport`, `PeerLink`, `HubLink`, `SatelliteLink`, (`NullLink` test aid may live in the test file instead).
- `core/protocol/test_decode.py` — round-trip + parse + enum-rebuild tests.
- `core/bus/test_network.py` — two-endpoint relay + ABC-contract + error-path tests.

Edited:
- `core/test_import_purity.py` — add the two new modules to the clean-env import list.
- `apps/inference/pyproject.toml` — **no change needed** (`websockets>=12.0` already present); confirm it stays.

Not touched: any `features/`, `fusion/`, `prediction/`, `decision/`, `output/`,
`sensors/` file; `core/protocol/codec.py`; `core/protocol/envelope.py`;
`core/bus/transport.py`; `core/bus/bus.py`; `core/pipeline.py`.

## 8. Explicitly out of scope (YAGNI)

Broker / message queue; >2 peers / fan-out; TLS / `wss://`; topic-subscription
negotiation; per-message ack / delivery guarantees / persistence; cross-reconnect
replay; schema-version negotiation; moving handler execution off the loop thread.
