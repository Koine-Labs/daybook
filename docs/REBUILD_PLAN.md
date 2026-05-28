# Daybook — Rebuild Plan

**Status: draft (v0.1) for review. Not yet executed.**
**Date drafted: 2026-05-27**
**Owner: Aakash Agrawal**

---

## Why this exists

The current implementation predates most of `docs/ARCHITECTURE.md`. The architecture doc describes the *ideal* system (16 commitments, 6 layers, JEPA-family prediction). The code is a glued-together v0 prototype where layers leak, L3 doesn't exist as a real component, L4 is empty, and several modules straddle layer boundaries.

The decision (2026-05-27): **scrap most of the current implementation and rebuild from the layered architecture down.** Specific user decisions baked in:

- Delete iOS + watchOS apps (rebuild later when there's a polished story).
- Delete the manually-imported 10-year Apple Health data rows.
- Keep `apps/inference/llm/` (Sign-in-with-ChatGPT + Codex client) — used as the API-bypass test path.
- Build "by the book" — every module honors its layer's contract.
- **v0 keeps running on `main` during the rebuild.** Dream-recall logging continues uninterrupted; rebuild work lives on `rebuild/main` and only lands on `main` after parity. The validation wedge does not pause.

This document is the single working plan. Redline it, approve it, then execute against it.

---

## Scope

**In scope:**
- Delete the modules that straddle layers or are legacy (chat handler, realtime mashup, cue decider, legacy feature engine, body-bridge shortcut, ad-hoc sleep observer).
- Delete the iOS + watchOS clients entirely.
- Delete the imported HK data rows (not the schema, not the importer script).
- Build L1–L6 as proper, layer-isolated Python modules per `docs/ARCHITECTURE.md`.
- Add migration 0005 (`prediction_log` + consent columns + any axis fields).

**Out of scope (deferred):**
- iOS/watchOS rebuild (later, separate project).
- Pi-side daemon rewrite (separate chat owns that).
- Full JEPA world-model training (per commitment #16 — v1 lands as per-axis scaffolds; world model arrives when paired-data volume permits).
- Subsystem deep-dive docs (`FUSION.md`, `PREDICTION.md`, `SENSING.md`) — write alongside the build, not upfront.
- Clinical-tier architecture (deferred per `POSITIONING.md`).

---

## Safety moves (must happen before any delete)

1. **Tag current `main` as `v0-pre-rebuild`.** Working v0 is recoverable forever, even if it's never deployed again.
   ```bash
   git tag -a v0-pre-rebuild -m "Daybook v0 — pre-rebuild snapshot. Last commit before architecture-aligned rebuild started."
   git push origin v0-pre-rebuild
   ```

2. **Take a Neon branch snapshot before deleting HK data.** Neon's branching makes this trivial — the imported HK data lives on the snapshot branch indefinitely; if the data delete is ever regretted, restore.
   ```bash
   # via Neon CLI or Neon MCP
   neonctl branches create --name pre-rebuild-snapshot --parent main
   ```

3. **Create `rebuild/` branch from `main`.** All rebuild work lives here. `main` stays intact until the new system is at parity.
   ```bash
   git checkout -b rebuild/main
   ```

4. **Coordinate with the Pi-side chat before each D-delete lands on `main`.** The Pi daemon (owned by a separate chat) imports from `apps/inference/realtime.py` (D4) and may import from other modules in the delete map. Each D-delete is gated on the Pi chat confirming its import surface has migrated to the new layered modules. Pattern per delete: announce cut-over in the Pi chat → confirm Pi imports are migrated → land the delete.

---

## Delete map

Each row: what's being deleted, the extent, what replaces it.

### D1 — iOS + watchOS apps

- **Path:** `apps/ios/` (entire directory)
- **Extent:** iPhone app, Watch app, project.yml, Daybook.xcodeproj, all SwiftUI code, Daybook.icon source bundle, Assets, DesignSystem, Components, Screens, State, Networking, Daybook-Local.plist mechanism.
- **Replaced by:** *Nothing during the rebuild.* The FastAPI bridge stays (serves future clients). iOS/Watch rebuild is a separate project, after.

### D2 — Imported 10-year HK data (rows only)

- **Storage:** Neon Postgres — rows that came from `parse_apple_health.py` (in `sensor_readings`, `sleep_sessions`, anywhere else the import populated).
- **Extent:** all rows from the manual import. Tables themselves stay.
- **Replaced by:** clean slate. New data accumulates from live capture going forward.
- **Before deletion:** run `python -m classifier.evaluate` and commit the resulting metrics report (per-fold F1/ROC, baseline comparisons) under `apps/inference/classifier/runs/pre-rebuild-metrics.md`. Tombstone for the existing model's provenance — without this, the trained `production_binary_rem.json` becomes an unprovenanced black box.
- **Side effect to acknowledge:** the trained sleep classifier (`production_binary_rem.json`) was trained on this data. Model file survives. Retraining later would need new data.

### D3 — Chat handler module

- **Path:** `apps/chat/` (entire module)
- **Extent:** handler.py, retrieval.py, trait_drift.py, observer.py, consolidator.py, conversation.py, cli.py, health_summary.py.
- **Replaced by:** chat as a thin client of the new layered backend.
  - User text input → L1 capture (text endpoint)
  - Decision of what Regis says → L5
  - Utterance generation → L6
  - Retrieval extracted as cross-cutting → `apps/inference/retrieval/`
  - Trait drift + observer extraction → nightly L3 jobs reading accumulated state

### D4 — Realtime classifier mashup

- **Path:** `apps/inference/realtime.py`
- **Extent:** the whole file. Currently does L2 feature extraction + L4 prediction + writes to `user_state_estimate` all in one place.
- **Replaced by:** clean split.
  - L2 features → `apps/inference/features/biometric.py`
  - L4 prediction → `apps/inference/prediction/sleep_classifier.py` (wraps trained model as registered stand-alone predictor per commitment #16)
  - Write to `user_state_estimate` → L3 historical persistence path

### D5 — Cue decider

- **Path:** `apps/inference/cue_decision.py`
- **Extent:** the file, including its 5 safety gates and threshold heuristics.
- **Replaced by:** proper L5 decision module at `apps/inference/decision/sleep_cue.py`. Reads L3 BeliefState + L4 sleep-stage predictions, applies intent dispatch (#10), respects meta-context bias (#14). The 5 safety gates survive as explicit policy checks in the new module.

### D6 — Legacy feature engine

- **Paths:** `apps/inference/feature_engine.py` + `tests/test_feature_engine.py`
- **Extent:** both files. Retired entirely per `docs/ARCHITECTURE.md §11`'s existing flag.
- **Replaced by:** `apps/inference/features/` — same job, cleaner home, per-modality submodules.

### D7 — Body-bridge L1→L3 shortcut

- **Location:** currently in `daybook.py` / `realtime.py` (the `body_state_estimate` scheduler job and supporting code).
- **Extent:** the code path that reads raw HR/HRV from `sensor_readings` and writes directly to `user_state_estimate` without going through L2 features.
- **Replaced by:** proper L1 → L2 → L3 flow. HK rows in L1 → L2 features module computes biometric features → L3 fusion combiner produces axis values → L3 writes to `user_state_estimate`. Same destination, honest path.

### D8 — Ad-hoc sleep observer

- **Path:** `apps/inference/sleep_observer.py` if it exists as a free-standing nightly script.
- **Extent:** whatever logic currently distills sleep sessions into `regis_observations`.
- **Replaced by:** L3 post-session aggregator — a nightly job in the L3 module that consumes the session's accumulated state and emits structured observations.

---

## Keep list (explicitly NOT touched)

- `apps/inference/llm/` — Sign-in-with-ChatGPT + Codex client. User-confirmed. API-bypass test path.
- `apps/inference/embeddings/` — BGE-M3. Already L2-aligned (text encoder).
- `apps/inference/db.py` — DB connection helper. Right module.
- `apps/inference/migrations/0001–0004` — schema stays; only data rows from D2 get deleted.
- `apps/api/` — FastAPI bridge per commitment #12. Routes get rewritten as backend rewrites; the bridge itself stays.
- `apps/wisp/PERSONA.md` — character bible. Untouched.
- `bin/cloudflare-tunnel-*.sh` — infrastructure scripts.
- `apps/inference/parse_apple_health.py` — script stays for future re-import.
- `apps/inference/classifier/` (training framework + `production_binary_rem.json`) — training framework wraps into L4 registry; trained model file persists.
- `apps/recall/` — light refactor to fit L1 + L2 + persistence layer boundaries.
- `apps/wisp/composer.py` — **relocate** to `apps/inference/output/utterance.py` and refactor to fit new L5/L6 interface. Composer becomes the canonical utterance renderer in L6 (resolves ambiguity about where the composer lives in the new tree).
- `packages/shared/` — TypeScript shared types. Schema source-of-truth in TS stays in sync with new migrations.

---

## Build list (new layer modules)

Target structure under `apps/inference/`:

```
apps/inference/
├── sensors/                 # L1 — intent-tagged capture contracts (per commitment #10)
│   ├── __init__.py
│   ├── contract.py          # IntentTaggedReading dataclass + capture-side adapter contract
│   └── (per-channel implementations live with their capture clients — Mac mic, HK sync, Pi mic, etc.)
├── features/                # L2 — feature extraction per modality
│   ├── __init__.py
│   ├── biometric.py         # heartpy / neurokit2 → FeatureSnapshot
│   ├── audio.py             # librosa / Whisper (when audio capture comes online)
│   ├── text.py              # wraps embeddings module
│   └── snapshot.py          # FeatureSnapshot dataclass + envelope/payload contract
├── fusion/                  # L3 — the integration spine
│   ├── __init__.py
│   ├── state.py             # per-axis storage (live + historical via user_state_estimate)
│   ├── combiners/           # per-axis combiner functions (v1 deterministic)
│   │   ├── arousal.py
│   │   ├── valence.py
│   │   ├── meta_context.py  # the meta_context axis itself (canonical writer)
│   │   └── ...
│   ├── belief_state.py      # BeliefState reader + snapshot policy
│   ├── offline.py           # OFFLINE sentinel + handling
│   └── observers/           # post-session aggregators (sleep, day-summary)
├── prediction/              # L4 — predictor registry + JEPA destination
│   ├── __init__.py
│   ├── registry.py          # (axis, meta_context) → predictor dispatch
│   ├── interface.py         # predict(axis, horizon, action) contract
│   ├── prediction_log.py    # writes to prediction_log table
│   ├── learning.py          # training pass (reads log, updates weights)
│   └── predictors/
│       ├── sleep_classifier.py    # wraps existing XGBoost as stand-alone
│       └── (more land as data permits — JEPA world model arrives last)
├── decision/                # L5 — action selection
│   ├── __init__.py
│   ├── bandit.py            # Thompson contextual bandit (carried over from learned_decider)
│   ├── policies/
│   │   ├── sleep_cue.py     # successor to cue_decision.py (5 safety gates preserved as policy)
│   │   ├── interject.py     # morning_brief, pre_sleep, inner_pulse, post_recall
│   │   └── ...
│   └── intent_dispatch.py   # routes by intent per commitment #10
├── output/                  # L6 — channel selection + render
│   ├── __init__.py
│   ├── tts.py               # Kokoro TTS, bone-conduction
│   ├── ui.py                # iOS/Watch render contracts (when clients return)
│   └── channels.py          # meta-context-aware channel selection
└── retrieval/               # cross-cutting (formerly in apps/chat/)
    ├── __init__.py
    ├── substrate.py         # gather_substrate successor
    └── pgvector.py          # HNSW similarity queries
```

L1 capture clients live where they capture from (Mac mic listener, HK sync, future Pi mic, etc.) — not centralized in one module. `sensors/contract.py` is the *contract surface* that capture clients import; the per-channel *implementations* stay at the edge.

---

## Sequence (order matters; each unblocks the next)

| # | Phase | Estimate | Unblocks |
|---|---|---|---|
| 0 | Safety moves (tag + Neon snapshot + rebuild branch + Pi-chat coordination protocol) | 30 min | Everything |
| 1 | Migration 0005 (prediction_log, consent cols, axis fields) — verify schema first | 1 day | L3, L4 |
| 2 | **L2 feature extraction** (`features/`) — biometric first, audio when capture exists | **1 week** | L3 (real inputs, not mocks) |
| 3 | L3 fusion engine — per-axis storage + BeliefState + OFFLINE + historical writes | 1–2 weeks | L4, L5, decommissioning body-bridge |
| 4 | L4 predictor registry + wrap sleep classifier as first stand-alone | 3–4 days | L5 sleep-cue policy |
| 5 | L5 decision module v1 — sleep cue + intent dispatch + bandit migration | 1 week | L6 |
| 6 | L6 output module — TTS + channel selection per meta-context + composer relocation | 3–4 days | end-to-end loop possible |
| 7 | L1 edge classifier work — intent tagging at capture clients + `sensors/contract.py` | 1 week | clean L1 contract |
| 8 | Chat handler rewrite over new layered backend | 2–3 weeks | parity with v0 chat |
| 9 | **End-to-end smoke** — simulated sensor input → L1 → L2 → L3 → L4 → L5 → L6 → TTS or text reply | 2–3 days | exit criterion #4 |
| 10 | Decommission deletes (D3–D8) after each layer's replacement is live + Pi-chat sign-off per module | rolling | clean repo |
| 11 | Wipe HK data rows (D2) — after the pre-deletion metrics tombstone is committed | 1 hr | clean Neon state |
| 12 | Delete iOS/watchOS (D1) | 5 min | repo cleanup |

**Realistic total: 9–14 weeks solo, part-time.**

Order rationale: L2 first so L3 builds against real feature inputs, not mocks. L3 next as the integration spine. L4 next so L5 has predictions to consume. L5/L6 close the loop. L1 last because edge intent tagging touches client code paths that need the rest to exist. Chat handler rewrite last because it integrates everything; the end-to-end smoke right after proves the loop actually closes.

---

## Migration 0005 contents (sketch)

```sql
-- 0005_rebuild_substrate.sql

-- L4 prediction log (commitment #16)
CREATE TABLE prediction_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  axis TEXT NOT NULL,
  meta_context TEXT NOT NULL,
  made_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  horizon_seconds INTEGER NOT NULL,
  prediction JSONB NOT NULL,                   -- distribution: mean, variance, or categorical probs
  action_conditioned_on JSONB,                 -- NULL = baseline; non-null = counterfactual
  model_id TEXT NOT NULL,
  inputs_used JSONB,
  cold_start BOOLEAN DEFAULT FALSE,
  action_conditioning_kind TEXT DEFAULT 'placeholder',  -- 'placeholder' | 'calibrated'
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_prediction_log_user_axis ON prediction_log(user_id, axis, made_at DESC);
CREATE INDEX idx_prediction_log_horizon ON prediction_log(made_at, horizon_seconds);

-- Consent metadata (cross-cutting per §8 privacy)
ALTER TABLE sensor_readings ADD COLUMN consent_scope TEXT NOT NULL DEFAULT 'personal_use';
ALTER TABLE sensor_readings ADD COLUMN consent_granted_at TIMESTAMPTZ NOT NULL DEFAULT now();
-- (repeat for chat_messages, dream_recalls, regis_moments, regis_observations, user_actions)

-- Axis fields if missing in user_state_estimate
-- (verify schema against current state before writing this section)
```

**Open:** verify which axis fields already exist in `user_state_estimate` before drafting the ALTERs. Run a `\d user_state_estimate` first.

---

## Decision checkpoints (each phase ends with explicit user sign-off)

Each phase produces:
1. A working module that passes its smoke test.
2. A short "what's live, what's stubbed" note.
3. A `git tag rebuild/phase-N-complete` mark.

User approves before next phase starts. Phases don't bundle — each one is its own commit + tag.

---

## Open questions (must resolve before/during)

| Q | Why it matters | When to decide |
|---|---|---|
| **Schema delta.** What axis fields already exist in `user_state_estimate` vs what migration 0005 needs to add? | Migration accuracy. | During Phase 1 (verify before writing the ALTERs). |
| **Action embedding space.** How are Regis actions represented in L4's `action` parameter? (Categorical kind only? Sparse embedding? Same space as utterance embedding?) | Affects L4 contract and L5 dispatch. | During Phase 4. |
| **Sleep classifier retraining.** With HK data wiped, do we ever retrain, or treat the existing model as a frozen baseline forever? | Affects L4 sleep-stage predictor's evolution. | Phase 4 or later. |
| **Subsystem docs.** Write `FUSION.md` + `PREDICTION.md` during their respective phases, or after the rebuild? | Doc bloat vs in-context reference. | Phase 3 (FUSION.md) decision; Phase 4 (PREDICTION.md) decision. |

*(Validation-wedge timing and Pi-side coordination were resolved — see "Why this exists" and Safety move #4.)*

---

## Exit criteria (the rebuild is "done" when…)

1. Every commitment in `docs/ARCHITECTURE.md §2` has corresponding code that honors it (verified by spot-checking against §11 gap entries — they should all be closeable or explicitly deferred).
2. The §11 implementation gap index drops to <5 entries (down from 20).
3. Every layer L1–L6 has a smoke test that passes (`python -m {layer}.smoke_test`).
4. A full end-to-end smoke run works: simulated sensor input → L1 → L2 → L3 → L4 → L5 → L6 → audible TTS or text reply.
5. The chat handler is fully replaced; `apps/chat/` no longer exists.
6. STATUS.md reflects the new architecture as live.
7. ARCHITECTURE.md §11 gap list is updated (closed entries removed, new gaps that emerged added).

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Solo timeline slips past 12 weeks | High | Phases are independent; can pause between them. Validation wedge runs in parallel on `main` if user picks that option. |
| L3 design surfaces issues mid-build that require ARCHITECTURE.md updates | Medium | Expected. Update the doc when the issue surfaces — the doc has been written as evolving. |
| Re-importing HK data later turns out to be necessary | Low | `parse_apple_health.py` stays. Neon branch snapshot keeps the data accessible. Reversible. |
| iOS rebuild gets deferred indefinitely | Medium | Acceptable. FastAPI bridge stays usable; testing happens via curl + LLM-client API-bypass path. |
| Trained sleep classifier loses validation when retrained on new data | Medium | Keep the existing model file as a frozen baseline. Retraining is a separate decision later. |

---

## Sign-off

Before execution begins, user confirms:
- [ ] Scope is correct (delete map + keep list + build list).
- [ ] Safety moves (Phase 0) execute first, before any delete.
- [ ] Phase sequence (#1–#12) approved.
- [ ] Pi-chat coordination protocol is acceptable (gate each D-delete on Pi sign-off).

After sign-off, execution starts at Phase 0.
