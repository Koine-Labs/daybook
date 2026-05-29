# Daybook — Nervous-System Skeleton

**Date:** 2026-05-28
**Status:** design approved; implementation plan next (writing-plans)
**Topic:** the distributed message-passing skeleton that ties L1–L6 into one nervous system, built so the organs later move onto the Wisp without internal change.

## 1. Goal

Build the complete *nerves* of Daybook now — the typed messages and the pathways they travel between layers — so that when the body later splits across devices (Wisp ↔ phone ↔ desktop ↔ cloud), nothing inside any layer changes; only *where each part runs* changes.

This is a **skeleton-first** build: scaffold every layer's contract and get the whole L1→L6 pipeline running end-to-end (real where code exists, honest stubs elsewhere) before filling any layer deeply. Filling each layer is a separate follow-on spec.

## 2. Decisions locked (from brainstorming, 2026-05-28)

- **Slice:** skeleton-first across all six layers + cross-cutting, then fill.
- **Portability:** full distributed *contract shape* now — real cross-node protocol, envelope, node roles, bus.
- **Bar:** clean-prototype — typed and well-structured, light on versioning/observability/exhaustive contract-tests; optimize for runnable breadth. Harden later.
- **Bus realization:** in-process async pub/sub today (whole pipeline = one process on the Mac), behind a `Transport` seam so a broker/HTTP relay slots underneath later with zero layer-code change.
- **Wire format:** dataclasses (matching existing `FeatureSnapshot`/`AxisEstimate` style — `__post_init__` validation + `to_dict()`) as source of truth → JSON on the wire; mirrored to TS in `packages/shared`. (Pydantic stays at the HTTP boundary only.)

## 3. The four building blocks

### 3a. Protocol — the language the nerves speak
One shared vocabulary of typed messages. Every message rides in a `MessageEnvelope`:

```
MessageEnvelope:
  id: UUID
  type: str                       # payload discriminator
  schema_version: int             # present but not gold-plated (clean-prototype bar)
  source_role: NodeRole
  target_role: NodeRole | None    # None = broadcast
  occurred_at: datetime           # tz-aware UTC, always
  meta_context: MetaContext       # waking|sleep + sub-state — commitment #14
  consent_scope: str              # privacy travels with the data — commitment #11
  trace_id: UUID                  # follow one stimulus through all 6 layers
  i_model_id: UUID | None         # commitment #1
  payload: SignalPacket | FeaturePacket | BeliefState | Prediction | ActionDecision | OutputDirective
```

Payloads, one per layer handoff:

- **`SignalPacket`** (L1→L2): `modality` (voice|text|gesture|biometric|audio|vision|bci) + `intent` (explicit|continuous) — commitment #10's two orthogonal axes as first-class fields — plus `kind`, `payload` (JSONB-shaped), `recorded_at`. Semantic-first: only meaningful extractions ride here, never raw pixels/audio (#11).
- **`FeaturePacket`** (L2→L3): wraps the existing `features/snapshot.py::FeatureSnapshot` (carries `.intent` already).
- **`BeliefState` / `AxisEstimate`** (L3): the existing `fusion/belief_state.py` types, including the `OFFLINE` sentinel.
- **`Prediction`** (L4→L5): forecast for `(axis, horizon, action)` — distribution + confidence + `model_id` + provenance (`placeholder|calibrated`). Carries the `action` seam for #15/#16. `PREDICTION_OFFLINE` sentinel mirrors L3's `OFFLINE`.
- **`ActionDecision`** (L5→L6): chosen action (interject|hold, witness|companion, content kind) + rationale + safety-gate trace.
- **`OutputDirective`** (L6→channel): rendered intent + channel (voice primary; haptic/visual future) + delivery params (mode-aware pacing).

### 3b. Bus — the pathways
A minimal pub/sub core: `publish(envelope)` / `subscribe(topic, handler)`. Routes by `target_role`.
- `InProcessBus` — async in-memory; runs the full pipeline as one process today.
- `Transport` interface — the seam. Today every role resolves to "local." Later a `NetworkTransport` (broker or HTTP relay over the existing tunnel) slots under the same interface; layers are unaware.

### 3c. Node roles — the body map
`NodeRole` enum (`wisp_edge | phone_relay | desktop_compute | cloud`) + a declarative placement config mapping each layer/handler to its eventual home. Today all map to the local process; it is the destination written as code, and it is what the bus consults to route. Generalizes `apps/AI_PI_CONTRACT.md`.

### 3d. Layer skeletons — the organs
Each layer is a module with: an **interface** (contract), a **registry** where it selects plug-ins (L3 axes, L4 predictors, L5 policies), a **degraded/OFFLINE sentinel**, a **smoke test**, and **implementations real where code exists, honest stubs elsewhere**. Every layer reads `meta_context` from the envelope (#14).

## 4. File structure (target)

New code is additive; existing working modules are *wrapped*, not rewritten.

```
apps/inference/
  core/                      # NEW — the nervous system itself
    protocol/                # MessageEnvelope + 6 payloads (dataclasses); NodeRole, MetaContext enums
    bus/                     # InProcessBus + Transport seam + topic registry
    nodes.py                 # placement config (layer/handler → NodeRole)
  sensors/   (L1)            # NEW contract — IntentTaggedReading → SignalPacket; adapters wrap mac mic, HK sync, mock
  features/  (L2)            # snapshot.py exists; producers emit FeaturePacket
  fusion/    (L3)            # EXISTS — register 3 live axes; interfaces for missing axes + observers
  prediction/(L4)            # NEW — registry + predict(axis,horizon,action) + PREDICTION_OFFLINE + stub predictors + classifier wrap
  decision/  (L5)            # NEW — policy registry + intent_dispatch + sleep_cue (5 gates recovered from git) + bandit stub
  output/    (L6)            # NEW — meta-context-aware channel selection + composer-as-renderer
packages/shared/src/         # protocol types mirrored to TS (types.ts / ids.ts)
```

No new top-level doc tree. This spec + the eventual plan are the only new docs; subsystem docs (`FUSION.md`, etc.) are written only if a fill spec needs them.

## 5. How existing code adapts (no rewrites)

- `apps/voice/loop.py` → an L1-capture + L6-output pair of bus participants.
- `apps/wisp/composer.py` → the L6 renderer (relocate per REBUILD_PLAN keep-list; persona unchanged).
- `embeddings/`, `llm/` → sit behind `desktop_compute` / `cloud` node roles (compute placement).
- The 3 live fusion axes → register into the L3 registry; `loader.py`/`writer.py` unchanged behind it.
- The trained sleep classifier → wrapped as the first registered L4 predictor (stub-then-real).

## 6. Commitments honored at the contract level

Baked into the envelope/contracts so they cannot be violated downstream: #1 (`i_model_id`), #3 (voice-primary L6), #10 (intent+modality on `SignalPacket`), #11 (semantic-first, `consent_scope` travels with data), #14 (`meta_context` on every envelope), #16 (`predict(axis, horizon, action)` seam). #12 is generalized: the `Transport` seam *is* the bridge.

## 7. Definition of done (this spec)

1. Every layer boundary speaks the typed protocol; the tree type-checks and compiles (`pytest apps` + `tsc -p packages/shared`).
2. **One command sends a stimulus end-to-end** and a single `trace_id` is observable flowing L1→L6 — real where built, stubbed elsewhere.
3. A smoke test per layer passes.
4. `packages/shared` TS types mirror the protocol payloads + envelope.
5. STATUS.md updated; no other new docs.

## 8. Out of scope (becomes follow-on fill specs)

Real L4 predictors + JEPA world model; real L5 policies + bandit; remaining L3 axes (`arousal_inferred`, `valence`, `state_declared`, `cognitive_load`) + post-session observers; vision/BCI capture adapters; `NetworkTransport` (real cross-node); schema-versioning/migration machinery; observability/tracing depth; clinical-tier substrate. The skeleton makes each a contained, parallelizable job.

## 9. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Skeleton scope sprawls into fills | Hard line: stubs that speak the protocol, not implementations. Fills are separate specs. |
| Protocol churns once fills start | Clean-prototype bar accepts churn; `schema_version` exists but isn't gold-plated. Lock payloads only after one end-to-end run. |
| Existing modules resist wrapping | Adapt at the seam (an adapter that emits/consumes packets); never edit working internals in this spec. |
| Recovered code (sleep_cue gates, classifier inference) drifts from v0 | Recover verbatim from the safety-net tag (`git show v0-pre-rebuild:apps/inference/cue_decision.py`), not from memory. |

## 10. How this spec stays alive

Update only when a payload type or a building block changes. When a fill spec lands, note the closed stub here in one line. Do not duplicate ARCHITECTURE.md — link to it.
