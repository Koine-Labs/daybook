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

*Status: TODO.* The deployment view.

- **Today:** Python backend on Mac, FastAPI tunneled via Cloudflare (`daybook.koinelabs.com`), iOS + Watch apps as clients
- **Soon:** Pi 4 takes over the always-on backend role
- **Eventually:** custom wearable hardware
- **Constant across all phases:** same code path; only the host changes (per commitment #9)
- **Auth model:** `X-API-Key` for tunneled traffic, loopback bypass for local
- **Embedding compute:** Mac MPS today → desktop GPU as scale demands → potentially on-device in v3

---

## 7. Cross-cutting concerns

*Status: TODO.* Things that don't fit neatly into one layer:

- **The nightly scheduler** — 11 scheduled jobs in `apps/daybook.py`, what each does and when
- **The interject decider** — Thompson contextual bandit, outcome labeling loop, learned routing
- **Error handling philosophy** — graceful degradation; hot paths never crash; log + return None on optional reads
- **The substrate as single read point** — everything Regis perceives in a moment flows through `gather_substrate`
- **Observability** — where logs go, what's monitored, what's not yet

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
