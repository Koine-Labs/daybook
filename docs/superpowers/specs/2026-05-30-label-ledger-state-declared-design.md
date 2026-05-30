# Label Ledger + `state_declared` — Design Spec

**Date:** 2026-05-30
**Branch:** `feat/label-ledger` (worktree)
**Scope:** Commitment #17 steps **#1 (evidence ledger substrate)** + **#2 (`state_declared` keystone)**. Defers literature priors (#3), cold-start arbitration (#4), and the offline fusion-ablation harness (#5) to follow-on worktrees off the merged `main`.

This is the **labeling and cold-start substrate** — the layer that lets future sensor data become *meaningful* by giving every label-like datum a recorded origin, and by adding the first high-value label source (explicit self-report).

---

## 1. Why this, why now

The labeling architecture is already **codified** as `ARCHITECTURE.md` Commitment **#17** ("Labels are provenance-scoped priors, not truth by default") plus the §6 source-set fusion note and the §9 open-questions log. What does **not** exist yet (per the architecture's own gap index): *"no unified label store, self-report axis, literature/LLM extraction workflow, demographic-prior store, or provenance-weighted training loader."*

The single existing hook is `AxisEstimate.source: str` (a freetext provenance string on the 7 live L3 axes). This build turns that toehold into a real substrate.

`state_declared` has been deferred **twice** (see STATUS 2026-05-29) for one honest reason: *"Intent.EXPLICIT is an unused enum; the one real transcript bypasses the bus."* This build resolves that deferral by making **Intent.EXPLICIT a real end-to-end path** and giving it the ledger to write into.

---

## 2. Load-bearing decisions

**D1 — The ledger stores calibration-grade *labels*, not the continuous belief stream.**
`label_observations` holds discrete, provenance-bearing data used for calibration / training / cold-start: `self_report`, `ground_truth`, `observed_outcome`, `literature_prior`, `demographic_prior`, `llm_literature_bootstrap`, `clinician`. Continuous inferred per-tick beliefs **stay** in `user_state_estimate_v2` (which already carries `source` + `confidence`). Rationale: #17's record fields describe *labels for training*; folding 7 axes × ~2880 ticks/day of inferred belief into the ledger would drown the calibration signal and bloat the table. The offline harness (#5) later *joins* `self_report` ledger labels against `user_state_estimate_v2` beliefs on `(user, axis, time)` to grade the inferred axes — separate tables make that join natural.

**D2 — One provenance vocabulary, system-wide.** A typed `LabelSource` enum mirrors #17's eight sources exactly. The 7 live axes' freetext `source` strings normalize onto this vocabulary (lightweight retrofit) so the whole system speaks one provenance language. Inferred axes remain tier `heuristic`/`literature_prior` priors — they do **not** each spam ledger rows (per D1).

**D3 — `state_declared` is real ground truth, not a scaffold.** Unlike `arousal_inferred`/`affect_prosody` (`scaffold=True`), an explicit self-report is high-confidence truth. It writes `self_report` ledger labels keyed to the **inferred axes it speaks to** (a declaration "wiped but wired" → labels for `fatigue` + `arousal`), which is exactly the ground truth the inferred axes get graded against.

**D4 — The declaration rides the bus (honors the architecture, resolves the deferral).** L1 EXPLICIT producer → L2 classifier → L3 axis → ledger. Not a side-channel. This lights up `Intent.EXPLICIT` for the first time.

**D5 — LLM-structured classifier with a deterministic quick-pick fallback.** `ChatClient.chat_structured` maps free text → structured axis claims; a small offline lexicon fallback keeps CI **DB-free and LLM-free** (the repo's "green from clean caches with no DATABASE_URL" convention).

---

## 3. Data model — migration `0011_label_ledger.sql`

Append-only, additive. Applied to the shared Neon DB via the Neon MCP (`run_sql_transaction`), then verified by a DB-gated smoke (insert → readback → delete).

```sql
BEGIN;

CREATE TABLE IF NOT EXISTS label_observations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL,
    axis          TEXT NOT NULL,              -- target axis the label speaks to (arousal, fatigue, cognitive_load, sleep_stage, focus, mood, ...)
    value         JSONB NOT NULL,             -- scalar / category / distribution claimed for the axis
    confidence    REAL NOT NULL DEFAULT 0.5,  -- [0,1] strength of THIS label
    source        TEXT NOT NULL,              -- LabelSource taxonomy (see §4)
    provenance    JSONB NOT NULL DEFAULT '{}'::jsonb,  -- source-specific lineage (citation, model, population, limitations, declaration_text, outcome_ref, classifier)
    consent_scope TEXT NOT NULL DEFAULT 'unscoped_v0',
    i_model_id    UUID NULL,                  -- commitment #1
    meta_context  TEXT NULL,                  -- commitment #14 (waking/sleep) when known
    observed_at   TIMESTAMPTZ NOT NULL,       -- when the labeled moment occurred
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()  -- when the row was written
);

CREATE INDEX IF NOT EXISTS idx_label_obs_user_axis_time
    ON label_observations (user_id, axis, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_label_obs_user_source
    ON label_observations (user_id, source);

COMMIT;
```

`#3`/`#4`/`#5` will own migrations `0012`/`0013`/`0014` respectively (pre-allocated to prevent collisions when those run as parallel worktrees). They add their own tables (`literature_priors`, `cold_start_profiles`, etc.); they do **not** alter `label_observations`.

TS mirror: add the `LabelObservation` entity shape + a `LabelSource` union to `packages/shared/src/types.ts` (DB is the source of truth; keep TS in sync per convention).

---

## 4. The `labels/` package (the frozen contract)

New package `apps/inference/labels/`:

- **`labels/provenance.py`** — `class LabelSource(str, Enum)` with the eight #17 values:
  `GROUND_TRUTH`, `SELF_REPORT`, `OBSERVED_OUTCOME`, `HEURISTIC`, `LITERATURE_PRIOR`, `DEMOGRAPHIC_PRIOR`, `LLM_LITERATURE_BOOTSTRAP`, `CLINICIAN`.
  A `TRUST_ORDER` tuple expresses the epistemic ladder (ground_truth highest). A unit test asserts the enum is exactly the #17 set (catches drift if #17 changes).

- **`labels/record.py`** — `@dataclass LabelRecord` mirroring the table (`user_id, axis, value, confidence, source: LabelSource, provenance: dict, consent_scope, i_model_id, meta_context, observed_at`). `to_row()` helper for the writer.

- **`labels/ledger.py`** — DB-wrapped, crash-safe (mirrors `fusion/writer.py` + `loader.py`):
  - `record_label(rec: LabelRecord) -> str | None` — INSERT, returns id; swallows DB errors with a logged warning (never crashes the arc), returns `None` when DB absent.
  - `record_labels(recs: list[LabelRecord]) -> int` — batch.
  - `read_labels(user_id, axis=None, sources=None, since=None, limit=None) -> list[LabelRecord]` — the read path #4/#5 will consume.
  - Uses `from db import get_conn` (never re-implements connection logic).

---

## 5. The `state_declared` lane

### L1 — `sensors/declare_adapter.py`
`DeclarationBusSink` (transport-agnostic; holds only a `MessageBus`, mirrors `WatchBusSink`/`EEGBusSink`). `declare(text, *, user_id, meta_context=MetaContext.WAKING)` builds an `IntentTaggedReading(modality=Modality.TEXT, intent=Intent.EXPLICIT, payload={"kind": "state_declaration", "text": text}, consent_scope="self_report_v1")` and calls `publish_reading(...)`. Voice/watch/gesture later feed text into the same sink — no rebuild.

### L2 — `features/declaration.py`
Registered for `Modality.TEXT`, guarded on `kind == "state_declaration"` (returns OFFLINE/`None` for other text). Maps text → structured claims:
- **Primary:** `ChatClient.chat_structured(system, user, DeclaredState)` where `DeclaredState` is a Pydantic model: `claims: list[Claim]` with `Claim = {axis: str, value: float|str, confidence: float}` + `note: str`.
- **Fallback (CI / no-auth / `DAYBOOK_DECLARE_OFFLINE=1`):** a small deterministic lexicon (`focused/locked in → focus↑`, `tired/wiped → fatigue↑`, `anxious/wired → arousal↑`, `calm → arousal↓`, ...).
Returns a `FeatureSnapshot` with `features={"claims": [...], "raw_text": text, "classifier": "llm"|"quickpick"}`.

### L3 — `fusion/axes/state_declared.py`
`fuse_from_feature(snapshot, meta_context=None)`:
- Produces a `state_declared` `AxisEstimate` (`value={"claims": [...], "raw_text": ...}`, `confidence=0.9`, `source=LabelSource.SELF_REPORT.value`, `scaffold=False`).
- For **each** claim, builds a `LabelRecord` (`axis=claim.axis`, `value=claim.value`, `confidence=claim.confidence`, `source=SELF_REPORT`, `provenance={"declaration_text": raw_text, "classifier": ...}`, `consent_scope="self_report_v1"`, `meta_context`, `observed_at=now`). Ledger writes happen via a dedicated belief-subscriber in the arc (see below), **not** inline in `fuse_from_feature` (keep the axis pure/testable; ledger I/O is a side-effecting subscriber).
- Registered in `AXIS_REGISTRY` → **8th live axis**.

### Orchestration — `state/` lane + surfaces
- **`apps/inference/state/declare.py`** — `assemble_declaration_arc(bus)` registers the L2 extractor, the L3 axis, and a `record_self_report_labels` subscriber on `TOPIC_BELIEF` (writes the per-claim `LabelRecord`s + persists the `state_declared` belief). `declare_state(text, *, user_id, persist=True) -> DeclarationResult` runs the in-process arc synchronously and returns the parsed claims + written label ids (for CLI/API/tests).
- **CLI:** `python -m state.declare "I'm locked in"` (mirrors `recall.capture` ergonomics; `--offline` forces quick-pick; `--user` override).
- **API:** `POST /state/declare` in `apps/api/routes/state.py` → `{text}` body → `declare_state(...)` → returns claims + label ids. Auth via existing `X-API-Key` middleware; user via `current_user_id()`.

---

## 6. Retrofit — normalize the 7 axes onto the taxonomy (light)

Each live axis (`meta_context`, `sleep_stage`, `audio_social_context`, `cognitive_load`, `visual_context`, `arousal_inferred`, `affect_prosody`) keeps its descriptive `source` but maps it onto a `LabelSource` tier (most are `HEURISTIC`; the ones with literature grounding, e.g. `arousal_inferred`'s HRV basis, are `LITERATURE_PRIOR`). Implementation: a `labels.provenance.classify_source(source_str) -> LabelSource` helper + a test asserting every live axis' `source` resolves to a valid tier. **No behavior change to the axes**; this only makes provenance legible system-wide and is the seam #4/#5 read.

---

## 7. Testing (TDD, DB-free + LLM-free CI)

Write tests first per component. Full CI-mirror suite (`core sensors features fusion prediction decision output bci vision labels state`) must stay green with **no `DATABASE_URL`** (verified baseline before this build, the 9 layer dirs: **289 passed, 2 skipped**; the wider `apps/inference` suite is ~307).

- `labels/`: enum-completeness vs #17; `LabelRecord` round-trip; `record_label`/`read_labels` with `get_conn` monkeypatched (DB-free) + a DB-gated real smoke.
- migration `0011`: DB-gated smoke (table exists, insert→readback→delete).
- L1 `declare_adapter`: emits `SignalPacket` with `Intent.EXPLICIT` + `kind="state_declaration"` + `consent_scope="self_report_v1"`.
- L2 `declaration`: quick-pick deterministic; LLM path with `chat_structured` mocked; non-declaration text → OFFLINE.
- L3 `state_declared`: belief shape + per-claim `LabelRecord`s emitted (ledger mocked); `source=self_report`, `scaffold=False`.
- e2e arc: `declare_state("wiped but wired", offline=True)` → `state_declared` belief + `fatigue`+`arousal` self_report labels (DB + LLM mocked).
- retrofit: each of the 7 axes' `source` resolves via `classify_source`.

---

## 8. Commitment alignment (theory-aligner gate before merge)

- **#1** — `label_observations.i_model_id` present (null until clustering).
- **#10** — declaration tagged `(Intent.EXPLICIT, Modality.TEXT)`; first real EXPLICIT path.
- **#11** — explicit self-report is user-volunteered (not continuous capture); `consent_scope="self_report_v1"` stamped.
- **#14** — `meta_context` on the label (default `waking`; declarations don't occur in deep sleep).
- **#17** — the build itself: provenance taxonomy, `self_report` tier, provenance jsonb with `declaration_text` + `classifier`; `state_declared` is honest ground truth (`scaffold=False`) vs the inferred scaffolds.
- **Honesty over theater** — quick-pick fallback is labeled `classifier:"quickpick"` in provenance, not passed off as LLM understanding.

---

## 9. Build sequence (workflow phases)

1. **Foundation (sequential, single author):** migration `0011` + `labels/` package (provenance, record, ledger) + tests. The frozen contract.
2. **Lane (sequential, single author):** `state_declared` L1+L2+L3 + `state/declare.py` orchestrator + CLI + `POST /state/declare` + tests. Registers into `AXIS_REGISTRY` / `EXTRACTORS`.
3. **Retrofit (parallel, one agent per axis):** `classify_source` + normalize each of 7 axes (independent files → safe parallel) + test.
4. **Adversarial review (parallel lenses):** data-model correctness; architecture-cohesion + commitment alignment; build-feasibility / blast-radius / test-coverage.
5. **Controller integration:** apply 0011 via Neon MCP, run full DB-free suite + DB-gated smokes, fix review findings, run `theory-aligner`, commit, fast-forward-merge to `main`.

Shared-file edits (`AXIS_REGISTRY`, `EXTRACTORS`, `routes/state.py`) stay inside the single-author phases (1–2) to avoid parallel collisions; only the per-axis retrofit fans out.

---

## 10. After merge — the parallel back-half (#3/#4/#5)

Once this merges to `main`, spin three worktrees off the updated `main` (the worktree+venv flow is proven here): `feat/literature-priors` (#3, migration 0012), `feat/cold-start` (#4, migration 0013), `feat/fusion-ablation` (#5, migration 0014). Guardrails: pre-allocated migration numbers (above) + the frozen `labels/ledger.py` read/write API (none may fork it). #4/#5 are meaningful only once real labels exist in the ledger — which this build creates.
