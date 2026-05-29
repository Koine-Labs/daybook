# Continuous semantic vision — design

**Date:** 2026-05-29
**Status:** approved (design delegated to Claude; founder chose "build the code system, defer hardware/using")
**Piece:** the last absent sense (candidate **A**). A continuous, semantic-first vision lane onto the L1–L6 bus — completing the multimodal set (mic + biometric + BCI + **vision**) toward the north star: walking down the street, fully sensed.

## Context

Vision is the only modality with no live bus lane: `features/participant.py:77` points `"vision"` at the passthrough stub, and the only vision code is `llm/vision.py` — a **batch cloud describer**. Per commitment **#11**, continuous vision must be **semantic-first**: low-bandwidth meaningful extraction at the edge (objects / scene / OCR → a semantic packet), **raw pixels discarded**; the cloud multimodal call (`llm/vision.py describe_image`) is **triggered-escalation only, never continuous**.

This lane mirrors the shipped BCI lane exactly (synthetic-signal → real-model-on-hardware), so the camera is a *calibration/using* step later, not part of this build:
- BCI: `sensors/eeg_adapter.py` + `bci/bandpower.py` → `features/bci.py` (Modality.BCI) → `fusion/axes/cognitive_load.py` + consent `eeg` + off-CI `bci/firmware/eeg_edge_stub.py`.
- Vision (this piece): `sensors/vision_adapter.py` + `vision/perception.py` → `features/vision_scene.py` (Modality.VISION) → `fusion/axes/visual_context.py` + consent `vision` + off-CI `vision/perception_edge_stub.py`.

**Ground truth (verified on disk):** `Modality.VISION="vision"` exists; consent has **no vision scope** (vision falls through to `unscoped_v0` — a tracked fail-open gap this piece closes, mirroring how BCI got `eeg`); L3 axis pattern = `fuse_from_feature` + a live-only combiner in `fusion/participant.py` + `AXIS_REGISTRY`; L2 pattern = `extract(sig)` + `compute_derived`, registered for the modality (replacing the stub).

## Design

### Semantic schema (the `visual_scene` SignalPacket payload — semantic-first, #11; NO pixels)
```
{ "setting": "outdoor"|"indoor"|"transit"|"screen"|"unknown",
  "people_present": int,            # detected persons
  "salient_objects": [str],         # top-k detected object classes
  "text_present": bool,             # OCR found text (optional)
  "model": str }                    # provenance: "yolov8n" | "synthetic"
```

### New: `vision/perception.py` (+ `vision/__init__.py`) — canonical edge extraction (analog of `bci/bandpower.py`)
- `extract_semantics(image_bytes) -> dict`: runs the real detector (LAZY import of the `[vision]` model — ultralytics YOLO for person/object, optional OCR), returns the semantic dict, **discards pixels** (#11). Off-CI (needs the model). Constants: `SETTINGS`, `KIND_VISUAL_SCENE="visual_scene"`, `VISION_SOURCE="camera.visual_scene"`.

### New: `sensors/vision_adapter.py` (CI-safe, transport-agnostic — mirrors `EEGBusSink`)
- `VisionBusSink`: holds only a `MessageBus` (+ `user_id`, `meta_context=UNKNOWN`). `emit_scene(semantics, *, timestamp, ...) -> MessageEnvelope`: wrap the semantic dict in `IntentTaggedReading(modality=VISION, intent=CONTINUOUS, kind=KIND_VISUAL_SCENE, source=VISION_SOURCE)` → `sensors.participant.emit`. Asserts no raw-pixel key rides the payload.
- `synthesize_vision_frame(index=0) -> dict`: deterministic synthetic semantic dict (mirrors `synthesize_eeg_window`), varying by `index`, never random.

### New: `features/vision_scene.py` — L2 extractor (mirrors `features/bci.py`)
- `compute_derived(semantics) -> dict`: `people_present:bool`, `crowd_size:"none"|"one"|"few"|"many"`, `setting` passthrough, `has_text:bool`, `object_count:int`.
- `extract(sig) -> FeatureSnapshot`: structured payload (`kind`, `extractor`, `semantics`, `features`). Registered for `Modality.VISION` in `features/participant.py` (replaces the stub).

### New: `fusion/axes/visual_context.py` — L3 axis (mirrors `cognitive_load.py`)
- `fuse_from_feature(packet, *, now) -> AxisEstimate|None`: fires only for `kind=="visual_scene"`; value `{setting, people_present, salient_objects, category:"alone"|"with_people", method, scaffold:True}`. A WAKING sub-context (#14). Live-only (no DB vision table yet — no `fuse_recent`), honest confidence ~0.5. Wired via a `_visual_combiner` (live-only, like `_cognitive_load_combiner`) + `AXIS_REGISTRY["visual_context"]` in `fusion/participant.py`.

### New: `vision/perception_edge_stub.py` (off-CI — analog of `bci/firmware/eeg_edge_stub.py`)
- Runs `extract_semantics` over a sample image → `VisionBusSink.emit_scene` over `InProcessTransport`; documents the one-line `NetworkTransport` swap (camera-as-satellite) and the camera-on-arrival "using" step. Lazy imports; import-clean with no model/DB.

### Edits
- `consent.py`: add `"vision": "camera_continuous_v1"`.
- `sensors/participant.py`: add `Modality.VISION.value: CONSENT_SCOPES["vision"]` to `_MODALITY_CONSENT` (closes the `unscoped_v0` fail-open).
- `features/participant.py`: register `vision_scene.extract` for `"vision"`.
- `fusion/participant.py`: import `visual_context`, add `_visual_combiner` + `AXIS_REGISTRY["visual_context"]`.
- `pyproject.toml`: add a `[project.optional-dependencies] vision = [...]` extra (ultralytics + pillow) — heavy, off-CI, like `voice`.

### Triggered-escalation seam (#11 — documented, not wired into the continuous loop)
`llm/vision.py describe_image` stays the escalation path: when the continuous semantic layer flags something salient/novel, a future L4/L5 hook escalates to the cloud describer. This piece documents the seam; it does not make any continuous cloud call.

## Test plan
- **CI-safe** (append `vision` to the CI suite, mirroring `bci`; tests live in `sensors/`, `features/`, `fusion/`, `vision/` — all import-clean with no model/DB):
  - `synthesize_vision_frame`: shape + determinism by index.
  - `VisionBusSink`: emits a well-formed VISION SignalPacket on `TOPIC_SIGNAL`; **#11 invariant — payload carries only the semantic dict, never raw image bytes**.
  - L2 `compute_derived` / `extract`: derived features correct; registered for VISION.
  - L3 `visual_context.fuse_from_feature`: mapping correct; non-vision packet → None (OFFLINE upstream).
  - **End-to-end (no model/DB):** synthetic frame → `VisionBusSink(WAKING)` → `TOPIC_SIGNAL` → L2 vision FeatureSnapshot → L3 `visual_context` belief; assert trace_id / meta_context / `consent_scope=="camera_continuous_v1"` / i_model_id propagate (#1/#11/#14).
  - consent: `VISION → camera_continuous_v1` (not `unscoped_v0`).
- **Off-CI:** `python -m vision.perception_edge_stub` (real model + sample image) — manual smoke.

## Commitments touched
- **#11** — primary: semantic-first vision; raw pixels discarded at the edge; cloud describe is triggered-escalation only.
- **#10** — VISION modality on the (intent, modality) axes.
- **#14** — `visual_context` is a WAKING sub-context; emits under the active meta-context.
- **#1** — `i_model_id` propagates through the lane.
- **#9** — transport-agnostic `VisionBusSink`: the same code becomes the camera-satellite producer over `NetworkTransport`.
- Closes the tracked **consent fail-open** for vision (`unscoped_v0` → `camera_continuous_v1`).

## Risks / notes
- The real detector (YOLO/OCR) is necessarily off-CI (a model call, not pure math) — CI proves the schema + bus plumbing on synthetic semantics, exactly as the BCI lane proved band-power plumbing on synthetic EEG. The real model is `[vision]`-extra + the off-CI edge stub.
- `visual_context` is an honest v1 mapping (`scaffold:True`, moderate confidence) feeding the #16 flywheel — not a tuned scene classifier.
- No live camera in this build (the founder's deferred "using"); `VisionBusSink` is transport-agnostic so the camera/Pi-satellite wires in later with no change.
- Scope guard: this is the *continuous* semantic lane only. The escalation hook to `llm/vision.py` is documented, not implemented.
