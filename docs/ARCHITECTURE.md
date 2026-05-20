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

*Status: TODO.* The inviolable rules of the system. Currently 12 (becoming ~14 as the fusion direction adds new ones). Each commitment gets:
- **Rule** (1 sentence — what's locked)
- **Why** (2-3 sentences — the reasoning that made it inviolable)

Migrated and expanded from `CLAUDE.md`. `CLAUDE.md` will keep a 1-liner-per-commitment list pointing back here for the depth.

---

## 3. The layered design

*Status: TODO (the heart of this document — needs real conversation).*

Daybook organizes around 6 horizontal layers. Each has one job, takes inputs from the layer below, produces outputs for the layer above. For each layer this section will document:

1. **Job** — one sentence: what this layer is responsible for
2. **Current components** — what lives here today, with status
3. **Contract** — what flows in, what flows out, at what cadence
4. **Evolution path** — v1 (today) → v2 → v3 trajectory

Layers, top to bottom:

```
Layer 6 — Output             (text → TTS / UI / future hardware effects)
Layer 5 — Decision           (forecasts + outcomes → action choice)
Layer 4 — Prediction         (state + trajectory → forecasts of future state)
Layer 3 — Fusion             (per-modality features → unified user-state representation)
Layer 2 — Signal processing  (raw sensor data → meaningful features, per modality)
Layer 1 — Sensors            (raw data ingestion from biometrics, audio, vision, BCI, chat)
```

This is the section that answers *"do we have everything? does it fit together?"* Walking each layer makes coverage gaps obvious. It's also the section that legitimizes parallel agent work — once each layer's contract is written, implementations are independent.

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
