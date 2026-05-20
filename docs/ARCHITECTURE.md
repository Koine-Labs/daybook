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

### 10. Input is classified by intent, not modality

**Rule.** All input is classified into two categories at the L1 ingestion boundary, distinguished by user intent:

- **Explicit** — user-initiated, communication-intended.
  Voice (typed text directly; spoken voice via STT → text), deliberate gestures (pinch, head shake, deliberate nod, hand wave).
  Land in `chat_messages` and `user_actions`.

- **Continuous** — ambient, passive sensing, no communication intent.
  Biometrics, audio prosody, vision, BCI, involuntary gestures (EMG-detected blinks, micro-movements). Land in `sensor_readings` (polymorphic via `kind`).

Modalities can cross-cut both categories (voice can be explicit speech or background mumbling; gestures can be deliberate commands or involuntary state signals). Each event is tagged with its intent at the L1 boundary.

Output channels are voice (primary), future haptic, future visual indicator — all explicit-by-design.

**Why.** Categorizing by modality muddles the design: "gestures" as one category conflates EMG-detected involuntary blinks (state signal) with Vision-Pro-style pinch-to-select (command), but these need fundamentally different routing downstream. The intent axis is what later layers care about: continuous signals feed Layer 3 (fusion) to update state estimates; explicit signals dispatch to Layer 5 (decision) as commands. Intent propagates through the whole pipeline with different interpretive weight at each layer — it's a typing system, not just an L1 tag.

**Lineage.** Original v1 of this commitment (2026-05-17) framed inputs as three channels (voice / continuous context / gestures). Refined 2026-05-21 to intent-based classification after recognizing gestures cross-cut both categories. The "non-voice input is first-class" claim of v1 is preserved; the taxonomy is sharpened.

### 11. Semantic-first continuous sensing

**Rule.** All continuous sensor streams use semantic-first architecture: continuous low-bandwidth meaningful extraction (VAD, diarization, prosody for audio; YOLO, scene class, OCR for visual) → semantic packets stored as `sensor_readings`. Raw pixels and raw audio are discarded after processing. Cloud LLM calls (multimodal vision, full STT) are *triggered escalation only* — never continuous.

**Why.** Continuous full-fidelity capture is impossible on battery, privacy, and cost grounds. The biological model is correct: the brain doesn't process every photon; it extracts features at low levels and escalates to focused attention selectively. Following this pattern is the only viable architecture for always-on awareness on real hardware.

### 12. Native clients talk to FastAPI, never brain modules directly

**Rule.** iOS, watchOS, and any future client speaks HTTP to `apps/api/`. They never import `chat`, `recall`, `wisp`, etc. The bridge is the seam. Auth via `X-API-Key` with loopback bypass.

**Why.** Direct module imports across language boundaries (Swift → Python) couple platforms together and break independent evolution. The FastAPI bridge enforces a clean contract: backend evolves in Python, clients evolve in their native stack, the API is the only thing that needs versioning. Auth and tunnel concerns are isolated at the bridge.

### 13. Regis is a controlled variable in his own predictive model

**Rule.** The decision layer eventually models how Regis's actions shape predicted future state — decisions become forward-looking treatment-effect estimation, not just retrospective scoring of "did interjecting help."

**Why.** A purely reactive Regis (responds to events, learns from outcomes) is fundamentally limited — it can never ask "if I do X vs Y, how does the user's trajectory change?" That counterfactual reasoning is the difference between a chatbot and an empathic agent. The Thompson contextual bandit (current state) is the first seed; the destination is a system that models its own influence on predicted state at t+1. Purely reactive architectures are inconsistent with the long-term direction.

---

## 3. The layered design

Daybook organizes around 6 horizontal layers. Each has one job, takes inputs from the layer below, produces outputs for the layer above. Walking the layers makes coverage gaps obvious. Writing the contracts makes parallel work possible — once each layer's contract is agreed, implementations are independent.

```
Layer 6 — Output             text → TTS / UI / future hardware effects
Layer 5 — Decision           forecasts + outcomes → action choice
Layer 4 — Prediction         state + trajectory → data / context / action forecasts
Layer 3 — Fusion             intent-tagged features → unified state representation
Layer 2 — Signal processing  raw sensor data → meaningful features (per modality)
Layer 1 — Sensors            raw input ingestion (intent-classified at the boundary)
```

**Intent propagates through every layer.** As established in commitment #10, every event is classified as **explicit** (user-initiated, communication-intended) or **continuous** (ambient, passive) at the L1 boundary. That intent tag travels with the event through subsequent layers; each layer applies intent-aware logic where it matters. Layers 2-4 use intent to choose feature pipelines, fusion weights, and prediction model types; Layer 5 routes decisions by intent (commands vs state updates).

For each layer below: **Job** · **Current components** · **Contract** · **Evolution**.

---

### Layer 1 — Sensors

**Job.** Ingest raw input from sources; persist as discrete events tagged with intent. No deep interpretation — only normalization.

**Intent categories (per commitment #10):**
- **Explicit:** voice (typed text directly; spoken voice via STT → text), deliberate gestures (pinch, head shake, hand wave). Land in `chat_messages` / `user_actions`.
- **Continuous:** biometrics, audio prosody, vision, BCI, involuntary gestures (EMG-detected blinks, micro-movements). Land in `sensor_readings` (polymorphic via `kind`).

**Current components:**
- ✅ HealthKit ingestion (iOS HealthKitClient → `/state/sensor_readings`)
- ✅ Audio prosody capture (Mac mic listener → audio_context persistor → `sensor_readings`)
- ✅ STT (Whisper, captures user voice as `chat_messages`)
- ✅ Text chat (iOS / CLI → `chat_messages`)
- ⚪ Deliberate gestures (schema in `user_actions`; no ingestion code yet — needs hardware/UI)
- ⚪ Involuntary gestures (no ingestion yet — needs BCI/EMG hardware or vision)
- ⚪ BCI raw signals (no ingestion yet — BioAmp EXG Pill incoming)
- ⚪ Vision (no ingestion yet — ESP32-CAM available)

**Contract.**
- *Inputs:* hardware/user events (HealthKit deltas, mic frames, typed text, future BCI samples, etc.)
- *Outputs:* persistent rows in event tables, each implicitly tagged with intent by its destination table (`chat_messages` / `user_actions` = explicit; `sensor_readings` = continuous)
- *Cadence:* per-event. No fixed clock; driven by source.
- *Interpretation:* minimal — schema normalization only. Whisper STT sits at the L1/L2 boundary; we treat captured speech-as-text as L1 output for downstream simplicity.

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

## 6. Where Regis runs

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

## 7. Cross-cutting concerns

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

## 8. Evolution roadmap

*Status: TODO (sequenced after §3 layered design is agreed).*

A short list of what's *done*, *next*, and *later*. Lives here (not in `STATUS.md`) because it's about *architectural* evolution — the trajectory of capabilities, not the operational state of any one capability.

Expected structure:
- **Done** — major architectural milestones reached
- **Next** — what's currently being built or up next
- **Later** — known architectural moves on the horizon (BCI integration, MoE-style gating, vision modality, online learning loops, custom wearable hardware, etc.)

---

## 9. Open questions + references

*Status: TODO.* The honest list of what we don't yet know — design decisions deferred, labeling strategies undecided, evaluation harnesses unbuilt. Plus links to subsystem deep dives and per-feature design docs as they're written:

- `docs/Architecture/FUSION.md` (planned)
- `docs/Architecture/SENSING.md` (planned)
- `docs/design/<feature>.md` (per-feature, as-needed)

---

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
