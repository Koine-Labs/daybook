# Daybook — System Architecture

> **Status: outline (v0.1).** This document is being filled in section-by-section through ongoing design conversation. Sections marked `TODO` are awaiting content. The outline is committed so the structure is stable and we can iterate without restructuring.

---

## What this document is

The single source of truth for **how Daybook fits together as a system** — its layers, the contracts between them, the inviolable architectural commitments, and the evolution roadmap.

**Sibling docs and their jobs:**
- `CLAUDE.md` — *how to work in this repo at all* (conventions, things-not-to-do)
- `STATUS.md` — *what's currently live and what's in flight* (operational state, evolves frequently)
- `RUNBOOK.md` — *how to actually run things* (command catalog, recipes)
- `POSITIONING.md` — *who this is for and why it matters* (strategy, not architecture)
- `docs/Architecture/<SUBSYSTEM>.md` — *deep dives on individual subsystems* (referenced from §4 of this doc)

If you're new to the repo, read `CLAUDE.md` first for orientation, then this document for the system shape.

---

## 1. System at a glance

*Status: TODO.* A high-level diagram (ASCII or Mermaid) showing inputs (phone + Mac + watch + future BCI/vision) → FastAPI bridge → backend layers → Postgres → outputs (TTS via bone-conduction, iOS UI, future hardware). Plus 3-5 sentences describing what you're looking at — what Daybook is at the level a stranger reads in 60 seconds.

---

## 2. Architectural commitments

The inviolable rules of the system. Each commitment exists to protect against a specific failure mode that would compromise the product. Locked unless explicitly re-opened in a design conversation; new code must not violate them.

### 1. I-Model polymorphism

**Rule.** Every event entity has `i_model_id UUID NULL`. Schema + retrieval hooks present from day one.

**Why.** New event kinds (chat messages, observations, dream recalls, moments, intents, etc.) shouldn't trigger schema migrations to associate with I-Models. One nullable column per table absorbs that cost up-front. Without this, adding I-Model awareness later becomes a multi-table refactor.

### 2. Content polymorphism

**Rule.** `regis_moments.kind` is a pluggable discriminator; cue selection and downstream logic is content-agnostic.

**Why.** New kinds of Regis utterance (sleep cue, walking remark, post-recall reflection, inner pulse, dream-thought, etc.) shouldn't require new tables. One log with a discriminator absorbs unbounded variety. Decision logic operates on the discriminator, not the content.

### 3. Wisp-as-interface

**Rule.** Audio output (eventually bone-conduction TTS) is the primary surface. Screens are for setup, debug, and explicit interaction.

**Why.** The product's defining experience is intimacy through voice, not screen time. Designing for "voice first" rules out features that only make sense in a screen-centric product. The eventual form factor (single-ear wearable) literally has no screen.

### 4. Three distinct I-Models

**Rule.** `user_self` (what the system has discovered about the user) + `regis_of_user` (how Regis perceives the user specifically) + `regis_self` (Regis's own current state). All three are first-class entities in `i_model_clusters` distinguished by `model_owner`.

**Why.** Conflating these confuses three fundamentally different things: who the user IS, how the system PERCEIVES them, and who REGIS IS. Each evolves under different update rules (user traits drift from real signal; Regis's perception updates from notable exchanges; Regis's self changes from his accumulated voice + nightly projection). Bundling them would force a single update mechanism that misrepresents at least two.

### 5. Regis is dual-mode, not flat-toned

**Rule.** Witness Mode during sleep (reverent, sparse). Companion Mode when awake (dry, teasing — canon TBATE energy). Same character, different posture based on user consciousness state.

**Why.** A single tone makes Regis either too quiet for waking life or too chatty for sleep. Mode is determined by `moment_kind` today; eventually by live `user_state_estimate`. Same identity expressed through context-appropriate posture is honest; flattening to a single tone is not.

### 6. Self-expanding I-Models

**Rule.** I-Models are DISCOVERED from data via unsupervised clustering, not pre-defined. The three top-level categories are containers; sub-I-Models emerge from embeddings. Embeddings are many-to-many with clusters via `embedding_cluster_memberships`.

**Why.** Pre-defined facet schemes (a fixed list of personality types or facets) are brittle and false. Real human variability emerges from real data. The system gains granularity as the user generates signal, rather than forcing the user into a pre-fab taxonomy.

### 7. Moment polymorphism

**Rule.** `regis_moments` is the generalized any-context Regis action log. Sleep cue, morning prompt, walking remark, conversation tease, inner pulse, dream-thought — all live here, distinguished by `kind`.

**Why.** Separate tables per Regis-utterance type would create artificial boundaries and fragment downstream processing (memory, retrieval, outcome tracking, embedding indexing). One log keeps the discipline "anything Regis does is a Moment" — testable, queryable, evolvable.

### 8. Generative Regis from day one (not scripted variants)

**Rule.** `PERSONA.md` is the system prompt; an LLM composes utterances dynamically per moment. Scripted variants in `PERSONA.md` serve as few-shot examples, not the output bank.

**Why.** Scripted output looks identical every time, creating brittle pattern recognition and a stale feel. Generative output uses retrieved context to compose appropriate utterances per moment. Changing Regis's voice means editing one persona file, not rewriting variant lists.

### 9. Continuous build, not phased

**Rule.** v1 prototype IS the v3 substrate. Don't defer features by phase; build them when foundational, even if the matching hardware lags.

**Why.** "We'll do that in v2/v3" architectures usually never reach v2/v3. By building everything as one continuous codebase that gracefully degrades when hardware is missing, the system is always one step closer to the destination. Hardware adoption then enables existing software rather than triggering rewrites.

### 10. Input is classified by intent AND modality

**Rule.** Every input event is classified along two orthogonal axes at the L1 ingestion boundary:

**Axis 1 — Intent** (user communication-intent):
- **Explicit** — user-initiated, communication-intended
- **Continuous** — ambient, passive sensing, no communication intent

**Axis 2 — Modality** (signal type):
- Voice / Text / Gesture / Biometric / Audio (non-voice) / Vision / BCI

The two axes are orthogonal: the same modality can appear under different intents (voice → explicit speech OR continuous mumbling; gesture → deliberate pinch OR involuntary blink). Output channels (voice primary, future haptic, future visual indicator) are all explicit-by-design.

**Downstream consequences:**

| Layer | Routes by |
|---|---|
| L1 — Sensors | Both — intent determines table (`chat_messages` / `user_actions` / `sensor_readings`); modality determines `kind` within table |
| L2 — Signal processing | **Modality** — biometrics → heartpy/neurokit2; audio → librosa/Whisper; BCI → MNE-Python; vision → OpenCV |
| L3 — Fusion | **(Intent, Modality)** — explicit speech and continuous prosody are weighted differently in the unified state |
| L4 — Prediction | **(Intent, Modality)** — HRV trajectory (continuous, biometric) is regression; nod event (explicit, gesture) is classification — different ML problems |
| L5 — Decision | **Intent** — explicit events dispatch as commands; continuous state updates feed posture |

**Why.** Intent alone is insufficient: the *type* of signal determines which library / model handles it. Modality alone is insufficient: the *meaning* of a signal depends on whether the user meant to send it. The two together give complete typing — an event is `(intent, modality)`, and downstream routing decisions split on whichever axis matters at that layer.

**Lineage.**
- v1 (2026-05-17): three input channels (voice / continuous context / gestures)
- v2 (2026-05-21 morning): refined to intent-based; gestures cross-cut both
- v3 (2026-05-21 afternoon): refined to two-axis classification (intent × modality) after recognizing both axes carry distinct architectural weight

### 11. Semantic-first continuous sensing

**Rule.** All continuous sensor streams use semantic-first architecture: continuous low-bandwidth meaningful extraction (VAD, diarization, prosody for audio; YOLO, scene class, OCR for visual) → semantic packets stored as `sensor_readings`. Raw pixels and raw audio are discarded after processing. Cloud LLM calls (multimodal vision, full STT) are *triggered escalation only* — never continuous.

**Why.** Continuous full-fidelity capture is impossible on battery, privacy, and cost grounds. The biological model is correct: the brain doesn't process every photon; it extracts features at low levels and escalates to focused attention selectively. Following this pattern is the only viable architecture for always-on awareness on real hardware.

### 12. Native clients talk to FastAPI, never brain modules directly

**Rule.** iOS, watchOS, and any future client speaks HTTP to `apps/api/`. They never import `chat`, `recall`, `wisp`, etc. The bridge is the seam. Auth via `X-API-Key` with loopback bypass.

**Why.** Direct module imports across language boundaries (Swift → Python) couple platforms together and break independent evolution. The FastAPI bridge enforces a clean contract: backend evolves in Python, clients evolve in their native stack, the API is the only thing that needs versioning. Auth and tunnel concerns are isolated at the bridge.

### 13. Regis is a controlled variable in his own predictive model

**Rule.** The decision layer eventually models how Regis's actions shape predicted future state — decisions become forward-looking treatment-effect estimation, not just retrospective scoring of "did interjecting help."

**Why.** A purely reactive Regis (responds to events, learns from outcomes) is fundamentally limited — it can never ask "if I do X vs Y, how does the user's trajectory change?" That counterfactual reasoning is the difference between a chatbot and an empathic agent. The Thompson contextual bandit (current state) is the first seed; the destination is a system that models its own influence on predicted state at t+1. Purely reactive architectures are inconsistent with the long-term direction.

### 14. The pipeline operates within a meta-context that biases every layer

**Rule.** Two mutually exclusive, non-overlapping meta-contexts: **Waking** and **Sleep**. Each contains sub-contexts that further refine bias:

- **Waking sub-contexts:** alert / working out / relaxed / focused / low-energy / social / ...
- **Sleep sub-contexts:** REM / deep / core / awake-in-bed / ...

Every layer's interpretation is conditioned on the active `(meta, sub)` context:

| Layer | What meta-context biases |
|---|---|
| L2 — Signal processing | Feature extraction priorities (which features matter in this state) |
| L3 — Fusion | Fusion weights and rules (which modalities dominate; how to combine) |
| L4 — Prediction | Model selection and prior weighting (different ML problems per state) |
| L5 — Decision | Action policies (Witness vs Companion mode — corollary of this commitment) |
| L6 — Output | Channel selection and style (no TTS during deep sleep; voice volume; haptic intensity) |

L1 captures uniformly; meta-context biases begin at L2.

**Why.** Human cognition doesn't process inputs uniformly across all states. Background hum during deep sleep doesn't trigger attention; the same hum during alert work might. A system that flattens this — treating sleep as just another state dimension — fails to mirror how perception actually works. Meta-context as a cross-layer bias means every component naturally asks "how do I behave differently in this mode?" — and Regis's voice, perception, and decisions stay coherent across phases of the user's day.

**Relationship to existing commitments.**
- Commitment #5 (Regis dual-mode: Witness vs Companion) is the L5/L6 *corollary* of this commitment, scoped to persona/output.
- Commitment #11 (semantic-first continuous sensing) is the L2 *foundation* — semantic packets carry the meta-context-relevant features at low cost.
- Commitment #4 (Three I-Models) — the `regis_self` model's mode field is one expression of meta-context propagation.

**Lineage.** Added 2026-05-21 PM. Identified during §3 layered-design conversation when the user observed that sleep isn't a state variable within the pipeline — it's a meta-context that biases the entire pipeline.

---

## 3. The layered design

Daybook organizes around 6 horizontal layers. Each has one job, takes inputs from the layer below, produces outputs for the layer above. Writing the contracts makes parallel work possible — once each layer's contract is agreed, implementations are independent.

```
Layer 6 — Output             text → TTS / UI / future hardware effects
Layer 5 — Decision           forecasts + outcomes → action choice
Layer 4 — Prediction         state + trajectory → data / context / action forecasts
Layer 3 — Fusion             intent-tagged features → unified state representation
Layer 2 — Signal processing  raw sensor data → meaningful features (per modality)
Layer 1 — Sensors            raw input ingestion (intent-classified at the boundary)
```

**Two cross-cutting principles propagate through every layer:**

**Intent + modality (per commitment #10).** Every event is classified along two orthogonal axes at the L1 boundary — Intent (Explicit / Continuous) and Modality (Voice / Text / Gesture / Biometric / Audio / Vision / BCI). Downstream layers route by whichever axis matters at that step: L2 routes by modality (which library to use); L3 and L4 route by `(intent, modality)`; L5 routes by intent.

**Meta-context (per commitment #14).** The pipeline runs within one of two meta-contexts — Waking or Sleep — each with sub-contexts that further refine bias. Every layer's interpretation is conditioned on the active `(meta, sub)` context. Where a layer's meta-context bias is load-bearing, the layer notes it explicitly.

For each layer below: **Job** · **Contract** · **Meta-context bias** · **Evolution**.

> This document describes the **ideal** architecture. Where current implementation diverges, see §11 (Implementation gap index) and `STATUS.md`. Per-layer descriptions describe what should be, not what currently is.

---

### Layer 1 — Sensors

**Job.** Ingest raw input from sources; persist as discrete events tagged with `(intent, modality)`. No interpretation — only schema normalization.

**Two-axis classification at the boundary (per commitment #10):**

Every event has both an intent and a modality:

| | Voice | Text | Gesture | Biometric | Audio (non-voice) | Vision | BCI |
|---|---|---|---|---|---|---|---|
| **Explicit** | Spoken-to-Regis | Typed chat | Pinch / nod / wave | — | — | Looking-at-camera | — |
| **Continuous** | Background mumble | — | Blink / jaw clench | HR / HRV | Room prosody | Scene / presence | EEG / EOG / EMG |

Storage: intent determines the table; modality determines the row's `kind` (or content):
- **Explicit** → `chat_messages` (voice/text), `user_actions` (gestures)
- **Continuous** → `sensor_readings` (polymorphic via `kind`: `heart_rate`, `hrv`, `audio_context`, future `eeg_packet`, etc.)

**Contract.**
- *Inputs:* hardware/user events (HealthKit deltas, mic frames, typed text, future BCI samples, etc.)
- *Outputs:* persistent rows in event tables, each implicitly tagged with `(intent, modality)` by destination table + `kind`
- *Cadence:* per-event. No fixed clock; driven by source.
- *Interpretation:* minimal — schema normalization only. Modality-specific feature extraction (Whisper STT, prosody features) happens at L2.

**Meta-context bias.** L1 captures uniformly regardless of meta-context. Sleep vs Waking biases begin at L2. (L1 may eventually throttle explicit-intent capture during deep sleep — there's no reason to run STT continuously when the user is asleep — but this is an efficiency optimization, not a behavioral change.)

**Evolution.** Polymorphic schema absorbs new modalities without migrations. Adding BCI is `kind='eeg_packet'`, not a new table. Modality coverage extends as hardware comes online.

---

### Layer 2 — Signal processing

**Job.** Turn raw L1 events into meaningful **features** that downstream layers can reason about. Each modality runs through its own established library pipeline.

**The L2 mini-pipeline per modality:**
```
L1 row → [signal normalization] → [feature extraction] → FeatureSnapshot → L3
```

- **Signal normalization** (where the source doesn't already provide it): filter noise, baseline-correct, resample to common rates. For modalities where the source pre-normalizes (Apple HealthKit, Whisper), this step is a no-op.
- **Feature extraction:** the main work. Library calls that compute higher-level numbers from (normalized) raw data.

**Routing — by modality (per commitment #10).** Each modality runs through its own established library:

| Modality | Library / model | Intent-specific branches? |
|---|---|---|
| Biometric | `heartpy`, `neurokit2` | No — always continuous |
| Audio | `librosa`, `Whisper` | **Yes**: explicit → text + prosody; continuous → prosody only |
| Vision | `OpenCV`, `MediaPipe`, `YOLO` | **Yes**: explicit → face/gaze landmarks; continuous → scene/presence |
| BCI | `MNE-Python`, `NeuroDSP` | Continuous for raw-signal features; explicit-gesture detection is a separate path |
| Text | `sentence-transformers` (BGE-M3) | No — always explicit |
| Gesture | (vision-derived; model TBD) | **Yes**: explicit → command classification; continuous → micro-feature |

**Contract.**
- *Inputs:* L1 events from `sensor_readings` / `chat_messages` / `user_actions`
- *Outputs:* `FeatureSnapshot` with uniform envelope + modality-specific payload:
  ```
  {user_id, modality, intent, timestamp, features, confidence}
  ```
  The envelope is invariant across modalities; the `features` payload is modality-specific (a dict of prosody floats, a 1024-dim BGE-M3 vector, a 24-element biometric feature tuple, future bandpower vector for BCI, etc.).
- *Cadence:* continuous streams → rolling-window extraction at modality-appropriate rate (biometrics every 5min; audio prosody every 5-10s; future BCI every 1s). Explicit events → one snapshot per event.

> **Envelope vs payload.** The envelope normalizes *shape*, not *values*. The payload is modality-specific in both content and native units (HRV in ms, pitch in Hz, embedding in unit-vector space, etc.). The envelope's job is to give downstream layers a uniform integration point; interpretation of payload content stays modality-aware.

**Meta-context bias.** L2's feature-extraction priorities shift with the active meta-context:

- **Waking:** full multi-modal extraction across all available sensors. STT runs on detected explicit voice; prosody extracts continuously on ambient audio; biometric features support moment-to-moment state estimation; vision processes scene + presence; BCI extracts attention/alertness markers.
- **Sleep:** extraction priorities shift —
  - **STT mostly off** (no point transcribing internal dream activity)
  - **Audio shifts to sleep-event detection** (snoring, sleep-talking, environmental disturbances) rather than everyday speech
  - **Biometric features prioritize sleep classification** (REM/non-REM features over moment-to-moment HRV stress estimation)
  - **Vision off** (camera doesn't run during sleep — privacy + compute)
  - **BCI features shift to sleep-staging** rather than alertness markers

Sub-context further refines: **REM** elevates dream-recall preparation (sub-vocal detection); **Deep** sleep is minimal extraction; **Alert** waking is maximum cadence; **Working out** elevates HR/HRV + motion features.

**Evolution.** The architectural pattern absorbs new modalities by adding a new feature extractor + registering it. The FeatureSnapshot envelope is invariant; only the modality-specific payload changes. Migration target: centralize all L2 work in `apps/inference/features/` with per-modality submodules.

---

### Layer 3 — Fusion

**Job.** Take FeatureSnapshots from L2 and fuse them into the system's current per-axis representation of the user. Hold that representation as the truth-of-record for *now*. Expose it to downstream consumers (Regis, the UI, L4) through read-only interfaces.

It holds the most current, best-understood picture of the user — with honest representation, per dimension, of how current that picture actually is.

**State substrate — per-axis storage.** L3 holds state as a registry of independent axes. Each axis represents one dimension of the user (arousal, valence, focus, distress, social orientation, sleep_stage, etc.) and updates at its own cadence. For each axis, L3 stores:

| Field | Meaning |
|---|---|
| `value` | Current best estimate (scalar, vector, categorical — or the sentinel `OFFLINE`) |
| `timestamp` | When the fuser last wrote this axis |
| `confidence` | The fuser's confidence at that time |
| `source` | Which modality (or set of modalities) contributed |

No global tick. Each axis updates independently, with write cadence driven by its underlying signal sources. Modalities span three orders of magnitude in cadence (BCI ~1s through dream recall ~24h); per-axis storage represents each at its honest cadence.

> **Per-axis state is the truth-of-record.** Everything else L3 exposes — the BeliefState snapshot, composites, momentum — is derived from it.

**Fusion mechanism — Bayesian, with swappable prior.** L3 produces axis values by Bayesian combination of incoming FeatureSnapshots with a prior. Each modality contributes a likelihood; the fuser combines the prior with active likelihoods to produce a posterior. The posterior's mean is the new axis value; the posterior's variance becomes the new confidence.

Likelihoods are Gaussian by default. Per-axis combinator instances may use other distributions where the axis's nature requires it (categorical for sleep_stage, etc.); the architecture supports per-axis math.

The prior is a swappable input. Default: smoothed-recent from the bounded backward window. The fuser interface accepts an alternative prior source per axis — reserved for the predictive-coding loop, where L4's short-horizon forecast may replace smoothed-recent as the prior once L4 exists and per-axis behavior justifies it.

**Intent modulation — uniform ingestion, distinct axes.** Per commitment #10, every event carries an intent (Explicit / Continuous) and a modality. L3 honors this without exposing separate ingestion paths.

L3 only sees FeatureSnapshots. L2 wraps explicit events (a spoken sentence, a typed message, a deliberate gesture) into FeatureSnapshots that carry the `(intent, modality)` tag. The tag drives downstream weighting inside the fuser.

Continuous evidence updates *inferred* axes (e.g., `arousal_inferred`, `valence_inferred`). Explicit evidence updates *declared* axes (e.g., `state_declared`, `intent_declared`). The two coexist; consumers and composites may read either or both. L3 does not collapse them — an inferred reading and a declared reading are epistemically different facts.

Semantic content from explicit events (the actual words) stays in `chat_messages`. L3 holds state, not content. L2 extracts state implications and writes them to L3's declared axes; the words themselves persist in the existing chat tables and are read separately by downstream consumers that need them.

**Snapshot policy — the derived "current view" (BeliefState).** Most consumers (Regis especially) want a single current snapshot — one object that says "here's the state right now." This is the **BeliefState**: a view computed on demand from per-axis storage. It is not stored.

Each axis declares a freshness threshold (the window during which its last value is considered current) and a staleness behavior. Both are declared per-axis in fusion config — values are derived from the source's natural cadence and the consumer's tolerance, and may be personalized per user as data accumulates.

Staleness behaviors:
- **Decay** — report the last value with confidence reduced in proportion to staleness. *Default.*
- **Hide** — omit the axis; consumers see it as undefined.
- **Predict** — call L4 for a short-horizon forecast and mark the value as predicted. Opt-in per axis; creates a hard dependency on L4.

A BeliefState represents state at the moment of read; two reads milliseconds apart may differ. Consumers needing a stable view across a multi-step operation read once and cache for the operation's duration. Snapshot policy lives in L3 — reads do not take policy parameters.

**Backward window — bounded recent history.** L3 maintains a short rolling buffer per axis (seconds to minutes, axis-specific) to support smoothing, momentum derivation, prior construction (the fuser's default prior is smoothed-recent from this buffer), and immediate-past queries.

> **Hard boundary with L4.** L3 looks at the recent past only. Day-over-day comparisons, weekly rhythms, cyclical patterns all live in L4. The bound on L3's window is the architectural commitment that keeps the layers from collapsing into each other.

The buffer is internal — substrate for snapshot freshness, momentum, and priors. Not exposed as a separate read interface. Consumers either read the BeliefState or query L4.

**Composites — views, not storage.** Many user-meaningful states ("agitated," "in flow," "exhausted," "scattered") are combinations of primitive axes. These are views: pure functions over per-axis state.

A composite returns a value (boolean, scalar, label) computed from named primitive axes. Composites live in a named registry, consistent across consumers. Each declares: name, input axes, derivation rule, and (optionally) a confidence model over its inputs' confidences. They are not stored; they have no writer. The definition can evolve without backfill — changing the rule re-derives historical queries against the new rule.

> **If it has a writer, it's a primitive. If it's pure derivation from existing storage, it's a view.**

A state detected *directly* by an L2 process (e.g., a model trained on dissociation signatures) is a primitive axis — L2 writes it, L3 stores it. The same name treated as a composite (derived from arousal + attention) would be a view. The line is "is there a writer," not "does it feel emergent."

**Offline state — decay ≠ offline.** A modality going offline is a different epistemic object from a modality whose last reading is just old. L3 distinguishes them explicitly.

`OFFLINE` is a value type. Each axis holds either `(value, confidence, timestamp, source)` or the sentinel `OFFLINE`. L3 marks an axis OFFLINE when L2 sends an explicit "modality offline" signal, when L2's heartbeat stops arriving, or when L3 times out (no writes for N times the expected cadence).

When an input modality is OFFLINE, its likelihood is not included in the Bayesian product for any axis it contributes to. The posterior is computed from the prior and remaining modalities; the resulting confidence reflects the smaller input set.

On reconnection, L3 cold-starts the axis — the fresh value replaces OFFLINE without interpolation or gap-filling. L3 makes no claims about what happened during the gap, regardless of gap duration.

L3's writes to long-term storage include OFFLINE periods as such. Knowing when the system was blind is part of historical truth.

OFFLINE propagates up the stack:
- **L4** treats OFFLINE inputs as missing — either skips forecasts that depend on them or marks predictions as "partial inputs."
- **L5** policies are axis-aware about blindness — sleep cues that depend on physiological readiness do not fire when HRV is offline; Regis may switch to a "diminished mode" when enough state is unknown.
- **L6 / UI** renders OFFLINE distinctly from "known with low confidence" — the user can tell whether the system is uncertain or blind.

**Contract.**
- *Inputs:* `FeatureSnapshot {user_id, modality, intent, timestamp, features, confidence, meta_context}` from L2. Each snapshot writes to one or more axes (axis routing declared per-modality in fusion config). Writes are atomic per axis.
- *Outputs — three read paths:*
  1. **BeliefState read** — current view across all axes, with snapshot policy applied. Primary path for Regis and the UI.
  2. **Per-axis read** — raw state of a named axis, no policy applied.
  3. **Composite read** — computed value of a named composite.
- *L4 access:* L4 reads per-axis state (including the bounded backward window) for forecasting. L4 does not write to L3. When the predictive-prior hook is activated for a given axis, L3 reads L4's forecast as the fusion prior in place of smoothed-recent.

**Meta-context bias.** Per commitment #14, the active meta-context (`Waking` / `Sleep`) biases L3's fusion at every step. Implementation is faithful: distinct combinator functions per meta-context, each with its own active axes, feature inputs, and math. Dispatch is by context detection.

At meta-context transitions:
- Axes exclusive to the previous context freeze at last value, then become stale per snapshot policy.
- Axes exclusive to the new context come online cold; first values arrive when relevant signals appear.
- Shared axes continue under the new context's fuser.

Sub-contexts (REM, deep, alert, focused, etc.) further specialize the combinator's behavior within a meta-context.

**Evolution.** The architectural pattern absorbs new modalities and axes by registering them in the fusion config; the FeatureSnapshot ingestion path and per-axis storage shape are invariant. Migration target: replace the body-bridge L1→L3 shortcut (raw HR/HRV → user_state_estimate) with proper L2 features (heartpy/neurokit2 → FeatureSnapshot) consumed by L3's biometric likelihoods. See §11. Predictive priors per axis (L4 forecasts as Bayesian priors) become available once L4 exists and its forecasts demonstrably beat smoothed-recent.

**Open questions.**
- *Per-user calibration of freshness thresholds.* Defaults will be wrong for some users; personalization deferred until N > 1.
- *Confidence model for composites.* The combination rule (min, product, Bayesian) is deferred. Placeholder: minimum input confidence.
- *L3 writes to long-term storage.* Cadence and format of historical writes is a separate decision, likely tied to L4's needs.
- *Concurrency for transactional multi-axis writes.* Per-axis writes are atomic; multi-axis transactional writes aren't supported. Flag if needed.
- *Per-axis likelihood distributions.* The Gaussian default works for many physiological axes but breaks down for categorical or bimodal ones; per-axis distribution choice is open.

---

### Layer 4 — Prediction

*Status: TODO (the next focused conversation after L3).*

**Job (preview).** Take current `BeliefState` + recent state trajectory and produce forecasts of future state. Per yesterday's design conversation, prediction is **multi-faceted**:

- **Data prediction** — "what will HRV be in 30 min?" (regression on a sensor signal)
- **Context/state prediction** — "how will the user's overall state evolve — energy, arousal, focus, distress?" (multi-dimensional state trajectory; this is the most product-relevant)
- **Action prediction** — "will the user issue a command? engage with what?" (event prediction)

Each prediction type has its own model family. L4 will hold a registry of per-state-axis predictors.

Per commitment #13, L4 eventually models counterfactuals (*"if Regis acts X, predicted t+1 = ?"*). Meta-context bias selects which prediction models are active.

---

### Layer 5 — Decision

*Status: TODO.*

**Job (preview).** Take predictions + user-outcome history + current explicit input + meta-context and decide what action (if any) Regis takes. Routes by **intent** (per commitment #10) — explicit events dispatch as commands, continuous state updates feed posture decisions (Witness vs Companion mode per commitment #5).

Components today: the Thompson contextual bandit (`learned_decider.py`) is the seed. Eventually closes the treatment-effect estimation loop from commitment #13.

---

### Layer 6 — Output

*Status: TODO.*

**Job (preview).** Take the decision from L5 and emit it through the appropriate channel. Per commitment #3 (wisp-as-interface), audio is primary; UI/haptic/visual indicators are supplementary. Output channel selection is intent-dependent (commitment #10) and meta-context-biased (commitment #14 — no companion-mode TTS during deep sleep).

Components today: TTS via Kokoro (bone-conduction headphones), iOS chat UI rendering. Future: haptic, visual indicators.

---

## 4. Data architecture

*Status: TODO.* The Postgres schema is the integration spine. This section documents:
- Each significant table and what it holds (one line per)
- The polymorphic patterns (`kind` + `payload`, `source` discriminator, `model_owner` discriminator)
- The pgvector HNSW index over `embeddings` for semantic retrieval
- Freshness gates (e.g., 1-hour rule on `user_state_estimate`)
- Migration discipline (append-only, additive)

---

## 5. The three I-Models

*Status: TODO.* A deep dive on Daybook's most distinctive architectural concept (per commitment #4 in §2). All three live in `i_model_clusters` with a `model_owner` discriminator:

- **`user_self`** — discovered clusters of who the user is (HDBSCAN over user-side embeddings)
- **`regis_of_user`** — how Regis perceives the user (separate clustering namespace)
- **`regis_self`** — Regis's own current state (single projection row, nightly refreshed paragraph fingerprint)

How they're stored, how they're queried (cosine similarity for the first two, singleton read for the third), and why they exist as three distinct concepts rather than one merged model.

---

## 6. The sleep sub-system

Sleep is one of two meta-contexts the pipeline operates within (per commitment #14). Architecturally it's not special — every layer's behavior is biased by whether the meta-context is Waking or Sleep. **Operationally, however, sleep is one of Daybook's most important product surfaces:**

- The v1 validation wedge is *"≥50% improvement in weekly dream recall"*
- The product thesis centers on always-on companionship *"especially attentive at night, where it monitors sleep and gently intervenes in dream patterns"*
- A meaningful share of the codebase (classifier, sessions, dreams, cues, observer, witness persona) lives in the sleep domain

This section documents the sleep sub-system as a unified concept, mapping each component to its place in the layered architecture. Commitment #14 establishes the architectural principle (meta-context as cross-layer bias); this section provides the unified product view.

### Components of the sleep sub-system

| Component | Layer | Role |
|---|---|---|
| **Sleep classifier** | L4 (Prediction) | Trained XGBoost on biometric features; predicts REM/non-REM per epoch. Lives at `apps/inference/classifier/`. |
| **Sleep sessions** | L3 (Fusion) | Aggregated session boundaries (when sleep started/ended, duration, fragmentation). Stored in `sleep_sessions` table. |
| **Dream recall** | L1 (Sensors) + L5 (Decision) | Morning capture flow: user speaks/types dream → STT → `dream_recalls` table → embedding. Major product surface for v1 validation. |
| **Sleep cues** | L5/L6 (Decision/Output) | Gentle audio intervention during sleep (witness-mode TTS via bone-conduction). Gated by `cue_decision.py` safety rules. |
| **Sleep observer** | L3 (Fusion, post-mortem) | Nightly post-mortem of sleep session → writes `regis_observations`. Lives at `apps/inference/sleep_observer.py`. |
| **Witness persona** | L6 (Output) | Regis's sleep-mode posture — reverent, sparse, minimal. The L5/L6 corollary of meta-context #14 applied to Sleep. |

### Sub-contexts within Sleep

Per commitment #14, Sleep contains sub-contexts that further refine bias:

- **REM** — dream-active; potential intervention window for nightmare disorder, lucid dreaming, etc. Cues should be especially gentle.
- **Deep (Slow Wave Sleep)** — no cues; system in pure observation mode. Critical for recovery — interruption has measurable cost.
- **Core (Light NREM)** — limited intervention OK if gated by safety rules.
- **Awake in bed** — transitional; system may begin morning posture if duration suggests final waking.

Each sub-context biases L4 (which prediction model fires), L5 (what cues are allowed), and L6 (output gating).

### Why sleep gets its own section despite #14's elegance

Per architectural principle, sleep follows commitment #14 like any meta-context — not special-cased. But sleep is rich enough across the codebase that documenting it scattered across per-layer bias notes would obscure the sub-system. This section provides the unified view; commitment #14 + per-layer bias notes provide the architectural integration. Both are needed.

---

## 7. Where Regis runs

The deployment view — what runs where, today and in future phases.

### Today (v1)

- **Backend (the brain):** Python, running on the founder's Mac. All apps (`chat`, `wisp`, `inference`, `recall`, `api`) plus the always-on scheduler in `apps/daybook.py`. Started via `python -m daybook`.
- **Persistence:** Neon Postgres (cloud-hosted, PG 17 with pgvector).
- **Bridge to clients:** FastAPI server (`apps/api/`) on `localhost:8000`, exposed publicly via Cloudflare Tunnel at `https://daybook.koinelabs.com`.
- **Clients:** iOS app (iPhone + Apple Watch). Swift, native. Talks to the FastAPI bridge over HTTPS using an `X-API-Key` for auth. Never imports backend modules directly (per commitment #12).
- **Voice:** Codex backend (gpt-5.2) via the founder's ChatGPT login — used as a frozen LLM, no fine-tuning.
- **Embeddings:** BGE-M3 (1024-dim) running locally on the Mac (MPS-accelerated). Model cached at `~/.cache/huggingface/`.

### Soon (v1.5 — Pi takeover)

The Pi 4 takes over as the always-on backend host:
- Same Python code, just runs on the Pi
- Mac becomes a dev machine again
- Mic + bone-conduction audio I/O moves to the Pi
- Embedding compute may offload to the 24/7 desktop PC (NVIDIA 4080)

### Eventually (v3 — custom wearable)

The single-ear wearable form factor:
- BCI + audio + camera tether, all on-body
- Some inference moves on-device (Core ML / ONNX Runtime Mobile)
- Cloud / Mac / desktop still handles heavy lifting

### Constant across all phases (per commitment #9)

Same code path. v1 prototype IS the v3 substrate. The host changes; the architecture doesn't. Whatever works on the Mac today is what will run on the wearable — we just keep evolving the same codebase.

### Auth model

- `X-API-Key` header for all FastAPI calls coming through Cloudflare Tunnel
- Key lives in `.env.local` server-side and `Daybook-Local.plist` client-side (both gitignored)
- Loopback bypass: requests from `localhost` skip the key (so dev tools work)
- BUT middleware enforces the key whenever Cloudflare headers (`cf-connecting-ip` etc.) are present — prevents cloudflared-on-Mac from laundering unauthenticated requests through localhost (per commitment #12)

### Embedding compute trajectory

- **Today:** BGE-M3 on Mac MPS (~30-40s first call, ~200ms each subsequent)
- **Pi era:** BGE-M3 too heavy for Pi 4; embedding calls route to the 24/7 desktop PC over local network
- **Wearable era:** smaller distilled embedding model on-device, or cloud-served

---

## 8. Cross-cutting concerns

Things that touch multiple layers and don't fit cleanly into any one.

### The nightly scheduler

`apps/daybook.py` runs an `APScheduler` BackgroundScheduler with 11 jobs:

| Time | Job | What it does |
|---|---|---|
| 02:00 | `outcome_labeler` | Backfills `user_outcome` on past `interject_decisions` rows |
| 03:00 | `nrem_consolidation` | Distills yesterday's chat into `regis_observations` |
| 04:00 | `nightly_clustering` | HDBSCAN over embeddings → discovers/updates I-Models |
| 04:30 | `trait_decay` | Pulls trait dials toward learned baselines (half-life 90d) |
| 04:45 | `cluster_dormancy_sweep` | Marks clusters dormant after 60d of no activation |
| 05:00 | `rem_dreaming` | Pairs distant observations → produces dream-thoughts |
| 05:30 | `refresh_regis_self` | Synthesizes Regis's current self-portrait fingerprint |
| 07:30 | `morning_brief` | The good-morning utterance (surfaces overnight dreams) |
| 22:30 | `pre_sleep` | The wind-down utterance |
| Every 25 min | `inner_pulse` | Smart-gated proactive thought loop |
| Every 5 min | `body_state_estimate` | Live biometric → state translator (body-bridge) |

Jobs can fail independently without bringing the daemon down. The scheduler runs as part of the same Python process as the mic listener when both are active via `python -m daybook`.

### The interject decider

`apps/inference/interject/decider.py` is the brain of "should Regis speak right now?" — a small but real learning system:

- Multiple **triggers** (`morning_brief`, `pre_sleep`, `inner_pulse`, `post_recall`) each build a context and ask the decider for a verdict
- Default mode: **fixed-weight scoring** (receptivity / novelty / silence / time-of-day combined with hand-set weights, threshold 0.65)
- Optional mode (env-gated): **Thompson contextual bandit** in `learned_decider.py` that learns from outcomes — needs 50+ labels to activate; falls back to fixed-weight otherwise
- Every decision is persisted to `interject_decisions` (with feature snapshot)
- Every fired interjection eventually gets an outcome label (positive / neutral / negative / ignored) by the nightly `outcome_labeler` job
- The outcome → bandit update loop is the only "real" online learning in the system today

### Error handling philosophy

Three rules, applied throughout:

1. **Hot paths never crash on optional reads.** If `gather_substrate` can't fetch latest `user_state_estimate`, returns `None` and the prompt builder omits the section. No exception breaks the chat turn.
2. **Optional writes log + return.** Embedding a Regis utterance fails? Log a warning, return. The moment is still persisted; novelty just isn't logged this time.
3. **Required reads can raise.** If the LLM call genuinely fails (auth expired, network outage), the error propagates. Better a visible failure than silent wrong behavior.

Specifically: novelty logging, prosody capture, trait drift, observer extraction — all wrapped in try/except + log. The chat turn itself can crash if the LLM is unreachable.

### The substrate as single read point

`gather_substrate(user_id, query_embedding)` is the **one read** that fetches Regis's perception substrate for any moment — trait dials, active I-Models, current prosody, regis_self fingerprint, relevant observations, current user state.

Both the **chat handler** (responding to user messages) and the **wisp composer** (composing autonomous moments) call this same function. There are no parallel reader paths. Anything Regis sees comes through here.

Consequence: changes to what's in the substrate land in both code paths automatically. No drift between "what Regis-the-chatbot knows" and "what Regis-the-autonomous-agent knows."

### Observability

Honest current state:
- **Logs:** stdout/stderr via Python `logging`; captured by the host OS (systemd journal on Pi, Console.app on Mac)
- **DB introspection:** ad-hoc — connect to Neon, run SELECTs
- **No structured metrics yet:** no Prometheus, Grafana, or error-rate dashboards. Single-user scale = we debug from logs + DB queries
- **Future:** when scale demands, observability becomes its own layer — but premature for N=1

---

## 9. Evolution roadmap

*Status: TODO (sequenced after §3 layered design is agreed).*

A short list of what's *done*, *next*, and *later*. Lives here (not in `STATUS.md`) because it's about *architectural* evolution — the trajectory of capabilities, not the operational state of any one capability.

Expected structure:
- **Done** — major architectural milestones reached
- **Next** — what's currently being built or up next
- **Later** — known architectural moves on the horizon (BCI integration, MoE-style gating, vision modality, online learning loops, custom wearable hardware, etc.)

---

## 10. Open questions + references

*Status: TODO.* The honest list of what we don't yet know — design decisions deferred, labeling strategies undecided, evaluation harnesses unbuilt. Plus links to subsystem deep dives and per-feature design docs as they're written:

- `docs/Architecture/FUSION.md` (planned)
- `docs/Architecture/SENSING.md` (planned)
- `docs/design/<feature>.md` (per-feature, as-needed)

---

## 11. Implementation gap index

Known architectural divergences between this ideal and current code. Each entry is a one-line pointer; see `STATUS.md` and Issue #2 for detail.

This index is the **bridge between ARCHITECTURE.md (ideal) and STATUS.md (reality).** The bodies of all sections above describe what the system should be; this index acknowledges what hasn't caught up. **When a gap closes, its line is removed from this index** — the doc body never has to be edited.

### Storage and persistence gaps

- **Sleep classification storage:** Apple's `sleep_stage` rows currently land in `sensor_readings` (HK storage convenience). Ideal: upstream state in `user_state_estimate` or dedicated state table.
- **Multiple sleep storage locations:** `sensor_readings.sleep_stage` + `sleep_sessions` + `user_state_estimate.stage_proba` all hold sleep data. Ideal: one canonical home per concept.
- **`sensor_readings` is a misnomer:** holds raw L1 signals AND L2 features AND pre-classified state from third parties. Ideal: separation by conceptual layer.

### Layer-implementation gaps

- **L2 not centralized:** signal processing scattered across modality-specific modules (mic listener for prosody, `embeddings/` for text, `classifier/` for biometrics). Ideal: `apps/inference/features/` as the single home with per-modality submodules.
- **Body-bridge L1→L3 shortcut:** body-bridge reads raw HR/HRV from L1 and applies heuristics directly. Ideal: formal L2 features (heartpy / neurokit2) producing FeatureSnapshot → L3 fusion.
- **Fusion engine doesn't exist as a separate concept:** today the substrate reads scattered data + body-bridge is the only synthesizer. Ideal: dedicated L3 fusion engine that combines all modality features into a unified `BeliefState`.
- **L4 (Prediction) has no components:** zero predictive heads exist. Ideal: per-state-axis predictors (arousal at t+30min, REM probability, sleep onset, etc.).
- **Meta-context biases not implemented at L2–L4:** commitment #14 declares cross-layer biasing; today only L5/L6 (persona — Witness vs Companion) honors this. Ideal: every layer applies meta-context bias.

### Modality coverage gaps

- **Vision ingestion:** ⚪ unimplemented (ESP32-CAM available).
- **BCI ingestion + features:** ⚪ unimplemented (BioAmp EXG Pill incoming).
- **Deliberate gestures:** ⚪ schema in `user_actions`, no ingestion code yet.
- **Involuntary gestures (EMG/EOG):** ⚪ unimplemented — needs BCI hardware or vision.

### Learning gaps

- **Online learning loops:** only the Thompson bandit learns from data; no other components improve over time. Ideal: every predictor + decider learns from outcomes.
- **No labeled training data pipeline:** future trained models require labels; no auto-labeling infrastructure exists. Ideal: multi-modal-LLM auto-labeling pass + self-report capture.
- **Treatment-effect estimation (commitment #13):** bandit is the seed but counterfactual reasoning ("if Regis does X, predicted t+1 = ?") isn't implemented yet. Ideal: forward-looking decision models.

### Documentation gaps

- **Smoke tests for trait_decay + cluster_dormancy:** convention from CLAUDE.md says "smoke test before declaring done" — these nightly jobs ship without them.
- **Subsystem deep-dive docs** (`docs/Architecture/FUSION.md`, etc.): planned but unwritten.


## How this document gets written

This outline is committed as **v0.1**. Each section will be filled through ongoing design conversation, in roughly this order:

1. §6 + §7 (Where Regis runs, Cross-cutting concerns) — mostly describing what exists; quick to draft
2. §2 (Architectural commitments) — migrating from `CLAUDE.md` and expanding the *why*
3. §3 (The layered design) — **the focused conversation; the heart of the doc**
4. §4 + §5 (Data architecture, Three I-Models) — descriptive once §3 is settled
5. §8 (Evolution roadmap) — derives naturally from §3 sequence
6. §1 (System at a glance) — written last, summarizes everything above
7. §9 (Open questions) — captured along the way

Section by section, committed as v0.2, v0.3, etc. The document is **never declared "done"** — it evolves with the system. Major architectural moves trigger an update; minor changes don't.
