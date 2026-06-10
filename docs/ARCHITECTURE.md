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

**Tension with commitment #6 (acknowledged).** The dual-mode binary is a v1 framing — useful because it ships, matches product intent, and maps cleanly to the two meta-contexts. Real Regis postures over time will be richer than a binary (morning-groggy, post-conflict-careful, social-quiet, walking-curious, alert-focused, anxious-comforting). The destination is **posture as a discovered axis on `regis_self`** — analogous to user-side I-Models, emerging from accumulated context+utterance+outcome data rather than pre-defined enums. Until that discovery substrate is online, the binary is the right shippable surface; afterward, modes become discovered postures and #5 is superseded by #6's pattern applied to Regis.

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

**Rule.** Every input event is classified along two orthogonal axes at the L1 ingestion boundary. Intent is assigned at the **edge** — by the capture client / channel through which the event arrives (wake-word detector, chat endpoint, gesture recognizer, sensor sync path) — before the event reaches L1 storage. L1 itself does not derive intent from raw signal; it receives pre-tagged events.

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

**Status: audio stream live (Week 3, 2026-05-28).** `apps/inference/audio_context/` implements the audio half of this rule. One always-on mic stream (`apps/voice/loop.py::listen_continuous`) extracts VAD → speaker identity (`speaker_id.py`) → prosody, and (optionally) YAMNet ambient classes, emitting semantic packets — `audio_social_context`, `audio_prosody`, `audio_ambient` — via `audio_context/writer.py`. **Raw audio is never persisted**; only the semantic packets land in `sensor_readings`. Full STT remains triggered-escalation (wake-word → `transcribe_streaming`), never continuous. YAMNet is a lazy, optional, fail-soft backend so the heavy TF dep can't gate the core pipeline. Privacy Policy #1 (see §8 / commitment below) is enforced by a pure state machine (`audio_context/privacy.py`) the loop consults *before* any prosody/ambient write — non-self voice yields only a presence marker plus a 30s suppression buffer, and an un-enrolled (`unknown`) speaker fails safe to suppression.

**Canonical HealthKit storage (post-0009).** Apple Health is a third-party semantic stream and follows the same `sensor_readings` polymorphism. Its single canonical writer is `bin/sync_hk_export.py`, emitting the `apple_health_*` kind namespace (`apple_health_hr`, `apple_health_hrv`, `apple_health_spo2`, `apple_health_respiratory_rate`, `apple_health_temperature`, `apple_health_sleep_stage`). The v0 importer `parse_apple_health.py` is deprecated/disabled; `sleep_sessions` + `sleep_stage_classifications` are frozen classifier-training data, not the live store. Each write stamps `consent_scope` (`apple_health_v1` / `mac_activity_v1`) per `apps/inference/consent.py` — this is the capture-side audit trail the 0009 consent columns were added for.

### 12. Native clients talk to FastAPI, never brain modules directly

**Rule.** iOS, watchOS, and any future client speaks HTTP to `apps/api/`. They never import `chat`, `recall`, `wisp`, etc. The bridge is the seam. Auth via `X-API-Key` with loopback bypass.

**Why.** Direct module imports across language boundaries (Swift → Python) couple platforms together and break independent evolution. The FastAPI bridge enforces a clean contract: backend evolves in Python, clients evolve in their native stack, the API is the only thing that needs versioning. Auth and tunnel concerns are isolated at the bridge.

### 13. Outcome-driven action selection

**Rule.** Regis's discrete-action choices (interject vs not, witness vs companion, content kind A vs B) are learned from observed outcomes via online learning. The Thompson contextual bandit (`learned_decider.py`) is the v1 mechanism; the pattern generalizes — any time L5 picks among finite options, the choice is informed by outcome labels accumulated over time. Every fired decision gets persisted with its feature snapshot; outcomes are labeled by nightly jobs; the bandit (or successor) updates from these labels.

**Why.** Hand-coded action rules don't adapt to the specific user. Outcome-driven selection lets the system improve at picking the right discrete action without explicit retuning — and provides the substrate of paired (action, outcome) data that the modeled-influence commitment (#15) eventually consumes.

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

**Canonical writer.** The active `meta_context` is itself a categorical axis in L3 (see §3 Layer 3 / Meta-context bias). L3 fuses it from sleep-classifier output, activity signals, and temporal context, and applies hysteresis to avoid rapid flipping. Every other layer (and L3's own per-axis fusers) reads `meta_context` from L3. There is one canonical writer and one canonical read point — no implicit chicken-and-egg.

**Why.** Human cognition doesn't process inputs uniformly across all states. Background hum during deep sleep doesn't trigger attention; the same hum during alert work might. A system that flattens this — treating sleep as just another state dimension — fails to mirror how perception actually works. Meta-context as a cross-layer bias means every component naturally asks "how do I behave differently in this mode?" — and Regis's voice, perception, and decisions stay coherent across phases of the user's day.

**Relationship to existing commitments.**
- Commitment #5 (Regis dual-mode: Witness vs Companion) is the L5/L6 *corollary* of this commitment, scoped to persona/output.
- Commitment #11 (semantic-first continuous sensing) is the L2 *foundation* — semantic packets carry the meta-context-relevant features at low cost.
- Commitment #4 (Three I-Models) — the `regis_self` model's mode field is one expression of meta-context propagation.

**Lineage.** Added 2026-05-21 PM. Identified during §3 layered-design conversation when the user observed that sleep isn't a state variable within the pipeline — it's a meta-context that biases the entire pipeline.

### 15. Regis as a modeled controlled variable in state prediction

**Rule.** Beyond outcome-driven action selection (commitment #13), the system eventually models how Regis's actions causally shape user-state trajectories — "if Regis says X vs Y vs stays silent, predicted state at t+1 differs by Z." This is causal inference / treatment-effect estimation territory, distinct from action selection. The L4 `predict(axis, horizon, action)` interface preserves this destination from day one via the optional `action` parameter; v1 implementations may return naïve action-conditioning placeholders, evolving toward proper causal modeling as data accumulates.

**Why.** An empath that only reacts to past outcomes (commitment #13) can never reason "if I do this differently, the user's trajectory changes." That counterfactual reasoning is the difference between learning-from-outcomes and modeling-influence. Conflating it with #13's action selection obscures the architectural choice: action selection works at N=1 with light data; influence modeling needs accumulated paired (action → state-change) data across many similar contexts, or explicit experimentation, or a causal model. Different data requirements, different evaluation strategies, different failure modes — splitting the commitment makes that explicit.

**Relationship.** Commitment #13 produces the substrate (paired action-outcome data from every fired decision); commitment #15 consumes it (estimating Regis's actual influence on state). The two compose: outcome-driven selection improves which actions Regis takes; influence modeling improves how Regis reasons about what those actions will do.

**Lineage.** Split from the original commitment #13 (2026-05-22) after independent review noted that "Regis as controlled variable" conflated discrete action selection with continuous influence modeling — different architectural bets with different data needs. Refined 2026-05-24 to point at commitment #16 (JEPA-family world model) as the architectural substrate that makes the destination implementable — v1 naïve action-conditioning placeholders compose into the world model's action-conditioning branch as data accumulates, rather than being thrown away.

### 16. Prediction operates in latent space (JEPA-family world model)

**Rule.** L4 predictors implement the **Joint Embedding Predictive Architecture (JEPA)** pattern: an **encoder** maps observations to a compact latent state; a **predictor** forecasts future latent state conditioned on an optional action embedding; and consumers compare/plan in latent space rather than in raw signal space. The v1 implementation target is the **LeWM recipe** ([le-wm.github.io](https://le-wm.github.io/)): ~15M parameters, single-GPU end-to-end training, two losses (latent prediction + **SIGReg** Gaussian regularizer), Cross-Entropy Method planning over candidate actions. No pretrained encoders are required — the architecture trains stably from scratch.

This is an architectural-shape commitment, not a library lock-in. Variants of JEPA that satisfy the same invariants (latent-space prediction, action conditioning, anti-collapse regularization, planning-by-rollout) substitute freely; the invariants are the lock.

**Why.** Prediction in raw signal space (next HR value, next pixel, next sample) wastes capacity on detail the system doesn't need and can't usefully act on. Prediction in latent space — embeddings that capture *meaning* — focuses capacity where signal-to-noise is highest, and aligns prediction with how the rest of the system already represents the user (clusters of embeddings, semantic packets, fused per-axis state). The encoder/predictor split also gives a natural insertion point for action conditioning: the predictor reads `(current latent state, action embedding) → predicted next latent state`, which is precisely what commitment #15 (Regis as modeled controlled variable) requires to ever become real.

LeWM specifically is chosen as the v1 target because it solves the collapse problem (the historical reason hobbyist JEPA implementations fail: the encoder discovers it can trivially "predict" the future by outputting a constant) with a single-knob regularizer (SIGReg, forcing latent embeddings to a Gaussian distribution), runs end-to-end on a single GPU at small parameter counts, and bundles all three pieces an empath needs — encoder, action-conditioned predictor, planner — in one published recipe.

**Cross-layer implications.**

- **L2 — Encoders.** Where L2 already has its own representational outputs (BGE-M3 text embeddings, biometric feature vectors, future BCI bandpower vectors), JEPA training generalizes as a self-supervised objective: predict next embedding from current. **SIGReg** generalizes as the anti-collapse regularizer for any L2 encoder trained on the Daybook signal flow.
- **L3 — Latent state.** Per-axis state in L3 remains the truth-of-record for downstream reads (commitment #4, commitment #14 dispatch). Under #16, L3 axes may also be expressible as projections of a unified latent state (the world model's encoder output). v1 keeps per-axis storage; the unified latent representation is consumed by L4 for prediction and (in v2) by L5 for planning, not stored as L3 state.
- **L4 — Predictors.** Predictors implement JEPA: encoder + action-conditioned predictor + per-axis projection heads. Training is end-to-end via latent-space prediction loss + SIGReg, not direct ground-truth axis regression. Axis-level calibration happens at the projection heads (against `user_state_estimate` history). Multiple `(axis, meta_context)` registry entries may share an underlying world model, with the registry routing to axis-specific heads.
- **L5 — Planning.** Action selection in v2 uses CEM (or equivalent rollout-based) planning over the world model: sample candidate Regis actions, query L4 with each, compare predicted next-state embeddings against goal-state embeddings, pick the action whose predicted trajectory best matches the goal. The Thompson bandit (commitment #13) remains v1; the transition to world-model planning happens per-axis as the action-conditioning branch becomes calibrated.
- **L6 — Surprise/novelty.** A JEPA world model produces a natural **prediction-error signal** — actual next embedding vs predicted next embedding. High prediction error = novelty/surprise = an event worth Regis attending to. This becomes the foundation for "what should Regis notice," replacing today's hand-tuned threshold rules.

**Relationship to existing commitments.**

- **#6 (Self-expanding I-Models)** — Same architectural family: representations of the user are *discovered* from data, not pre-specified. #6 covers the *static structure* of those representations (clusters of embeddings); #16 covers their *dynamics* (how they evolve over time and respond to Regis's actions). Together they describe a unified empath substrate.
- **#11 (Semantic-first continuous sensing)** — Both commitments share the bet that meaning lives in latent space, not signal space. #11 is the *capture-side* bet (extract semantic packets, discard raw); #16 is the *prediction-side* bet (model the future in latent space, not raw).
- **#13 (Outcome-driven action selection)** — Produces the paired (action, outcome) data the JEPA world model consumes for training its action-conditioning branch. #13 is the v1 mechanism (Thompson bandit); the world-model planner (#16) is the v2 successor.
- **#15 (Regis as modeled controlled variable)** — #16 specifies the *architectural shape* that makes #15's destination implementable. #15 is the goal (treatment-effect estimation); #16 is the predictor architecture that produces those counterfactuals.
- **#9 (Continuous build, not phased)** — #16 honors #9 by committing to the v3-substrate architecture from day one. v1 predictors are scaffolds that compose into the world model as data accumulates, not throwaway placeholders.

**What v1 looks like.** The full LeWM stack is not built tomorrow. v1 predictors land as per-axis regression heads (per the L4 registry pattern) with the *interface* shaped for the world-model destination: every prediction call already accepts an action argument; every prediction is logged with provenance distinguishing learned-counterfactual from hand-set-placeholder; every predictor's training pass reads the same `prediction_log` substrate. The encoder/predictor/SIGReg machinery lands once enough multimodal (state, action, next-state) triples exist to train it — likely 4–8 weeks of real interaction data. Until then, the architecture-shaped scaffolding generates the data flywheel that the world model consumes.

**Lineage.** Added 2026-05-24 after independent research surfaced LeWM (le-wm.github.io) as a practical, single-GPU, end-to-end JEPA recipe that resolves the historical collapse problem with a single regularizer. Before #16, commitment #15 specified the destination (modeled influence) without committing to architectural shape; v1 implementations would have defaulted to per-axis regression with hand-tuned action-conditioning, which doesn't compose into the world-model substrate the destination requires. #16 locks in latent-space prediction as the architectural shape from day one, so v1 placeholder implementations evolve naturally toward the JEPA destination rather than being thrown away. The decision converges with #6 and #11 — Daybook independently arrived at JEPA-shaped commitments because *any* always-on empath substrate that processes continuous biometric signal converges on "predict in latent space, not signal space."

### 17. Labels are provenance-scoped priors, not truth by default

**Rule.** Every label-like datum carries provenance. The system must distinguish ground truth, self-report, observed outcome, heuristic pseudo-label, literature prior, demographic prior, LLM literature bootstrap, and future clinician/expert label. These sources may all help training, calibration, or cold-start behavior, but they are not epistemically equal and must not be mixed as if they were the same kind of truth.

**Why.** Daybook needs labels before it has months of personal data, especially for a new user. Literature-derived findings and LLM-extracted research summaries can provide a useful starting map: blink-rate ranges associated with attentional state, HRV-arousal relationships, EEG bandpower patterns, prosody-affect correlations, sleep-stage feature distributions, and so on. Demographic baselines can refine that starting map when the user explicitly provides or consents to those attributes. But none of that says what this specific person is experiencing in this specific moment. Treating priors as truth would make the system confidently wrong; treating them as provenance-scoped priors lets the system be useful on day one while still learning the person.

**Cold-start policy.** A new user starts with a blend of: population priors from literature and validation cohorts, optional demographic priors, device/session calibration, and user-provided onboarding facts. As personal evidence accumulates — self-reports, observed outcomes, Apple Health history, repeated sensor patterns, and Regis-action outcomes — each axis shifts from population-weighted to person-weighted. The mixing weight is per-axis and is itself part of the model state.

**LLM/literature extraction.** LLMs may be used to extract candidate label rules from papers, datasets, and validated domain references. Those outputs land as `LLM_literature_bootstrap` priors or pseudo-label generators, not as final labels. Each extracted rule must retain citation/provenance, target axis, applicable population, confidence, and known limits. Promotion from pseudo-label rule to training signal requires validation against instrumented, self-reported, or outcome-based evidence.

**Demographic baselines.** Demographics are allowed only as opt-in, provenance-marked priors or uncertainty modifiers. They cannot hard-classify a user's internal state, cannot override personal data, and must be auditable because they carry bias and fairness risk. The architecture's default direction is: demographics help initialize uncertainty; personal signal replaces them.

**Training implication.** L3 fusion and L4 prediction training weight labels by provenance and confidence. Instrumented ground truth and explicit self-report are high-value calibration sources; observed behavioral outcomes train action selection and counterfactual branches; literature/LLM/demographic labels provide cold-start priors and weak supervision. The label record must preserve `axis`, `value`, `confidence`, `source`, `provenance`, `consent_scope`, and `created_at` so downstream models can decide how much to trust it.

**Lineage.** Added 2026-05-30 after the labeling/cold-start design discussion: the user proposed LLM-extracted literature labels as a baseline, with demographic baselines once enough data exists. The commitment locks in the safe version of that idea: use them early, but keep their provenance visible and let personal evidence supersede them.

### Commitment review process

Commitments are inviolable rules new code must honor, but they are not immutable. They may be **split** (as #13 → #13 + #15 in v0.8), **refined** (clarified scope, sharper rule), or **superseded** (replaced by a different formulation) when:

- A focused design conversation surfaces a flaw or internal contradiction.
- Independent review (outside readers, post-mortem analysis) demonstrates the commitment misrepresents the system.
- Implementation experience proves the commitment unworkable in practice.

When a commitment changes, the change is recorded in a **Lineage** note at the bottom of the commitment with date and brief reason. Numbering is preserved — refined commitments keep their number; split commitments retain the original number for the most direct successor and assign new numbers (taken from the end of the list) for new offshoots. Superseded commitments are kept in the doc with a `Superseded by #N` header rather than deleted, so the lineage is traceable.

Retirement (full removal) is rare and explicit — only when a commitment is no longer architecturally meaningful (e.g., it described a transitional state that has been fully replaced). Retired commitments move to a Lineage appendix rather than being deleted.

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

**Job.** Ingest events from intent-tagged input channels; persist as discrete rows. Intent tagging happens at the edge (wake-word detectors, chat endpoints, gesture recognizers, sensor sync paths) before events reach L1 storage. L1 itself performs schema normalization and persistence; it does not derive intent from raw signal, and it does not perform per-modality feature extraction (that is L2's job).

**Edge intent classification.** Intent (Explicit vs Continuous) is determined by the channel through which an event arrives, not by post-hoc analysis at storage time. Each input channel has a known intent declared by its capture client:

- chat API → explicit text
- wake-word-gated voice → explicit speech
- ambient mic listener → continuous voice (prosody, environmental audio)
- HealthKit sync → continuous biometric
- deliberate gesture detector → explicit gesture
- ambient camera → continuous vision (scene, presence)
- involuntary biometric (blink, jaw clench, EMG) → continuous gesture

The detectors that route signals into these channels — wake-word models, VAD/diarization, gesture classifiers, etc. — live at the **edge** (in capture clients, mic listeners, gesture recognizers). They are part of the L1 ingestion path but logically distinct from L1 storage. L1 receives pre-tagged events; it does not re-classify them.

**Two-axis classification (per commitment #10):**

Every event has both an intent and a modality:

| | Voice | Text | Gesture | Biometric | Audio (non-voice) | Vision | BCI |
|---|---|---|---|---|---|---|---|
| **Explicit** | Spoken-to-Regis | Typed chat | Pinch / nod / wave | — | — | Looking-at-camera | — |
| **Continuous** | Background mumble | — | Blink / jaw clench | HR / HRV | Room prosody | Scene / presence | EEG / EOG / EMG |

Storage: intent determines the table; modality determines the row's `kind` (or content):
- **Explicit** → `chat_messages` (voice/text), `user_actions` (gestures)
- **Continuous** → `sensor_readings` (polymorphic via `kind`: `heart_rate`, `hrv`, `audio_context`, future `eeg_packet`, etc.)

**Contract.**
- *Inputs:* hardware/user events from edge capture clients, each arriving pre-tagged with `(intent, modality)` by the channel they came through.
- *Outputs:* persistent rows in event tables, each carrying `(intent, modality)` via destination table + `kind`.
- *Cadence:* per-event. No fixed clock; driven by source.
- *Interpretation:* schema normalization and persistence only. Modality-specific feature extraction (Whisper STT on explicit speech, prosody features on continuous audio, etc.) happens at L2.

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

**State substrate — per-axis storage.** L3 holds state as a registry of independent axes. Each axis represents one dimension of the user (arousal, valence, focus, distress, social orientation, sleep_stage, `meta_context`, etc.) and updates at its own cadence. For each axis, L3 stores:

| Field | Meaning |
|---|---|
| `value` | Current best estimate (scalar, vector, categorical — or the sentinel `OFFLINE`) |
| `timestamp` | When the fuser last wrote this axis |
| `confidence` | The fuser's confidence at that time |
| `source` | Which modality (or set of modalities) contributed |

No global tick. Each axis updates independently, with write cadence driven by its underlying signal sources. Modalities span three orders of magnitude in cadence (BCI ~1s through dream recall ~24h); per-axis storage represents each at its honest cadence.

> **Per-axis state is the truth-of-record.** Everything else L3 exposes — the BeliefState snapshot, composites, momentum — is derived from it.

**Fusion mechanism — deterministic combiners (v1), Bayesian evolution (v2).** L3 produces axis values via per-axis combiners. Each axis has a registered combiner that reads its input FeatureSnapshots and produces a value plus a confidence number.

**v1 — deterministic combiners with declared confidence.** Each combiner is an explicit rule: weighted aggregation of inputs with declared weights, threshold logic, or simple state machines for categorical axes. Confidence is a *declared property of the rule under varying input conditions* — for example, "confidence 0.7 if all inputs fresh and within expected ranges; 0.4 if one input missing; 0.2 if inputs disagree beyond threshold." Confidence is not derived from probability theory in v1; it is a calibration the rule author specifies. Downstream consumers should read v1 confidence as a hand-set quality signal, not a posterior probability.

**v2 — Bayesian combiners (per-axis, deferred).** Once per-axis calibration data accumulates (paired observation-and-truth data from self-report, dream recall, or external reference), individual axes can migrate to Bayesian combiners that derive posterior distributions from per-modality likelihood functions. In this regime, confidence becomes posterior variance and uncertainty arithmetic is honest end-to-end. Migration happens **per-axis**, not all-at-once — some axes (those with cleaner ground truth) reach v2 sooner than others. v1 and v2 combiners coexist within the same L3 instance.

**Hierarchical priors for v2.** v2 priors are constructed hierarchically rather than personal-only:

- **Population priors** come from published literature (HRV-arousal correlations, sleep-stage feature distributions from PSG studies, prosody-emotion baselines), validation cohorts, and demographic baselines. These give v2 a sensible starting prior at zero personal data.
- **Personal priors** come from per-user data accumulated through the prediction-log learning loop, plus pre-existing historical imports (the user's Apple Health history, prior wearable exports). Aakash's 10-year Apple Health import is treated as calibration substrate — not just historical record — for axes where it provides ground-truth signal (sleep stage, HR/HRV-derived arousal, activity-derived energy).
- **Migration is gradual.** A v2 axis starts predominantly population-priored and shifts toward personal as data accumulates. Mixing weight is per-axis and reflects how informative each source is for that axis.

This is what makes v2 *shippable* rather than aspirational. Without hierarchical priors, v2 requires months of per-user calibration before any axis can migrate. With them, an axis migrates as soon as a credible population prior exists and enough personal data is available to refine it.

**Prior sources by axis (illustrative).** Each axis declares its prior sources in the fusion config:

| Axis | v1 prior source | v2 prior source |
|---|---|---|
| `arousal_inferred` | smoothed-recent | HRV literature (population) + Apple Health 10y baseline (personal) |
| `sleep_stage` | smoothed-recent (categorical) | PSG validation studies (population) + HK sleep labels (personal) |
| `valence_inferred` | smoothed-recent | prosody-emotion literature (population) + accumulated paired data (personal) |
| `attention_inferred` | smoothed-recent | blink-rate / EOG / EEG attention literature (population) + per-session calibration (personal) |
| `meta_context` | smoothed-recent (categorical, hysteresis) | sleep + activity feature distributions from prior cohorts (population) + user's own history (personal) |

**Source-set fusion evaluation.** EEG+EOG is not architecturally special — it is one source set among many. The same evaluation pattern applies to `EEG`, `EOG`, `ECG_watch`, `mic`, `EEG+EOG`, `EOG+mic`, `EEG+ECG_watch`, `EEG+EOG+mic`, and any future modality combination. Live L3 fusers should not brute-force every permutation on every tick. Instead, an offline fusion-ablation harness enumerates candidate source sets against provenance-scoped labels and proxy outcomes, measures whether the combination improves calibration or prediction beyond its individual components, and only promotes the useful combinations into live fusers. The desktop PC/GPU is the right place for this search; the Pi/Mac hot path reads the promoted rules.

**Swappable combinator slot.** The architectural shape (per-axis storage, snapshot policy, combinator interface) is invariant across v1 and v2. Migrating an axis from deterministic to Bayesian is a swap of the combinator implementation behind the existing interface — no external contract change for consumers.

**Swappable prior input.** Each combiner accepts a prior. Default in v1: smoothed-recent from the bounded backward window. Default in v2: the hierarchical-prior blend described above. A future predictive-coding integration — L4's short-horizon forecast as prior — is supported per axis as an additional opt-in alternative, available once L4 exists and per-axis behavior justifies it.

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

When an input modality is OFFLINE, the combiner excludes it from the axis computation. In v1 (deterministic combiners), this means the rule operates on remaining inputs with a declared confidence-reduction for the missing modality. In v2 (Bayesian combiners), the OFFLINE modality's likelihood is omitted from the posterior product, and confidence narrows naturally with fewer informative inputs.

On reconnection, L3 cold-starts the axis — the fresh value replaces OFFLINE without interpolation or gap-filling. L3 makes no claims about what happened during the gap, regardless of gap duration.

L3's writes to long-term storage include OFFLINE periods as such. Knowing when the system was blind is part of historical truth.

OFFLINE propagates up the stack:
- **L4** treats OFFLINE inputs as missing — either skips forecasts that depend on them or marks predictions as "partial inputs."
- **L5** policies are axis-aware about blindness — sleep cues that depend on physiological readiness do not fire when HRV is offline; Regis may switch to a "diminished mode" when enough state is unknown.
- **L6 / UI** renders OFFLINE distinctly from "known with low confidence" — the user can tell whether the system is uncertain or blind.

**Historical persistence.** L3 writes every axis update to long-term storage as a side effect of fusion. Each write is one row in `user_state_estimate` carrying the per-axis shape — `(axis, timestamp, value, confidence, source, meta_context)` — same as in-memory state. The table is per-axis-row, not per-snapshot: there is no synchronized "all axes at once" row. This mirrors L3's in-memory architecture, where per-axis state is the truth-of-record both live and in history.

Historical BeliefStates are reconstructed by selecting the latest row per axis at-or-before the target time. Consumers (primarily L4 for long-horizon forecasting) issue these queries directly against `user_state_estimate`.

OFFLINE values persist as such — the historical record honestly reflects when the system was blind, not just what was known.

**Contract.**
- *Inputs:* `FeatureSnapshot {user_id, modality, intent, timestamp, features, confidence, meta_context}` from L2. Each snapshot writes to one or more axes (axis routing declared per-modality in fusion config). Writes are atomic per axis.
- *Outputs — three read paths:*
  1. **BeliefState read** — current view across all axes, with snapshot policy applied. Primary path for Regis and the UI.
  2. **Per-axis read** — raw state of a named axis, no policy applied.
  3. **Composite read** — computed value of a named composite.
- *Side-effect writes:* every axis update is persisted to `user_state_estimate` (see *Historical persistence* above).
- *L4 access:* L4 reads in-memory per-axis state (including the bounded backward window) for short-horizon forecasting, and reads `user_state_estimate` for longer-horizon historical state. L4 does not write to L3. When the predictive-prior hook is activated for a given axis, L3 reads L4's forecast as the fusion prior in place of smoothed-recent.

**Meta-context bias.** Per commitment #14, the active meta-context (`Waking` / `Sleep`) biases L3's fusion at every step.

**`meta_context` is itself a categorical axis in L3** — fused from sleep-classifier output, activity signals, and temporal context. L3 owns its production; every other layer (and L3's own per-axis fusers when biasing themselves) reads `meta_context` from L3's per-axis state. This closes the loop: there is one canonical writer for "what mode is the user in," and one canonical read point.

L3's meta-context fuser runs first in each fusion cycle; other axes' fusers read the current `meta_context` value to select their per-context combinator.

**Hysteresis on transitions.** `meta_context` does not flip on single observations. The fuser requires sustained signal change (window-and-threshold per direction — falling asleep commits more slowly than waking) to avoid rapid mode-switching during boundary periods (drowsy-but-not-asleep, awake-but-still-in-bed). Boundary periods themselves can be represented as sub-contexts.

Implementation is **faithful per-context**: distinct combinator functions per `meta_context` value, each with its own active axes, feature inputs, and math. Dispatch is by `meta_context` axis read.

At meta-context transitions:
- Axes exclusive to the previous context freeze at last value, then become stale per snapshot policy.
- Axes exclusive to the new context come online cold; first values arrive when relevant signals appear.
- Shared axes continue under the new context's fuser.

Sub-contexts (REM, deep, alert, focused, awake-in-bed, etc.) further specialize the combinator's behavior within a meta-context.

**Evolution.** The architectural pattern absorbs new modalities and axes by registering them in the fusion config; the FeatureSnapshot ingestion path and per-axis storage shape are invariant.

Migration targets:
- Replace the body-bridge L1→L3 shortcut (raw HR/HRV → `user_state_estimate`) with proper L2 features (heartpy/neurokit2 → FeatureSnapshot) consumed by L3's biometric combiners. See §11.
- Per-axis migration from deterministic v1 combiners to Bayesian v2 combiners as calibration data accumulates per axis (paired observation-and-truth data from self-report, dream recall, or external reference).
- Predictive priors per axis (L4 forecasts replacing smoothed-recent as combiner priors) become available once L4 exists and its forecasts demonstrably beat smoothed-recent.

**Open questions.**
- *Per-user calibration of freshness thresholds.* Defaults will be wrong for some users; personalization deferred until N > 1.
- *Confidence model for composites.* The combination rule (min, product, Bayesian) is deferred. Placeholder: minimum input confidence.
- *Declared vs inferred conflict resolution.* When a declared axis (e.g., `arousal_declared` via "I'm fine") contradicts the corresponding inferred axis (e.g., `arousal_inferred` from HRV), the resolution policy lives at L5, not L3. L3 surfaces both faithfully; downstream decides what Regis does with the conflict.
- *Concurrency for transactional multi-axis writes.* Per-axis writes are atomic; multi-axis transactional writes aren't supported. Flag if needed.
- *Per-axis likelihood distributions.* The Gaussian default works for many physiological axes but breaks down for categorical or bimodal ones; per-axis distribution choice is open.

---

### Layer 4 — Prediction

**Job.** Take BeliefState + recent state trajectory from L3 (and historical fused state from `user_state_estimate`) and produce forecasts of future state. Forecasts serve L5's decision math primarily; L3 consumes forecasts as predictive priors when its swappable-prior hook is enabled.

**Architecture — JEPA-family world model (per commitment #16).** L4 predictors implement the Joint Embedding Predictive Architecture pattern: an **encoder** maps inputs (per-axis history, FeatureSnapshots, embeddings) to a compact **latent state**; a **predictor** forecasts future latent state conditioned on an optional **action embedding**; **projection heads** produce axis-specific distributional outputs from the latent state. The v1 implementation target is the LeWM recipe (single-GPU, ~15M parameters, two-loss end-to-end training with SIGReg as the anti-collapse regularizer).

The registry-and-axis interface (described below) remains the consumer-facing surface — `predict(axis, ...)` returns one axis's forecast — but underneath, predictors may **share an underlying world model** with axis-specific projection heads. Sharing is the architectural target; the registry doesn't require it (some axes with categorical or event-shaped outputs may use stand-alone predictors that don't share the world model).

**Output shape.** Forecasts are distributional, per-axis, on-demand. The contract:

`predict(axis, horizon, action=None) → (distribution, confidence, model_id, inputs_used, log_id)`

- `axis` — any registered axis (continuous, categorical, or binary-event).
- `horizon` — a time delta from now (or absolute time).
- `action` — optional Regis-action descriptor (a categorical action type, or an embedded action vector in the world-model's action space). `None` returns the baseline forecast given current latent state. A specific action returns the counterfactual conditional on that action — implemented as `predictor(latent_state, encode_action(action))` under the JEPA architecture. The hook preserves commitment #15's destination (modeled influence on state) from day one.
- Output — a distribution (mean + variance at minimum; richer forms per-axis) plus provenance. Provenance includes whether the action-conditioning is a calibrated learned branch of the world model or a hand-set v1 placeholder, so consumers know what they're reading.

Events are modeled as binary axes (e.g., `user_speaking_within_10min`) predicted as probabilities. There is no separate event-prediction interface.

Multi-horizon trajectories are assembled by consumers via repeated single-horizon calls. There is no bundled multi-horizon API. (Internally, the predictor may roll out the world model autoregressively in latent space — predicted latent at t+1 fed back as input for t+2 — and project from each rollout step to produce the requested horizon's output. This is an implementation detail of the predictor, not part of the consumer-facing contract.)

Per-axis predictors are **independent at the interface level** — even when they share an underlying world model at the implementation level. Joint distributions across axes are not exposed in v1; consumers wanting multi-axis predictions issue multiple calls.

**Predictor registry.** Predictors are organized in a registry keyed by `(axis, meta_context)`. Each axis has distinct predictors per active meta-context (Waking / Sleep), matching commitment #14's faithful per-context pattern. Horizon is a parameter passed to the predictor at call time, not a registry dimension.

Each `(axis, meta_context)` entry declares:
- The predictor implementation (function or model object).
- The distribution shape it outputs (continuous Gaussian, categorical probabilities, Bernoulli for binary-events).
- Historical-data dependencies — which tables, axes, and features the predictor reads.
- Training procedure — how the predictor consumes prediction errors to update itself.
- Cold-start fallback — what to return when no training data exists yet (literature-derived default or `PREDICTION_OFFLINE`).
- Confidence policy — whether very-low-confidence predictions are returned as-is (default) or treated as failure.
- Training cadence — `periodic`, `event-triggered`, or `continuous` (see *Learning loop*).

Registry population is declarative (matching L3's fusion config pattern). Dispatch at `predict()` time uses the active meta-context to select the correct predictor.

> **If an axis has no registered predictor for the active meta-context, `predict()` returns `PREDICTION_OFFLINE`.**

**Inputs.** L4 reads from several sources, with each query pattern serving a different prediction need:

| Source | Used for |
|---|---|
| **L3 in-memory state** (BeliefState + bounded backward window) | Short-horizon predictions (seconds to minutes) — current state + recent trajectory |
| **`user_state_estimate`** (Postgres) | Long-horizon predictions (hours to weeks) — historical fused state queried directly |
| **Embeddings + pgvector similarity** | Predictions that benefit from "find similar past contexts" lookup; secondary index, not primary historical store |
| **Raw event tables** (`sensor_readings`, `chat_messages`, etc.) | Predictors needing sub-axis granularity (e.g., raw HR vs derived arousal); used sparingly |
| **`prediction_log`** | Read by the training pass for prediction-error learning; not used during prediction itself |

L4 does not write to L3. The only L4 → L3 flow is the predictive-prior hook (L3 reads L4's forecast as a Bayesian prior, opt-in per axis).

**Counterfactual reasoning.** L4 owns the action-conditioning machinery. The action input is part of the JEPA architecture (commitment #16): `(current latent state, action embedding) → predicted next latent state`. When `predict()` is called with a specific `action`, the predictor produces the counterfactual forecast — predicted state assuming Regis takes that action — by routing through the action-conditioned branch of the world model. L5 calls `predict()` once per candidate action it wants to compare, then uses the returned distributions to choose.

The full causal-modeling machinery — calibrating how Regis's actions actually shape user-state trajectories — accumulates as paired (action, outcome) data lands in `prediction_log`, `regis_moments`, and `interject_decisions`. This is commitment #15's destination; commitment #16 names the predictor shape (encoder + action-conditioned predictor) that makes it concrete. v1 starts with hand-engineered action representations (categorical action types, or sparse embeddings derived from existing Regis intervention kinds) and naïve action-conditioning (the predictor's action branch is either an identity placeholder or a configured-constant shift). As data accumulates, the action branch trains under the same JEPA objective as the rest of the world model, and the predictor becomes a calibrated counterfactual engine rather than a placeholder. The placeholder-vs-calibrated distinction is surfaced in the prediction's provenance.

**Failure modes — `PREDICTION_OFFLINE` ≠ low-confidence.** A prediction failure and a low-confidence prediction are different epistemic objects.

`PREDICTION_OFFLINE` is a sentinel value (analogous to L3's `OFFLINE`) returned when prediction is genuinely impossible. L4 returns it when:
- The predictor crashed during inference (logged as an error).
- The predictor is in cold-start and the registry entry declares no fallback.
- L3 inputs required by the predictor are themselves `OFFLINE` and the predictor cannot operate without them.
- No predictor is registered for the `(axis, meta_context)` pair.

Low-confidence predictions are not failures. A predictor returning a Gaussian with high variance is reporting honest uncertainty; the prediction is returned with its real confidence, and downstream consumers (primarily L5) decide what to do with it. L4 does not artificially hide low-confidence predictions.

Cold-start fallbacks are declared per-predictor in the registry. A predictor with a fallback returns a default (literature-derived prior, baseline) marked `cold_start=true` in the provenance. A predictor without a fallback returns `PREDICTION_OFFLINE`.

**Prediction logging.** Every prediction L4 produces is logged with full provenance: `(axis, horizon, made_at, prediction, action_conditioned_on, model_id, inputs_used, log_id)`. The log persists to `prediction_log` (new Postgres table, owned by L4).

The log is the substrate for the universal prediction-error learning loop: every forecast becomes a training example once its horizon time arrives and actual state is known in `user_state_estimate`. This applies uniformly across all predictions, not just intervention or counterfactual ones. Counterfactual learning is a specialization where the prediction is conditioned on an action and the comparison happens with the action actually taken.

Predictions themselves are computed on demand and not pre-computed or cached. The log is for training, not for serving.

**Learning loop.** L4 predictors update via prediction-error training. Under commitment #16, the core training objective is **latent-space prediction loss + SIGReg regularization** — the predictor learns to forecast embeddings of future state, and SIGReg keeps the latent space from collapsing. Axis-level calibration (against actual axis values from `user_state_estimate`) happens at the projection heads, downstream of the latent prediction. Stand-alone per-axis predictors that don't share the world model train via direct ground-truth regression as before.

The mechanism:

1. A prediction made at time t is logged with full provenance.
2. At time t + horizon, actual state is recorded in `user_state_estimate` by L3 (and the corresponding latent representation is computed by the encoder).
3. The training pass reads logged predictions paired against actual latent state at horizon times, computes embedding-space prediction errors (plus SIGReg on the latent distribution and projection-head losses on the axis outputs), and updates encoder/predictor/head weights.

Training cadence is per-predictor, declared in the registry:

| Cadence | Trigger | Used by |
|---|---|---|
| `periodic` | Scheduler tick (default cadence) | Most predictors. Trains on prediction errors accumulated since last training. |
| `event-triggered` | Specific events (meta-context transitions, full-session completion) | Predictors needing complete-session data (e.g., sleep classifier — trains on completed sleep session when Waking begins). |
| `continuous` | Every prediction-actual pair as it becomes available | Rare; fast-converging models only. |

Predictors that require stability during active use (long-running continuous-prediction loops with state continuity) flag this in their registry entry; their training is paused while they are in an active loop and resumes when the loop ends.

Updated weights take effect on the next `predict()` call. The `prediction_log` records `model_id` for every prediction so historical analysis can attribute predictions to the model version that produced them.

**Calibration as a first-class concern.** L4 tracks calibration alongside accuracy. A well-calibrated predictor's stated confidence matches its actual hit rate — when it reports 70% confidence, it is right 70% of the time. Calibration is meta-honesty: whether the *uncertainty itself* is truthful.

Predictor training optimizes for calibration alongside (or constrained by) accuracy. Calibration metrics are surfaced per predictor; operators can see which predictors are well-calibrated and which over- or under-claim confidence. For an empath whose downstream layers act on stated confidence, calibration is a contract requirement, not a nice-to-have.

**Ground truth varies by axis.** Calibration requires comparing predicted distributions against actual outcomes — and "actual" is not uniformly available across axes:

- Axes with **real ground truth** (calibration is meaningful): `sleep_stage` (classifier output validated against Apple HK labels and eventually polysomnography); raw biometric values (HR, HRV — instrument-measured); declared axes (`arousal_declared` is itself the ground truth when the user states it); event axes with observable outcomes (`user_speaking_within_10min` resolves on observation).
- Axes with **estimator-vs-estimator** comparison (calibration is aspirational): inferred axes like `arousal_inferred`, `valence_inferred`. The "actual state at horizon time" comes from L3's fuser, which is itself an estimator. Calibration measured this way tells us whether the predictor matches the fuser — not whether either matches reality.

Per-axis predictor entries declare their ground-truth source and a calibration-meaningfulness flag. Calibration metrics are honest about which axes they can validate genuinely and which are reporting predictor-fuser agreement. Self-report integration (mood reports, dream recalls, explicit declarations) is one of the routes for upgrading aspirational calibration to meaningful calibration over time.

**Label provenance.** L4 training reads labels through the provenance taxonomy in commitment #17. In practice, this means a row derived from Apple Health sleep stages, an explicit "I feel focused" self-report, an ignored Regis interjection, a blink-rate literature prior, and an LLM-extracted attention heuristic are all different training objects. They may touch the same target axis, but they carry different weights, confidence, and calibration meaning. The prediction layer is allowed to learn from weak labels, but it must preserve the difference between "this was observed," "this was declared," "this was an outcome," and "this was inferred from published priors."

**Calibration state surfaced per axis.** Each predictor reports a `calibration_state` per axis: `cold_start` (no data, using fallback), `calibrating` (data accumulating, predictor learning), `calibrated` (sufficient data, predictor stable within target calibration tolerance). Downstream consumers — especially L6 / UI — read this state to surface honest framing ("Regis is still learning your baseline for [X]") rather than treating predictions as fully reliable. The state is part of the prediction's provenance; it is a system-wide epistemic property, not a product polish concern.

**Contract.**
- *Inputs:* L3 in-memory state (per-axis values + bounded backward window); `user_state_estimate` (historical fused state); embeddings index (similarity queries); raw event tables (rare, predictor-specific); `prediction_log` (training pass only).
- *Outputs — primary interface:*
  ```
  predict(axis, horizon, action=None) → (distribution, confidence, model_id, inputs_used, log_id)
  ```
  Returns `PREDICTION_OFFLINE` sentinel for failure cases (see *Failure modes*).
- *Side-effect writes:* every prediction is persisted to `prediction_log`. The training pass writes updated predictor weights/parameters to the registry-backing store.
- *L5 access:* L5 reads predictions via `predict()`. L5 may call `predict()` multiple times per decision (once per candidate action) to compare counterfactual forecasts. L5 does not write to L4.
- *L3 access (predictive prior hook):* when enabled per-axis, L3 calls `predict(axis, horizon=0, action=None)` to obtain a current-moment distribution it uses as the Bayesian prior in fusion. L3 does not otherwise read L4.

**Meta-context bias.** Per commitment #14, L4 maintains distinct predictors per `(axis, meta_context)` pair. Sleep predictors and Waking predictors are separate code paths with their own historical-data dependencies, math, and training procedures. Dispatch happens at `predict()` time based on the active meta-context.

Predictor training is also meta-context-aware: each context's predictors typically train on data from their own context, often event-triggered by the meta-context transition that ends a complete session. This naturally staggers training — sleep predictors train during waking hours (after a completed sleep session), waking predictors train during sleep (after a completed waking day) — avoiding the case where a predictor is being updated while actively producing live predictions in its own context.

**Evolution.** L4 does not exist today as a coherent layer (no world model is trained, no predictor registry is built). The migration is staged:

1. **v1 — per-axis scaffolds (stand-alone predictors, non-world-model branch).** Initial implementations come online as their respective input axes become available — biometric-derived predictors as L2 features stabilize, voice-derived predictors as prosody and STT mature, BCI-derived predictors when the BioAmp EXG Pill is online. The existing sleep classifier (XGBoost at `apps/inference/classifier/`) wraps as the first stand-alone per-axis predictor in the registry — an axis with categorical output that doesn't share a world model is exactly the case #16 carves out as legitimate stand-alone. Every v1 predictor honors the `predict(axis, horizon, action)` interface so its call sites compose forward.
2. **v2 — JEPA world model lands (commitment #16).** Once ~4–8 weeks of paired (state, action, next-state) data has accumulated via #13's outcome-driven decisions, the LeWM recipe trains end-to-end on the desktop PC's 4080. Axes whose predictors share the world model migrate their projection heads onto it; axes that don't (sleep classifier, event-shaped binary axes) stay stand-alone in the registry. The transition is per-axis-class, not all-at-once.
3. **v3 — predictive priors and rolling counterfactual.** Predictive priors for L3 come online once any individual predictor demonstrates better-than-smoothed-recent performance on a per-axis basis. CEM-style L5 planning over the world model activates per action-class once the action-conditioning branch is calibrated.

See §11 for current gaps.

**Open questions.**
- *Predictor model versioning.* Beyond `model_id` in the prediction log, full version-control machinery (rollback, A/B comparison across versions, model lineage tracking) is deferred to implementation.
- *Action embedding space.* Commitments #16 + #15 require an embedding space for Regis's actions. The space's shape (categorical kind tokens + a continuous utterance-embedding vector? a learned action codebook? a unified embedding via the same text encoder used for utterances?) is deferred to the world-model implementation. v1 uses a small categorical kind enum as a placeholder.
- *Goal-state specification for L5 planning.* Once L5 transitions to CEM-style world-model planning (commitment #16, L5 implication), goal states must be specified in the world model's latent space. The pipeline for deriving goal embeddings — averaged latent states from labeled "good outcome" sessions, hand-specified per-context targets, or user-specified preferences — is deferred.
- *Cold-start training data volume.* The JEPA recipe needs sufficient (state, action, next-state) triples to train without collapse. Estimated threshold is weeks-to-months of real interaction. The crossover point at which the world-model implementation supersedes v1 per-axis regression scaffolding is data-driven, not date-driven.
- *Self-report integration as training signal.* Mood reports, dream recalls, and declared-axis writes are obvious ground-truth sources. The specific pipeline (cadence, weighting vs inferred state, conflict resolution) is deferred.
- *Multi-user generalization.* Per-user predictors vs shared world models with personalization layers. JEPA's strength is that per-user fine-tuning over a population-pretrained world model is a clean path; deferred until N > 1.
- *Per-axis forecasting math (non-world-model branch).* Which model class fits which axis when not sharing the world model (regression, Bayesian, GP, small NN). Lives in the subsystem doc (`docs/Architecture/PREDICTION.md` planned), not in the architecture overview.

---

### Layer 5 — Decision

*Status: TODO.*

**Job (preview).** Take predictions + user-outcome history + current explicit input + meta-context and decide what action (if any) Regis takes. Routes by **intent** (per commitment #10) — explicit events dispatch as commands, continuous state updates feed posture decisions (Witness vs Companion mode per commitment #5).

**Action-selection evolution.**

- **v1 — Thompson contextual bandit (commitment #13).** `learned_decider.py` selects among discrete action options using outcome-labeled history. Works at N=1 with light data. Substrate today.
- **v2 — World-model planning over JEPA predictor (commitment #16).** Once the L4 world model's action-conditioning branch is calibrated enough, L5 samples candidate Regis actions, queries L4 with each (`predict(axis, horizon, action=candidate)`), compares predicted next-state embeddings against goal-state embeddings in latent space, and selects the action whose predicted trajectory best matches the goal. Algorithm: Cross-Entropy Method (CEM) sampling, as in LeWM. The Thompson bandit doesn't disappear — it remains valuable for actions whose downstream effects are too coarse or too rare to model — but for the major action categories (interject vs witness, content-kind selection, cue timing) the world-model planner supersedes hand-tuned scoring as data permits.

The transition is per-action-class, not all-at-once: action categories where the world model is well-calibrated transition to planner-driven selection; categories where it isn't stay on the bandit. Commitment #16's provenance signaling (placeholder vs calibrated action-conditioning) is what L5 reads to decide which mechanism to use per action class.

---

### Layer 6 — Output

*Status: partial (Week 2, 2026-05-28) — TTS + voice loop live.*

**Job (preview).** Take the decision from L5 and emit it through the appropriate channel. Per commitment #3 (wisp-as-interface), audio is primary; UI/haptic/visual indicators are supplementary. Output channel selection is intent-dependent (commitment #10) and meta-context-biased (commitment #14 — no companion-mode TTS during deep sleep).

Components today: TTS via `apps/inference/audio/tts_router.py` (`speak()`, witness/companion modes; macOS `say` default, Kokoro optional), played over bone-conduction headphones. Future: haptic, visual indicators.

**Voice loop (Week 2).** The conversational turn engine is `apps/wisp/composer.py::compose_utterance()` (NOT a separate chat handler — the rebuild scrap removed `apps/chat/`). It reads the **freshness-gated `BeliefState`** (`apps/inference/fusion/loader.py::load_belief_state`) before composing, so stale axes never shape Regis's reply (commitment #14). The cross-layer runtime `apps/voice/loop.py` ties it together: `VoiceWakeWordDetector` (L1) → `transcribe_streaming()` (L1/L2) → `classify_intent()` routes command-vs-message (commitment #10) → `compose_utterance()` (L5) → `tts_router.speak()` in the mode L5 chose (L6). Mode selection (witness vs companion) is the #5/#14 corollary surfaced at output.

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
| **Sleep classifier** | L4 (Prediction) | Trained XGBoost on biometric features; predicts REM/non-REM per epoch. Lives at `apps/inference/classifier/`. Under commitment #16, this is a stand-alone per-axis predictor (categorical output, non-world-model branch) — registered in L4's predictor registry without sharing the JEPA encoder/predictor. |
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

### What runs where, by layer

The host evolves across phases, but the layered architecture imposes a per-layer compute profile that constrains where each layer can live. Honest mapping:

| Layer | v1 (today, Mac) | v1.5 (Pi takeover) | v3 (wearable) |
|---|---|---|---|
| **L1** — edge capture clients | Mac (mic listener, gesture detector); iPhone/Watch via API; HealthKit sync | Pi (mic, gesture, intent edge classifiers); phone via API; HealthKit | On-body devices (BCI, mic, camera, IMU) with on-device intent tagging |
| **L1** — storage | Neon Postgres (cloud) | Neon Postgres (cloud) | Neon Postgres (cloud) |
| **L2** — feature extraction | Mac (heartpy, librosa, sentence-transformers, Whisper, YOLO) | TBD — lightweight features (HR/HRV, audio VAD) on Pi; heavier (embeddings, YOLO, full Whisper) on the desktop PC (4080) over local network | Distilled feature extractors on-device for low-bandwidth axes; heavier compute cloud / desktop |
| **L3** — fusion (in-memory) | Mac (Python process) | TBD — lightweight v1 deterministic combiners on Pi; v2 Bayesian combiners likely too heavy for Pi alone | Distributed: fast axes on-device, slower axes cloud/desktop |
| **L3** — historical persistence | Neon Postgres (cloud) | Neon Postgres (cloud) | Neon Postgres (cloud) |
| **L4** — prediction | Not built yet | TBD — training nightly on desktop PC; short-horizon inference likely on Pi (latency-sensitive); long-horizon on desktop | Same shape, more on-device for short horizons |
| **L5** — decision (bandit + decider) | Mac (`learned_decider.py`) | Pi (small, fits) | On-device (latency-critical) |
| **L6** — output (TTS, UI) | Mac (Kokoro TTS); iOS / Watch native | Pi (TTS for bone-conduction); iOS / Watch native | On-device (TTS, haptic, visual indicator) |
| **LLM client** | Mac (Codex via Aakash's ChatGPT login) | Pi or Mac depending on auth/network; cloud LLM is network-dependent regardless | Cloud for general LLM; small distilled models on-device |
| **Embeddings** | Mac MPS (BGE-M3, 1024-dim) | Desktop PC (4080) over local network | Smaller distilled model on-device, or cloud-served |

**Open architectural questions for v1.5:**

- *Where does L3's v2 Bayesian fusion run?* Per-axis combiners with hierarchical-prior math are not viable on Pi 4 alone for all axes. Likely split: deterministic v1 combiners stay on Pi for hot paths; v2 Bayesian combiners run on the desktop PC and write results back to `user_state_estimate` for the Pi to read.
- *Where does L4 inference run?* Training is batch (nightly) — desktop PC. Short-horizon inference must avoid a network round-trip on every BeliefState read; either runs on Pi or is cached locally with a TTL.
- *BeliefState read latency.* When L3's hot paths live on the Pi and L4 inference is local, BeliefState reads are sub-millisecond. When fusion or prediction crosses the network boundary, the latency budget becomes a real product concern (especially for live cue gating during sleep).

Commitment #9 (v1 IS v3 substrate) holds at the **code** level — same modules everywhere — but the **deployment** picture is genuinely distributed by v1.5. The architecture supports this because the layers communicate through Postgres (network-transparent) and through the FastAPI bridge (HTTP-based). Cross-host calls between layers are possible without code rewrites; what changes is where each layer is hosted.

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

### Privacy, consent, and audit trail

Daybook's product layering (consumer empath → clinical-grade extension → wearable form factor, per `POSITIONING.md`) requires privacy and consent treatment to be load-bearing in the architecture, not retrofitted. Privacy/consent constrains every storage write, every retrieval read, every cross-process boundary. The commitments below apply whether or not a clinical extension is active — they are foundational, not optional.

**Per-row consent metadata.** Every entity that holds user-derived information carries consent metadata. Minimum schema: `(consent_scope, consent_granted_at, consent_grantor)` per row.

- `consent_scope` — what the user has agreed to (e.g., `personal_use`, `share_with_therapist`, `share_for_research`, `model_training`).
- `consent_granted_at` — timestamp of the active grant.
- `consent_grantor` — typically the user themselves; may be a delegate (e.g., a clinician acting under documented authority).

Reads filter by current consent scope. Writes capture the active consent context. Consent can be tightened (revoked) but never silently broadened.

**User-driven deletion.** The user can request deletion at three granularities: per-row (specific events), per-time-range (all data within a window), per-modality / per-axis (all data of a kind). Deletion is soft-tombstoned in primary storage with a hard-delete grace window, and propagated to embeddings, clustering memberships, and any derived indexes. Composite axes recompute correctly because they have no stored values.

**Sensitive-content tagging.** Content sensitive by category (trauma narratives, dream content involving abuse, clinical observations about suicidal ideation, identity-disclosure content) is tagged at ingestion — by simple heuristics in L1/L2 or by explicit user marking. Downstream layers respect the tags: sensitive content is excluded from default retrieval indexes, not sent to non-private LLM endpoints, and treated with elevated logging.

**Therapist audit trail** (clinical extension). When a credentialed therapist accesses user data, every read is logged with `(therapist_id, accessed_at, scope, purpose_code)`. The audit log is itself user-readable — the user can see what their therapist saw, when, and why.

**Architectural implications across the layers.**
- L1 polymorphic tables (`sensor_readings`, `chat_messages`, `user_actions`, `regis_moments`, `dream_recalls`) carry consent columns.
- L2 feature extraction inherits sensitivity tags from L1 inputs; derived features inherit by default.
- L3 reads filter by active scope; the BeliefState surfaces only consent-allowed axes for a given consumer.
- L4 training pass honors consent scopes — predictors operating under `model_training` scope skip rows with `personal_use_only` consent.
- L6 output channels (TTS, UI) honor sensitivity tags in what they surface to whom.
- The FastAPI bridge (commitment #12) enforces consent at the request boundary, alongside auth.

**Open questions** (deferred to implementation / clinical conversations):
- Specific consent UI — how the user grants and revokes consent in the iOS app.
- HIPAA-grade encryption-at-rest — required for the clinical tier; v1 prototype runs on personal hardware.
- Data residency — Neon (current cloud Postgres) is US-hosted; clinical contexts may require region-specific hosting.
- Consent inheritance during clustering — what scope a discovered I-Model carries if its constituent embeddings span multiple scopes.

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

Jobs can fail independently without bringing the daemon down (APScheduler isolates failures per-job). The scheduler runs as part of the same Python process as the mic listener when both are active via `python -m daybook`.

**Concurrency and failure semantics.** Several jobs have implicit data dependencies: `trait_decay` (04:30) reads cluster activations updated by `nightly_clustering` (04:00); `cluster_dormancy_sweep` (04:45) reads activations updated by clustering and trait passes; `refresh_regis_self` (05:30) reads observations updated by `nrem_consolidation` (03:00). The scheduler does not currently enforce these dependencies — jobs fire at declared times regardless of whether their predecessors completed.

Architectural commitments for the ideal:

- **Idempotency** — every job is written to be safely re-runnable. Existing pattern: observation distillation keyed by `(date, source_id)` skips already-processed rows.
- **Declared dependencies** — jobs declare what they depend on; the scheduler enforces ordering or defers dependent jobs if their predecessors haven't completed.
- **Retry semantics** — transient errors retry with backoff; permanent errors log and surface alerts.
- **Partial-failure recovery** — long-running jobs (clustering especially) checkpoint progress so a mid-run failure doesn't restart from zero.

Today, idempotency is partially in place; dependency enforcement, retry layer, and checkpointing are not. See §11.

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

*Status: active design log.* The honest list of what we don't yet know — design decisions deferred, label-provenance mechanics not yet implemented, and evaluation harnesses unbuilt. Plus links to subsystem deep dives and per-feature design docs as they're written.

Current open questions:

- **Label store shape.** Do labels live in a new `label_observations` table, as typed rows in existing event tables, or both? The architecture requires provenance, confidence, consent scope, target axis, and source lineage either way.
- **Literature extraction workflow.** Which papers/datasets are trusted sources, how are LLM-extracted rules reviewed, and what threshold promotes a rule from weak prior to live pseudo-label generator?
- **Demographic priors.** Which demographic attributes, if any, are worth collecting, what consent language is required, and how do we prevent demographics from hard-coding biased assumptions?
- **Self-report capture.** What is the lowest-friction way for a user to declare state without turning the product into a survey app?
- **Fusion-ablation harness.** What source-set search space is practical for the desktop PC, and what metrics decide whether `EEG+EOG+mic` beats `EEG+EOG` or `EOG` alone for a target axis?

References and planned subsystem docs:

- `docs/Architecture/FUSION.md` (planned)
- `docs/Architecture/SENSING.md` (planned)
- `docs/Architecture/LABELING.md` (planned)
- `docs/Architecture/PREDICTION.md` (planned)
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

- **End-to-end hardware relay not proven:** sensor adapters and transport primitives exist, but the real prototype loop — external device/Pi producer → Mac inference process → BeliefState → Regis behavior — has not been proven with physical hardware.
- **L2 feature pipeline only partially centralized:** `apps/inference/features/` now holds biometric, audio-social, BCI, and vision-scene extractors. Remaining work is wiring every live capture/import path through the same `FeatureSnapshot` contract instead of one-off shortcuts.
- **L3 fusion scaffold exists, full fusion engine does not:** `apps/inference/fusion/` has `BeliefState`, loader/writer primitives, and live axis modules (`meta_context`, `sleep_stage`, `audio_social_context`, `cognitive_load`, `visual_context`, `arousal_inferred`, `affect_prosody`). Missing: one declarative fuser registry with source-set weights, provenance-aware priors, Bayesian v2 combiners, and offline-ablation promotion.
- **L4 scaffold exists, world model does not:** prediction interface/registry/stubs and the REM classifier wrapper exist; `prediction_log` schema exists. Missing: broad per-axis predictors, prediction-error training passes, calibrated action-conditioning, and JEPA/SIGReg world-model machinery.
- **Meta-context bias is partial:** `meta_context` is an L3 axis and some prediction/policy paths gate on it. The ideal per-context extraction/fusion/prediction behavior is not yet applied consistently across all L2-L4 modules.

### Modality coverage gaps

- **Vision ingestion:** code lane exists (`sensors/vision_adapter.py`, `vision/perception.py`, `features/vision_scene.py`, `fusion/axes/visual_context.py`), but continuous real-camera runtime and ESP32-CAM integration are not proven.
- **BCI ingestion + features:** code lane exists (`sensors/eeg_adapter.py`, `bci/bandpower.py`, `features/bci.py`, `fusion/axes/cognitive_load.py`), but the EXG Pill is not wired into the live prototype and no EOG blink / EMG clench calibration dataset exists yet.
- **Apple Watch live path:** Apple Health import/replay and watch adapter contracts exist; live low-latency Watch → Daybook streaming remains unproven.
- **Deliberate gestures:** ⚪ schema in `user_actions`, no ingestion code yet.
- **Involuntary gestures (EOG/EMG):** architecture and BCI feature lane can absorb them, but blink-rate / muscle-signal extraction is not implemented against real hardware.

### Learning gaps

- **General label provenance pipeline:** not built. Existing labels are narrow (Apple Health sleep stages, REM classifier training labels, schema fields for action outcomes). There is no unified label store, self-report axis, literature/LLM extraction workflow, demographic-prior store, or provenance-weighted training loader yet.
- **Online learning loops:** not broadly active. The repo has schemas and seams for outcome-driven learning, but predictors and policies do not yet improve continuously from labeled outcomes. Ideal: every predictor + decider learns from provenance-scoped labels and observed outcomes.
- **Fusion-ablation harness:** not built. We do not yet enumerate source sets (`EEG`, `EOG`, `EEG+EOG`, `EOG+mic`, etc.) offline and promote only the combinations that improve calibration.
- **Cold-start onboarding / per-user baselines:** not built. New users currently rely on generic defaults plus whatever imported device history exists; the architecture requires a formal cold-start profile that blends literature priors, optional demographics, device calibration, and early self-report.
- **Treatment-effect estimation (commitment #15):** the schemas and seams can accumulate paired (action, outcome) data, but counterfactual reasoning ("if Regis does X, predicted t+1 = ?") isn't implemented yet. Ideal: causal model consumed by L4's `predict(axis, horizon, action)` interface.
- **JEPA world model (commitment #16):** no encoder/predictor/SIGReg machinery exists. v1 predictors land as per-axis regression scaffolds with the L4 interface shaped for the world-model destination (every prediction logs provenance distinguishing placeholder vs calibrated action-conditioning). Ideal: shared encoder + action-conditioned predictor + projection heads, trained end-to-end via the LeWM recipe on accumulated (state, action, next-state) triples. Estimated 4–8 weeks of real interaction data before the world-model implementation supersedes per-axis scaffolding.
- **CEM-style L5 planning (commitment #16, L5 implication):** L5 today selects actions via fixed-weight/default policies and explicit warrants. The world-model planner — sample candidate actions, query L4 for predicted next-state embedding per candidate, pick the closest to a goal embedding — depends on a calibrated world model and is unimplemented.

### Documentation gaps

- **Architecture body current-state pass:** the gap index now reflects the rebuilt L1-L6 scaffolds, but some descriptive sections above still need a full post-rebuild cleanup pass.
- **Subsystem deep-dive docs** (`docs/Architecture/FUSION.md`, `docs/Architecture/LABELING.md`, `docs/Architecture/PREDICTION.md`, etc.): planned but unwritten.


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
