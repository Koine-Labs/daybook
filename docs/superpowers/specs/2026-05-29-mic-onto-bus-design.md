# Mic onto the Bus — Live Audio Producer Design

**Date:** 2026-05-29
**Goal:** Make the already-built continuous-mic semantic pipeline a LIVE producer on the nervous-system bus, so L3 fusion builds a live `audio_social_context` belief from real mic activity — not only from the orphaned DB-write path. This is the strongest waking sense and today it never touches the spine.

**Status of this doc:** implementation-ready. Every claim below was verified by reading the source on `feat/fill-l6-composer`, not docs.

---

## 0. Verified ground truth (what actually exists today)

### 0.1 The frozen protocol (MUST NOT change)
- `core/protocol/payloads.py` — `SignalPacket` (L1→L2): `user_id, timestamp(tz-aware UTC), modality, intent, kind, payload:dict, source, confidence, i_model_id`. `__post_init__` rejects naive timestamps and out-of-range confidence. Semantic-first (#11): "only meaningful extractions ride here, never raw bytes."
- `core/protocol/enums.py` — `Modality.AUDIO = "audio"`, `Modality.VOICE = "voice"`, `Intent.CONTINUOUS = "continuous"`, `Intent.EXPLICIT = "explicit"`. `MetaContext.{WAKING,SLEEP,UNKNOWN}`. `PayloadType.{SIGNAL,FEATURE,...}`.
- `core/bus/bus.py` — six topics; `TOPIC_SIGNAL="l1.signal"`, `TOPIC_FEATURE="l2.feature"`, `TOPIC_BELIEF="l3.belief"`. `MessageBus.publish/subscribe` over a pluggable `Transport`.
- `core/bus/transport.py` — `Transport` ABC (`register`, `send`); `InProcessTransport` is synchronous inline delivery. `NetworkTransport` lives in `core/bus/network.py`. **The producer must take a `MessageBus` and never name a transport** → transport-agnostic for free (mic-on-Mac in-process today; mic-on-Pi over `NetworkTransport` later, no code change).
- `core/layer.py` `forward_envelope(...)` — inherits `trace_id / meta_context / consent_scope / i_model_id` from an inbound envelope. **L1 has no inbound envelope** (it is the entry point), so L1 builds the envelope directly (see `sensors/participant.py`).

### 0.2 The L1 producer pattern (`sensors/`)
- `sensors/contract.py` — `IntentTaggedReading` (modality + intent + kind + payload + source + ts + confidence + user_id + i_model_id). Validates tz-aware ts, known modality, known intent, confidence∈[0,1]. `.to_signal_packet()` converts to `SignalPacket`.
- `sensors/participant.py` — `emit(bus, reading, *, meta_context=UNKNOWN)` → builds an L1 `MessageEnvelope` (fresh `id`, fresh `trace_id`, `source_role=WISP_EDGE`, `occurred_at=now`, `consent_scope=consent_scope_for(reading)`) and publishes on `TOPIC_SIGNAL`. `consent_scope_for`: `mac.*` source → `CONSENT_SCOPES["mac"]`; else by modality — **`Modality.AUDIO` and `Modality.VOICE` both map to `CONSENT_SCOPES["voice"] = "mic_continuous_v1"`** (verified in `_MODALITY_CONSENT`).
- `sensors/mac_adapter.py` — the precedent: a thin adapter that wraps an existing capture function (`capture.mac_sensors.capture_once`) and re-tags it as an `IntentTaggedReading`. **Our audio producer is the same shape, one layer richer** (it fans one window into 1–3 readings under the privacy gate).

### 0.3 The L2 extractor REGISTRY (`features/`)
- `features/participant.py` — subscribes `TOPIC_SIGNAL`, runs `extract(sig)` = `select_extractor(sig.modality)(sig)`, publishes `FeatureSnapshot` on `TOPIC_FEATURE` via `forward_envelope`. `EXTRACTORS: dict[str,Extractor]` maps modality→extractor. **Today `"audio"` → `_stub_passthrough_extractor`** (wraps `sig.payload` under `payload={"kind","features","extractor":"stub_passthrough"}`). `"biometric"` → the real `features.biometric.extract`. Unregistered modality → `_offline_extractor` (OFFLINE sentinel, `confidence=None`).
- `features/biometric.py` — the precedent for a *real* extractor: `extract(sig)->FeatureSnapshot` with a structured `payload` (`kind, extractor tag, feature_cols, features, vector, ...`). It reuses canonical math, never reimplements. **Our audio extractor follows this contract: structured semantic payload + an `extractor` provenance tag.**
- `features/snapshot.py` — `FeatureSnapshot`: `user_id, timestamp, modality, source, payload, intent="continuous", confidence, duration_ms, meta_context_hint, i_model_id`. `Extractor = Callable[[SignalPacket], FeatureSnapshot]`.

### 0.4 The L3 axis + fusion (`fusion/`)
- `fusion/axes/audio_social_context.py` — `AXIS="audio_social_context"`, `fuse_recent(*, user_id, now=None, window_seconds=300)`: **reads `sensor_readings` via `db.get_conn`**, takes latest `kind='audio_social_context'` row in window, maps `payload["speaker"]` → `category` (`with_other` if speaker∈{other,both}, else `alone`), returns `AxisEstimate(value={"category":...}, confidence=0.8, fresh_for_seconds=300)`. **This is the DB path. It imports `db` at module level** (via `from db import get_conn` inside the module body, after sys.path insert).
- `fusion/participant.py` — `AXIS_REGISTRY` wraps each axis's `fuse_recent` in `_wrap_fuse_recent`, which calls `fuse_recent(user_id=packet.user_id, now=now)` and **swallows any exception into an OFFLINE estimate** (so a missing DB never crashes the bus). `FusionParticipant.fuse(packet, now)` runs **every** registered axis against the inbound `FeatureSnapshot` and updates a per-user `BeliefState`. Critically: **axes currently ignore the packet payload entirely** — the packet only supplies `user_id + now`; the answer comes from the DB. `register(bus, participant=...)` subscribes `handle` to `TOPIC_FEATURE`.
- `fusion/belief_state.py` — `BeliefState.update(est)` / `.get(axis, now)` (freshness-gated) / `.snapshot(now)`. `AxisEstimate.is_fresh` uses `fresh_for_seconds`.

### 0.5 The audio semantic extractors + privacy gate (`audio_context/`) — REUSE, do not reimplement
- `audio_context/processor.py` — `process_audio_chunk(audio, sr, started_at)->AudioContextPacket` runs VAD→diarization→prosody; pure, no DB.
- `audio_context/vad.py`, `diarization.py`, `prosody.py`, `speaker_id.py`, `ambient.py` — the heavy extractors. **All heavy deps (torch/silero/resemblyzer/librosa/tensorflow) are lazy-imported inside functions** — verified: importing these modules' *callers* does not pull torch.
- `audio_context/privacy.py` — **`PrivacyGate`** (pure, no deps). `evaluate(*, speakers, now)->GateDecision`. Logic verified: `_classify` treats `"unknown"` as `"other"` (fail-safe, #1); `other`/`both` arm a `buffer_seconds` (default 30s) suppression deadline; `allow_prosody` only when `social=="self"` and not suppressed; `allow_ambient`/`allow_stt` when `social∈{self,none}` and not suppressed. `GateDecision` carries `social_context, allow_prosody, allow_ambient, allow_stt, suppressed_until`.
- `audio_context/writer.py` — the DB sink. Three kinds: `write_social_context(...kind='audio_social_context', payload={speaker,num_speakers,vad_active})`, `write_prosody(...kind='audio_prosody')`, `write_ambient(...kind='audio_ambient')`. Stamps `source="mic_listener_v1"`, `consent_scope=CONSENT_SCOPES["voice"]`.

### 0.6 The always-on loop + the reusable orchestrator (`voice/`)
- `voice/continuous.py` — **`ContinuousProcessor`**: pure orchestration with *injectable* I/O. Constructor takes `identify_speakers, prosody_of, ambient_of, write_social, write_prosody, write_ambient` (all callables) + `buffer_seconds`. It owns a `PrivacyGate`. `process_window(audio, sr, *, vad_active, now)`:
  1. `speakers = identify_speakers(audio,sr) if vad_active else []`
  2. `decision = self.gate.evaluate(speakers=speakers, now=now)`
  3. **always** `write_social(user_id, recorded_at=now, speaker=decision.social_context, num_speakers=len(set(speakers)), vad_active=vad_active)` — the presence marker.
  4. iff `decision.allow_prosody and vad_active`: `write_prosody(user_id, recorded_at, prosody=prosody_of(...))`
  5. iff `decision.allow_ambient and not vad_active`: `write_ambient(...)` (only if classes non-empty)
  - **Only `audio_context.privacy` is imported at module level — no torch.** Verified: `voice.continuous` imports in a CI-faithful env (no DATABASE_URL, no torch, no db).
- `voice/loop.py` `listen_continuous(...)` — the real mic loop: builds the heavy `identify_speakers/prosody_of/ambient_of` closures and the DB `write_*` functions, constructs a `ContinuousProcessor`, reads `sounddevice` blocks, and calls `proc.process_window(...)`. **This is where we add the bus wiring** (see §2.4).

### 0.7 The pipeline + CI (the green-bar constraints)
- `core/pipeline.py` `assemble_pipeline(bus, ...)` registers L2–L6; **L1 emits separately**. No change required for this work, but the producer composes onto the same bus.
- **CI command (`.github/workflows/ci.yml`), run from `apps/inference`, with NO `DATABASE_URL`, lean deps only (NO `[voice]`/`[ambient]` extras → no torch/silero/resemblyzer/librosa/tensorflow/sounddevice):**
  ```
  python -m pytest core sensors features fusion prediction decision output -q
  ```
  Baseline verified green: **139 passed**.
  - **Hard consequence:** every new module imported by `sensors/`, `features/`, or `fusion/` test collection MUST import cleanly with no torch and no DATABASE_URL. `numpy`/`pandas` ARE present. `voice.continuous`, `audio_context.privacy`, `audio_context.writer` (import-only; it lazy-uses db) are all clean — verified. `audio_context.vad/diarization/prosody/speaker_id/ambient` are NOT clean to *call* but ARE clean to *import* (heavy deps are lazy). The producer must only IMPORT the clean surface and INJECT the heavy callables (exactly the `ContinuousProcessor` pattern).
  - `apps/voice/` is reachable from `apps/inference` cwd by adding the parent (`apps/`) to `sys.path` — verified import works from that cwd.

### 0.8 The orphan, precisely
`listen_continuous` → `ContinuousProcessor` → `write_social/prosody/ambient` → **DB only**. Nothing publishes a `SignalPacket`. `audio_social_context.fuse_recent` reads those DB rows. So L3 *can* answer, but only by polling the DB out-of-band — the live mic never drives the spine, and on a node with no DB write access (future Pi) the sense vanishes. **This work adds a parallel bus emission; the DB path stays exactly as-is.**

---

## 1. Design overview (the arc we are building)

```
mic window ─► ContinuousProcessor (REUSED: privacy gate + injected extractors)
                   │  (we inject BUS-SINK writers instead of / in addition to DB writers)
                   ▼
        AudioBusSink.write_social/prosody/ambient
                   │  builds IntentTaggedReading(modality=AUDIO, intent=CONTINUOUS, kind=...)
                   ▼
        sensors.participant.emit(bus, reading)         ──►  TOPIC_SIGNAL   (L1 SignalPacket)
                   ▼
        features.participant  (audio extractor)         ──►  TOPIC_FEATURE (L2 FeatureSnapshot)
                   ▼
        fusion.participant  (audio_social_context axis)  ──►  TOPIC_BELIEF (L3 BeliefState)
```

Five concrete deliverables:

1. **L1 audio producer** (`sensors/audio_adapter.py`) — maps each privacy-gated semantic emission to an `IntentTaggedReading(modality=AUDIO, intent=CONTINUOUS)` and emits it on the bus. Privacy routing is *inherited* from `ContinuousProcessor`'s gate — we never re-implement #1.
2. **An `AudioBusSink`** (in the same file) — the three writer callables injected into `ContinuousProcessor`, turning each allowed packet into an `emit(...)`. This is what makes the producer transport-agnostic (it only holds a `MessageBus`).
3. **L2 audio extractor** (`features/audio_social.py`) — `SignalPacket(modality=audio) → FeatureSnapshot`, registered for `"audio"` in `features/participant.py` (replacing the passthrough stub for audio). Structured payload mirroring the biometric extractor's shape.
4. **Minimal L3 change** (`fusion/axes/audio_social_context.py`) — let the axis build a live `AxisEstimate` from the **inbound FeatureSnapshot** when one is present, falling back to the existing DB `fuse_recent` otherwise. Keeps the DB path working and all existing tests green.
5. **Tests** under `sensors/`, `features/`, `fusion/` (all on the CI path) proving the full hardware/DB/network-free arc + the privacy suppression behavior.

---

## 2. Component specs

### 2.1 Semantic-kind → SignalPacket mapping (the contract)

Each privacy-gated emission becomes one `SignalPacket`. All three share `modality=Modality.AUDIO.value`, `intent=Intent.CONTINUOUS.value`, `source="mic_listener_v1"` (matches the writer's source string), `user_id`, tz-aware `timestamp=now`. They differ by `kind` + `payload`:

| Emission | SignalPacket.kind | payload (semantic-first, #11 — NEVER raw audio) | When emitted |
|---|---|---|---|
| presence marker | `audio_social_context` | `{"speaker": <self/other/both/none>, "num_speakers": int, "vad_active": bool, "suppressed": bool}` | **always**, every window |
| prosody | `audio_prosody` | the prosody dict (`energy, pitch_mean_hz, pitch_std_hz, speaking_rate_wpm, tone`) | only when gate `allow_prosody and vad_active` |
| ambient | `audio_ambient` | `{"top_classes": [{"class","score"}, ...]}` | only when gate `allow_ambient and not vad_active` and classes non-empty |

`suppressed` in the presence payload = `decision.suppressed_until is not None and now < decision.suppressed_until` — a cheap, honest flag so downstream can see the gate fired without leaking content. (The privacy guarantee does NOT depend on this flag; it depends on prosody/ambient never being emitted while suppressed — which the gate already enforces inside `ContinuousProcessor`.)

**Privacy is load-bearing and is NOT re-implemented here.** Because the bus-sink writers are the same `write_social/write_prosody/write_ambient` callables `ContinuousProcessor` invokes, and `ContinuousProcessor` only calls `write_prosody/write_ambient` when the gate allows, a non-self speaker → only `write_social` is ever called → only the presence-marker `SignalPacket` is ever emitted. Unknown speaker → gate classifies as `other` → suppressed. No new privacy logic exists in the producer; it routes through `audio_context/privacy.py` transitively, exactly as required.

### 2.2 `sensors/audio_adapter.py` (NEW) — the L1 producer

Mirrors `sensors/mac_adapter.py` (thin re-tagging adapter) but for the three audio kinds, and adds the `AudioBusSink` that bridges `ContinuousProcessor`'s writer contract to `emit`.

```python
"""L1 audio producer: privacy-gated mic semantics -> SignalPacket on the bus.

Wraps voice.continuous.ContinuousProcessor (REUSED — VAD/diarization/prosody/
ambient + the Privacy Policy #1 state machine are not reimplemented here). Each
allowed semantic emission becomes an IntentTaggedReading (modality=AUDIO,
intent=CONTINUOUS, #10) and is published via sensors.participant.emit. Semantic-
first (#11): only derived values ride the bus, never raw audio.

Transport-agnostic: holds only a MessageBus, so it works over InProcessTransport
(mic on the Mac today) and NetworkTransport (mic on the Pi later) with no change.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.bus.bus import MessageBus
from core.protocol.enums import Intent, Modality
from sensors.contract import DEFAULT_USER_ID, IntentTaggedReading
from sensors.participant import emit

AUDIO_SOURCE = "mic_listener_v1"          # matches audio_context/writer.SOURCE
KIND_SOCIAL = "audio_social_context"
KIND_PROSODY = "audio_prosody"
KIND_AMBIENT = "audio_ambient"


def _reading(kind: str, payload: dict[str, Any], *, user_id: str, now: datetime) -> IntentTaggedReading:
    return IntentTaggedReading(
        modality=Modality.AUDIO.value,
        intent=Intent.CONTINUOUS.value,
        kind=kind,
        payload=payload,
        source=AUDIO_SOURCE,
        timestamp=now,
        user_id=user_id,
    )


class AudioBusSink:
    """The three writer callables ContinuousProcessor expects, but each emits a
    SignalPacket onto a MessageBus instead of writing the DB."""

    def __init__(self, bus: MessageBus, *, user_id: str = DEFAULT_USER_ID) -> None:
        self.bus = bus
        self.user_id = user_id

    def write_social(self, *, user_id: str, recorded_at: datetime, speaker: str,
                     num_speakers: int, vad_active: bool, suppressed: bool = False) -> None:
        emit(self.bus, _reading(KIND_SOCIAL, {
            "speaker": speaker, "num_speakers": num_speakers,
            "vad_active": vad_active, "suppressed": suppressed,
        }, user_id=user_id, now=recorded_at))

    def write_prosody(self, *, user_id: str, recorded_at: datetime, prosody: dict[str, Any]) -> None:
        emit(self.bus, _reading(KIND_PROSODY, dict(prosody), user_id=user_id, now=recorded_at))

    def write_ambient(self, *, user_id: str, recorded_at: datetime, top_classes: list) -> None:
        emit(self.bus, _reading(KIND_AMBIENT, {"top_classes": list(top_classes)},
                                user_id=user_id, now=recorded_at))
```

**`suppressed` plumbing decision (YAGNI-honest):** `ContinuousProcessor.process_window` currently calls `write_social(... speaker, num_speakers, vad_active)` WITHOUT a `suppressed` kwarg (verified). To avoid touching `ContinuousProcessor`'s signature (it has its own passing tests), `AudioBusSink.write_social` defaults `suppressed=False`. The presence marker is still always emitted and still carries `speaker` ∈ {self,other,both,none}, which is the field the L3 axis actually reads. Adding the real `suppressed` value is a **deferred, optional** follow-up that would add one kwarg to `ContinuousProcessor.process_window`'s `write_social` call (and is harmless because every existing sink ignores it via `**k`). Not needed for the live arc.

### 2.3 Why this is transport-agnostic (constraint satisfied)
`AudioBusSink` holds only a `MessageBus`. `emit` calls `bus.publish(TOPIC_SIGNAL, env)`. `MessageBus` delegates to whatever `Transport` it was constructed with. Therefore the identical producer code runs:
- **Today:** `MessageBus()` → `InProcessTransport` → L2/L3 handlers run inline in the same process as the mic (Mac).
- **Later:** `MessageBus(NetworkTransport(...))` → the `SignalPacket` envelope is serialized (it already has `to_dict()` + the protocol codec) and shipped from the Pi to the compute node. No producer change. We never name a transport in the producer.

### 2.4 `voice/loop.py` wiring (the only `voice/` edit) — optional bus output
Add an optional `bus: MessageBus | None = None` parameter to `listen_continuous(...)`. When provided, construct an `AudioBusSink(bus, user_id=user_id)` and pass ITS methods as the `write_social/write_prosody/write_ambient` callables — **either replacing the DB writers (pure-bus mode) or in addition to them (a tiny fan-out wrapper that calls both).** Default (`bus=None`) keeps today's DB-only behavior byte-for-byte. This file is NOT on the CI path, so its change is not test-gated by CI; it is the production wiring exercised by `voice` smoke tests on a voice-capable node. Keep it minimal: prefer pure-bus when a bus is supplied (the DB row is reconstructable downstream by an L3/persistence sink later); document that choice inline. **No mic, no torch, no DB enters CI through this edit.**

> The producer's *unit tests* never import `voice.loop`; they drive `ContinuousProcessor` + `AudioBusSink` directly (§3), so the heavy mic loop is irrelevant to CI.

### 2.5 `features/audio_social.py` (NEW) — the L2 AUDIO extractor
Mirrors `features/biometric.py`'s real-extractor shape: `extract(sig)->FeatureSnapshot` with a structured, provenance-tagged payload. For `kind='audio_social_context'` it normalizes `speaker → social_category` (the same alone/with_other mapping the L3 DB path uses, lifted to L2 so the live path computes it once). For `audio_prosody`/`audio_ambient` it passes the semantic dict through under a typed key. Pure: numpy not even needed; no heavy imports.

```python
"""L2 audio extractor — audio SignalPacket -> FeatureSnapshot.

Registered for Modality.AUDIO in features/participant. Consumes the privacy-gated
semantic packets the mic producer emits (kinds: audio_social_context / audio_prosody
/ audio_ambient) and shapes a FeatureSnapshot L3's audio_social_context axis can fuse
live. Semantic-first (#11): inputs are already derived values, never raw audio.
"""
from __future__ import annotations

from core.protocol.enums import Intent
from core.protocol.payloads import SignalPacket
from features.snapshot import FeatureSnapshot

EXTRACTOR_TAG = "audio_social.v1"
_INTENT_VALUES = {i.value for i in Intent}
_DEFAULT_INTENT = Intent.CONTINUOUS.value

# speaker -> coarse social category (single source of truth for the alone/with_other map).
def social_category(speaker: str) -> str:
    return "with_other" if speaker in ("other", "both") else "alone"


def extract(sig: SignalPacket) -> FeatureSnapshot:
    p = dict(sig.payload)
    features: dict = {"kind": sig.kind, "extractor": EXTRACTOR_TAG}

    if sig.kind == "audio_social_context":
        speaker = p.get("speaker", "none")
        features.update({
            "speaker": speaker,
            "social_category": social_category(speaker),
            "num_speakers": p.get("num_speakers", 0),
            "vad_active": bool(p.get("vad_active", False)),
            "suppressed": bool(p.get("suppressed", False)),
        })
    elif sig.kind == "audio_prosody":
        features["prosody"] = p
    elif sig.kind == "audio_ambient":
        features["ambient"] = p.get("top_classes", [])
    else:
        features["features"] = p   # unknown audio kind: passthrough, honest

    return FeatureSnapshot(
        user_id=sig.user_id,
        timestamp=sig.timestamp,
        modality=sig.modality,
        source=sig.source,
        payload=features,
        intent=sig.intent if sig.intent in _INTENT_VALUES else _DEFAULT_INTENT,
        confidence=sig.confidence,
        i_model_id=sig.i_model_id,
    )
```

**Registry edit** (`features/participant.py`): add `from features.audio_social import extract as _extract_audio_social` and change the registry entry `"audio": _stub_passthrough_extractor` → `"audio": _extract_audio_social`. Leave `"voice"` on the passthrough stub (explicit voice/STT path is separate, out of scope). This is the only L2 change; it is additive and import-clean.

### 2.6 Minimal L3 change — live fusion from the bus packet (`fusion/axes/audio_social_context.py`)
**The honest minimal change.** Today `audio_social_context.fuse_recent(*, user_id, now)` ignores the packet and reads the DB. The fusion participant's `_wrap_fuse_recent` calls `fuse_recent(user_id=packet.user_id, now=now)` — it has the packet but doesn't pass it. To make the live arc work end-to-end while keeping the DB path and all tests green, add a packet-aware front door WITHOUT changing the existing `fuse_recent` signature or DB behavior:

Add a new function the participant can prefer when an audio FeatureSnapshot is in hand:

```python
def fuse_from_feature(packet, *, now=None) -> AxisEstimate | None:
    """Build a live estimate from an L2 audio FeatureSnapshot, else None.

    Only fires for our own kind (audio_social_context); other kinds/modalities
    return None so the participant falls back to the DB fuse_recent path. No DB.
    """
    feats = getattr(packet, "payload", {}) or {}
    if feats.get("kind") != "audio_social_context":
        return None
    category = feats.get("social_category")
    if category is None:
        category = "with_other" if feats.get("speaker") in ("other", "both") else "alone"
    return AxisEstimate(
        axis=AXIS, value={"category": category},
        timestamp=getattr(packet, "timestamp", now) or now,
        confidence=0.8, source=SOURCE + ".live",
        meta_context=None, fresh_for_seconds=FRESH_SECONDS,
    )
```

This function is **pure (no `db` call)** — so importing it is DB-free, and it is exercised by a `fusion/` unit test that constructs a `FeatureSnapshot` directly.

**Participant wiring (the minimal, surgical edit in `fusion/participant.py`):** change the `audio_social_context` combiner so it tries `fuse_from_feature(packet, now)` first and, only if that returns `None`, falls back to the DB `fuse_recent`. Concretely, replace the registry entry's wrapper for this one axis with a small combiner:

```python
def _audio_combiner(packet, now):
    try:
        live = audio_social_context.fuse_from_feature(packet, now=now)
        if live is not None:
            return live
        return audio_social_context.fuse_recent(user_id=packet.user_id, now=now)
    except Exception as exc:   # same crash-safety contract as _wrap_fuse_recent
        return _offline_estimate("audio_social_context", now=now, reason=f"axis error: {exc!r}")
```

and register `"audio_social_context": _audio_combiner`. `meta_context` and `sleep_stage` keep using `_wrap_fuse_recent` unchanged. **Net effect:** when an audio FeatureSnapshot rides the bus, the axis fuses live with zero DB access; for any other inbound packet (e.g. a mac_activity feature), `fuse_from_feature` returns `None` and the existing DB `fuse_recent` runs exactly as before. Both `test_audio_social_context.py` (DB-mocked `fuse_recent`) and `test_participant.py` stay green because neither path was removed.

**What is deferred (documented, intentional):**
- **Prosody/ambient fusion into belief axes.** `audio_prosody`/`audio_ambient` packets now reach L2 as FeatureSnapshots but L3 has no prosody or ambient axis yet. They are emitted, shaped, and ride the bus, but are not yet fused into a belief. Adding `audio_prosody`/`audio_ambient` axes is a clean follow-up (new axis module + registry entry). This work delivers the **social-context** belief live, which is the stated goal ("live audio_social_context belief from real mic activity").
- **Real `suppressed` value** through `ContinuousProcessor` (see §2.2) — optional one-kwarg follow-up.
- **DB persistence of the live bus stream.** The bus path does not write `sensor_readings`; the DB path (when both sinks are wired) still does. Unifying them behind a single persistence subscriber on `TOPIC_SIGNAL` is future work, not required for the live belief.

### 2.7 Files touched (summary)
| File | Change | On CI path? |
|---|---|---|
| `sensors/audio_adapter.py` | NEW — `AudioBusSink` + `_reading` producer | yes (`sensors`) |
| `sensors/test_audio_adapter.py` | NEW — producer + privacy arc tests | yes |
| `features/audio_social.py` | NEW — L2 AUDIO extractor | yes (`features`) |
| `features/participant.py` | EDIT — register `"audio"` → real extractor | yes |
| `features/test_audio_social.py` | NEW — extractor unit tests | yes |
| `fusion/axes/audio_social_context.py` | EDIT — add pure `fuse_from_feature` | yes (`fusion`) |
| `fusion/participant.py` | EDIT — `_audio_combiner` (live-first, DB-fallback) | yes |
| `fusion/axes/test_audio_social_context.py` | EDIT/ADD — `fuse_from_feature` + combiner cases | yes |
| `voice/loop.py` | EDIT — optional `bus=` wiring in `listen_continuous` | NO (production only) |

No change to `core/protocol/*`, `core/bus/*` (the 6 topics, the Transport ABC), or `audio_context/*` (extractors + privacy untouched). `ContinuousProcessor` signature untouched.

---

## 3. Test plan (hardware-free, network-free, DB-free)

All new tests live under `sensors/`, `features/`, `fusion/` so the **exact CI command** covers them:
`python -m pytest core sensors features fusion prediction decision output -q` (run from `apps/inference`, no `DATABASE_URL`). No test imports torch, sounddevice, db, or a real mic. Synthetic `ContinuousProcessor` outputs are injected via fake `identify_speakers/prosody_of/ambient_of`.

### 3.1 `sensors/test_audio_adapter.py` — producer + privacy arc
Construct a real `MessageBus()` (default `InProcessTransport`), an `AudioBusSink(bus)`, and a real `ContinuousProcessor` with **injected fakes** (no models):

1. **`test_self_speech_emits_social_and_prosody_on_bus`** — `identify_speakers=lambda a,sr:["self"]`, `prosody_of` returns a dict, sink methods bound. Subscribe a collector to `TOPIC_SIGNAL`. Call `proc.process_window(np.ones(16000,float32), 16000, vad_active=True, now=...)`. Assert two `SignalPacket`s landed: kinds `{audio_social_context, audio_prosody}`; both `modality=="audio"`, `intent=="continuous"`, `source=="mic_listener_v1"`; social payload `speaker=="self"`.
2. **`test_other_voice_emits_presence_only`** (PRIVACY, load-bearing) — `identify_speakers=lambda:["self","other"]`. Assert exactly ONE `SignalPacket` on `TOPIC_SIGNAL`, kind `audio_social_context`, `payload["speaker"]=="both"`. Assert NO `audio_prosody` and NO `audio_ambient` packet was emitted (gate suppressed). Proves prosody/ambient never ride the bus when a non-self speaker is present.
3. **`test_unknown_speaker_fails_safe_to_suppressed`** — `identify_speakers=lambda:["unknown"]`. Assert one presence packet, `speaker=="other"`, and no prosody/ambient (unknown → other → suppressed, #1 fail-safe).
4. **`test_silence_emits_ambient_marker`** — `vad_active=False`, `ambient_of` returns `[{"class":"Silence","score":0.9}]`. Assert presence (`speaker=="none"`) + `audio_ambient` packet; no prosody.
5. **`test_consent_scope_and_no_raw_audio`** — inspect the emitted envelope: `consent_scope == "mic_continuous_v1"` (via `consent_scope_for` AUDIO mapping); assert the `SignalPacket.payload` contains no `numpy`/bytes/`audio` key (semantic-first #11).
6. **`test_transport_agnostic_shape`** — assert the envelope `.to_dict()` serializes cleanly (proves it is wire-ready for `NetworkTransport`); no transport is named in the producer.

### 3.2 `features/test_audio_social.py` — L2 extractor
1. `audio_social_context` SignalPacket (`speaker="both"`) → `FeatureSnapshot` with `payload["social_category"]=="with_other"`, `modality=="audio"`, `extractor=="audio_social.v1"`.
2. `speaker="self"` → `social_category=="alone"`.
3. `audio_prosody` packet → `payload["prosody"]` carries the dict through.
4. `audio_ambient` packet → `payload["ambient"]` is the class list.
5. **Registry**: `from features.participant import select_extractor; select_extractor("audio")` is the real audio extractor (not the passthrough stub); `select_extractor("voice")` is still the stub.
6. **Bus arc**: `register(bus)`, publish an audio `SignalPacket` envelope on `TOPIC_SIGNAL`, assert a `FeatureSnapshot` lands on `TOPIC_FEATURE` with `payload["social_category"]` set and inherited `trace_id`.

### 3.3 `fusion/axes/test_audio_social_context.py` — live fusion (add to existing file)
Keep the three existing DB-mocked `fuse_recent` tests unchanged (they prove the DB fallback still works). Add:
1. **`test_fuse_from_feature_with_other`** — build a `FeatureSnapshot(modality="audio", payload={"kind":"audio_social_context","social_category":"with_other","speaker":"both"})`; `fuse_from_feature(packet, now=now)` → `AxisEstimate(value={"category":"with_other"}, confidence=0.8, source endswith ".live")`. **No DB touched** (no `get_conn` monkeypatch needed — proves the live path is DB-free).
2. **`test_fuse_from_feature_alone`** — `speaker="self"` → `category=="alone"`.
3. **`test_fuse_from_feature_ignores_non_audio_kind`** — a packet with `payload={"kind":"mac_activity",...}` → `fuse_from_feature` returns `None` (so the participant will fall back to DB).

### 3.4 `fusion/test_participant.py` — combiner integration (add one test)
**`test_live_audio_packet_fuses_social_belief_no_db`** — the full L3 arc without a DB: register the **default** `FusionParticipant` (real `AXIS_REGISTRY` incl. `_audio_combiner`), but DO NOT provide a DB. Publish a `TOPIC_FEATURE` envelope whose payload is an `audio_social_context` `FeatureSnapshot` (`social_category="with_other"`). Assert a `BeliefState` lands on `TOPIC_BELIEF` with `belief.get("audio_social_context", now=now).value == {"category":"with_other"}`. Because `fuse_from_feature` returns a live estimate, `fuse_recent` (DB) is never called → no `get_conn`, no crash, no monkeypatch. The other axes (`meta_context`, `sleep_stage`) return OFFLINE for an audio packet (their DB `fuse_recent` raises → swallowed to OFFLINE by `_wrap_fuse_recent`), which is the correct, already-tested degraded behavior.

### 3.5 End-to-end producer→L1→L2→L3 arc (in `sensors/test_audio_adapter.py` or a dedicated `fusion/` test)
**`test_full_audio_arc_self_present`** — single bus, `assemble`-style manual wiring of L2 (`features.participant.register`) + L3 (`fusion.participant.register`); subscribe collectors to `TOPIC_FEATURE` and `TOPIC_BELIEF`. Drive `ContinuousProcessor.process_window(...vad_active=True, speakers=["self"])` through an `AudioBusSink`. Assert: a `FeatureSnapshot(payload.social_category=="alone")` reached L2 AND a `BeliefState` with `audio_social_context=={"category":"alone"}` reached L3 — proving the live mic→belief arc end-to-end with zero DB/network/hardware.
**`test_full_audio_arc_other_present_only_presence`** — same wiring, `speakers=["self","other"]`. Assert the L3 belief is `with_other`, AND assert only ONE `SignalPacket` (presence) was emitted on `TOPIC_SIGNAL` and no `audio_prosody` FeatureSnapshot was ever produced (privacy proven across the whole arc).

### 3.6 Regression guard
Re-run the full CI command and confirm the prior **139 passed** count rises by the count of new tests with zero failures, no new DATABASE_URL requirement, no torch import. The `core/test_import_purity.py` guard continues to pass (none of the new modules pull `db` into the import graph).

---

## 4. Constraint compliance checklist
- **Reuse, don't reimplement** — VAD/diarization/prosody/ambient + the `PrivacyGate` state machine are reused via `ContinuousProcessor`; the producer only injects bus-sink writers. ✓
- **Transport-agnostic** — producer holds only a `MessageBus`; no transport named; envelope is `to_dict()`-serializable for `NetworkTransport`. ✓
- **Privacy load-bearing** — every emission routes through `ContinuousProcessor` → `audio_context/privacy.py`; non-self/unknown → presence-marker only; prosody/ambient/raw never emitted while suppressed; fail-safe (unknown→other). Semantic-first: no raw audio on the bus. ✓
- **Frozen protocol unchanged** — no edits to `core/protocol/*`, the `Transport` ABC, or the 6 topics. Minimal additive fills to L2 (register audio extractor) and L3 (`fuse_from_feature` + `_audio_combiner`), DB path preserved. ✓
- **Tests hardware/network/DB-free** — all new tests under `sensors/`/`features/`/`fusion/`, on the CI path, inject synthetic `ContinuousProcessor` outputs, assert the audio→L1→L2→L3 arc and the suppress-to-presence-only privacy behavior. ✓
- **YAGNI** — prosody/ambient L3 axes, real `suppressed` plumbing, and unified bus-persistence are explicitly deferred; this delivers exactly the live `audio_social_context` belief. ✓
- **No commits** — authoring + self-test only; working tree left for the controller. ✓
