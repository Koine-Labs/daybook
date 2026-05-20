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

### Layer 1 — Sensors

**Job.** Ingest raw input from sources; persist as discrete events. Tag each event along both axes (intent + modality) at the boundary. No deep interpretation — only normalization.

**Two-axis classification at the boundary (per commitment #10):**

Every event has both an intent and a modality:

| | Voice | Text | Gesture | Biometric | Audio (non-voice) | Vision | BCI |
|---|---|---|---|---|---|---|---|
| **Explicit** | Spoken-to-Regis | Typed chat | Pinch / nod / wave | — | — | Looking-at-camera | — |
| **Continuous** | Background mumble | — | Blink / jaw clench | HR / HRV / sleep | Room prosody | Scene / presence | EEG / EOG / EMG |

Storage today: intent determines the table; modality determines the row's `kind` (or content):
- **Explicit** → `chat_messages` (voice/text), `user_actions` (gestures)
- **Continuous** → `sensor_readings` (polymorphic via `kind`: `heart_rate`, `hrv`, `sleep_stage`, `audio_context`, future `eeg_packet`, etc.)

**Current components:**
- ✅ HealthKit ingestion (iOS HealthKitClient → `/state/sensor_readings`) — *continuous, biometric*
- ✅ Audio prosody capture (Mac mic listener → audio_context persistor → `sensor_readings`) — *continuous, audio*
- ✅ STT (Whisper, captures user voice as `chat_messages`) — *explicit, voice*. Note: Whisper itself is L2 work (modality-specific feature extraction); the raw audio waveform was captured at L1
- ✅ Text chat (iOS / CLI → `chat_messages`) — *explicit, text*
- ⚪ Deliberate gestures — *explicit, gesture* (schema in `user_actions`; no ingestion code yet — needs hardware/UI)
- ⚪ Involuntary gestures — *continuous, gesture* (no ingestion yet — needs BCI/EMG hardware or vision)
- ⚪ BCI raw signals — *continuous, BCI* (no ingestion yet — BioAmp EXG Pill incoming)
- ⚪ Vision — *continuous, vision* (no ingestion yet — ESP32-CAM available)

**Contract.**
- *Inputs:* hardware/user events (HealthKit deltas, mic frames, typed text, future BCI samples, etc.)
- *Outputs:* persistent rows in event tables, each implicitly tagged with `(intent, modality)` by destination table + `kind`
- *Cadence:* per-event. No fixed clock; driven by source.
- *Interpretation:* minimal — schema normalization only. Modality-specific feature extraction (Whisper STT, prosody features) happens at L2.

**Evolution.**
- **v1 (today):** biometrics + audio prosody + text/voice chat
- **v1.5:** BCI + vision ingestion as additional `kind` values in `sensor_readings`
- **v2:** gesture pipelines online — deliberate via `user_actions`, involuntary via `sensor_readings`
- Polymorphic schema absorbs new modalities without migrations. Adding BCI is `kind='eeg_packet'`, not a new table.

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
- **Body-bridge L1→L3 shortcut:** body-bridge reads raw HR/HRV from L1 and applies heuristics directly. Ideal: formal L2 features (heartpy / neurokit2) producing FeatureVector → L3 fusion.
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
