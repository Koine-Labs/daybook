# Design Spec — #3 Literature-Prior Registry

> Status: DESIGN ONLY. No code or migrations in this artifact. A later build workflow executes it.
> Pre-allocated migration number: **0012** (`apps/inference/migrations/0012_literature_priors.sql`).
> Depends on #1 Label Ledger (branch `feat/label-ledger`: `apps/inference/labels/` package + `migrations/0011_label_ledger.sql` / `label_observations`) and #2 `state_declared`. Branches off **merged `main`** per the #1 spec §10.
> Grounding: ARCHITECTURE.md commitment **#17 "Labels are provenance-scoped priors, not truth by default"**, the §6 **"Source-set fusion evaluation"** note, the §9 open question **"Label store shape"**, and the FROZEN ledger contract in `docs/superpowers/specs/2026-05-30-label-ledger-state-declared-design.md`.

---

## 0. One-paragraph summary

The Literature-Prior Registry is a **curated, citation-backed store of weak priors** that map a sensor/feature condition to a claimed value on a target axis (e.g. "HRV/RMSSD decrease → arousal increase, healthy-adult population"; "frontal theta/beta ratio elevated → cognitive load increase"). It is a **registry** (the `literature_priors` table) layered *on top of* the frozen #1 ledger — it does not replace, fork, or alter the ledger. Each prior carries everything commitment #17 demands: **target axis, the rule (feature condition → claimed value), citation/source, applicable population, confidence, and known limitations**. Priors enter as `LLM_literature_bootstrap` *candidates* — proposed by a **human-reviewable** LLM-extraction pass over a *small, locally-curated corpus* (never autonomous internet scraping) — and only become **live** (consumable, and writable into the ledger at `LabelSource.LITERATURE_PRIOR`) after passing a **review/promotion gate** that validates the candidate against evidence *read from the ledger itself* (instrumented / self-report / outcome labels). Live priors are consumed two ways: **(a) cold-start (#4)** — when a user/axis has no direct evidence, materialize the prior as a single weak label; **(b) weak supervision / priors to L3 fusion + L4 training** — supply down-weighted, population-tagged signals that fusion and the world model lean on early and discount as real data accrues. The honesty value is load-bearing: this is a **small seed set + a human gate**, not a scraper that launders unvetted claims into the substrate.

---

## 1. Scope

### In scope
- Migration **0012** adding three additive tables: `literature_sources`, `literature_priors`, `literature_prior_promotions` (no ALTER of any ledger object).
- A new typed (3.11+) package **`apps/inference/literature_priors/`** providing:
  - registry CRUD + lifecycle (`candidate → reviewed → live → retired`),
  - the **LLM-extraction workflow** that turns a curated corpus into `LLM_literature_bootstrap` candidate rows (human-reviewable proposer, dry-run by default),
  - the **promotion gate** that validates a candidate against ledger evidence before flipping it `live`,
  - the **consumer API** that reads live priors and (i) provides weak supervision/priors to L3 fusion + L4 training and (ii) materializes a prior as a `LITERATURE_PRIOR` ledger label for cold-start (#4).
- A **small curated seed set** (data, not a crawler): a versioned `seed/` dir of hand-collected paper excerpts + a JSON seed of ~6–12 well-established priors so the registry is non-empty on day one.
- DB-free + LLM-free CI tests (repo convention).

### Out of scope (explicit non-goals)
- **Redefining the ledger.** The `labels/` package, `LabelSource` taxonomy, `LabelRecord`, `ledger.record_label`/`record_labels`/`read_labels`, and `label_observations` are consumed **as-is**.
- **Autonomous web scraping / live paper ingestion.** No network in the extraction module's runtime surface. The corpus is local, curated, committed.
- **Auto-promotion.** Promotion is human-in-the-loop in v1.
- **New axes.** Axes come from #2 `state_declared`; this registry references existing axis ids, it does not mint them.
- **Per-user prior personalization.** Priors are population-scoped; user binding happens only at materialization time.

---

## 2. How this consumes the frozen #1 ledger contract (verified)

This subsystem is a **producer and reader** of the ledger, never an owner of it. The surface below is **verified** against `apps/inference/labels/*.py` + `migrations/0011_label_ledger.sql` (build re-confirms when branching off merged `main`):

- `labels.LabelSource(str, Enum)` already contains `LITERATURE_PRIOR` and `LLM_LITERATURE_BOOTSTRAP` (plus `GROUND_TRUTH`, `SELF_REPORT`, `OBSERVED_OUTCOME`, `HEURISTIC`, `DEMOGRAPHIC_PRIOR`, `CLINICIAN`) and a `TRUST_ORDER` ladder.
- `labels.LabelRecord` (dataclass) fields: `user_id, axis, value, confidence, source: LabelSource, provenance: dict, consent_scope, i_model_id, meta_context, observed_at`. (No `id`/`created_at` — DB-assigned.)
- `labels.ledger.record_label(rec: LabelRecord) -> str | None` (crash-safe; returns `None` when DB absent), `record_labels(recs) -> int`, and **`read_labels(user_id, axis=None, sources=None, since=None, limit=None) -> list[LabelRecord]`** — note reads key by **`user_id`** and filter by **`sources=` (plural list)**.
- `label_observations` columns: `id, user_id, axis, value JSONB, confidence REAL, source TEXT, provenance JSONB, consent_scope, i_model_id, meta_context, observed_at, created_at`.

**Contract rules this subsystem obeys:**
1. **Registry ≠ ledger.** A `literature_priors` row is a *reusable, population-level rule*; it is NOT a `label_observations` row and carries **no `user_id`**. A row is appended to `label_observations` (via `record_label`) **only when a live prior is materialized** over a concrete `(user_id, window)`. (Proposed answer to the §9 "Label store shape" question — build confirms.)
2. **Source attribution is exact.** Materialized weak labels are written with `source=LabelSource.LITERATURE_PRIOR`. The candidate-stage extraction never writes to `label_observations`; candidates live only in `literature_priors` (`status='candidate'`, `origin='llm_literature_bootstrap'`). The `LLM_LITERATURE_BOOTSTRAP` origin is preserved in the ledger row's `provenance.proposed_source` when a bootstrap-origin prior is later materialized, so provenance is never lost.
3. **Provenance round-trips.** Every materialized ledger row carries, in `provenance`, the originating `literature_prior_id`, `citation`, `population`, `known_limitations`, and an idempotency key — so any label traces back to the paper that justified it (#17).
4. **The gate READS, never WRITES, the ledger.** `promote_prior` calls `ledger.read_labels(user_id, axis=..., sources=[GROUND_TRUTH, SELF_REPORT, OBSERVED_OUTCOME], ...)` and compares the rule's predictions to that evidence. It writes nothing to the ledger; it writes a `literature_prior_promotions` audit row and flips the registry row's `status`.

---

## 3. Data model — full DDL for migration 0012

`apps/inference/migrations/0012_literature_priors.sql` — append-only, additive. Apply via psycopg in a DB-gated smoke (NOT `psql`, per CLAUDE.md), or the Neon MCP `run_sql_transaction` as the #1 build did. Does NOT touch `label_observations`.

```sql
BEGIN;

DO $$ BEGIN
    CREATE TYPE literature_prior_status AS ENUM (
        'candidate',   -- proposed (LLM bootstrap / hand-entry / seed); NOT consumable
        'reviewed',    -- a human has read it; awaiting validation evidence
        'live',        -- passed the promotion gate; consumable + materializable
        'retired'      -- superseded / refuted / withdrawn
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE literature_prior_origin AS ENUM (
        'llm_literature_bootstrap',  -- proposed by the LLM-extraction pass
        'hand_entered',              -- a human typed it directly
        'seed'                       -- shipped in the curated seed set
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- A curated source document (paper / dataset / textbook chapter / review).
-- Local + cited; this is the corpus the extraction reads from.
CREATE TABLE IF NOT EXISTS literature_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citation        TEXT        NOT NULL,        -- human-readable citation string
    doi             TEXT        NULL,
    url             TEXT        NULL,            -- canonical link (NOT fetched at runtime)
    corpus_path     TEXT        NULL,            -- local path to the curated excerpt (inside seed/)
    source_kind     TEXT        NOT NULL,        -- 'paper' | 'dataset' | 'textbook' | 'review'
    population_note TEXT        NULL,            -- study sample (e.g. 'healthy adults 18-35, N=42')
    added_by        TEXT        NOT NULL DEFAULT 'human',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (citation)
);

-- The registry: each row is one weak, citation-backed prior (a reusable, population-level rule).
-- NOT a label_observations row. Carries NO user_id. Becomes a ledger label only at materialization.
CREATE TABLE IF NOT EXISTS literature_priors (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- WHAT IT CLAIMS (commitment #17 required fields)
    target_axis         TEXT        NOT NULL,    -- references an axis id from #2 state_declared / live axes
    rule                JSONB       NOT NULL,    -- the feature-condition -> claimed-value rule (schema in §3.1)
    claim_summary       TEXT        NOT NULL,    -- one-line human-readable claim
    population          TEXT        NOT NULL,    -- applicable population (e.g. 'healthy adults')
    applicability       JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- structured gates (age range, context, modality)
    confidence          REAL        NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    known_limitations   TEXT        NOT NULL,    -- honest caveats; NOT NULL on purpose (#17)

    -- PROVENANCE
    source_id           UUID        NOT NULL REFERENCES literature_sources(id),
    origin              literature_prior_origin NOT NULL,
    extracted_excerpt   TEXT        NULL,        -- the exact text the rule was drawn from

    -- LIFECYCLE
    status              literature_prior_status NOT NULL DEFAULT 'candidate',
    superseded_by       UUID        NULL REFERENCES literature_priors(id),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lit_priors_axis_status
    ON literature_priors (target_axis, status);
CREATE INDEX IF NOT EXISTS idx_lit_priors_status
    ON literature_priors (status);

-- Audit trail of every promotion-gate decision. The gate is the ONLY path candidate/reviewed -> live.
CREATE TABLE IF NOT EXISTS literature_prior_promotions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prior_id             UUID        NOT NULL REFERENCES literature_priors(id),
    from_status          literature_prior_status NOT NULL,
    to_status            literature_prior_status NOT NULL,

    -- VALIDATION EVIDENCE (READ from the #1 ledger; summarized here, not duplicated)
    evidence_user_id     UUID        NULL,       -- the user whose ledger supplied evidence (N=1 today)
    evidence_axis        TEXT        NOT NULL,
    evidence_label_count INTEGER     NOT NULL,   -- how many ledger labels were compared
    evidence_sources     TEXT[]      NOT NULL,   -- which LabelSource values supplied evidence
    validation_metric    TEXT        NOT NULL,   -- e.g. 'sign_agreement_rate'
    validation_score     REAL        NULL,       -- the measured statistic
    passed               BOOLEAN     NOT NULL,
    decided_by           TEXT        NOT NULL,   -- human reviewer id; auto-promotion forbidden in v1
    rationale            TEXT        NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lit_promotions_prior
    ON literature_prior_promotions (prior_id, created_at DESC);

COMMIT;
```

### 3.1 The `rule` JSONB schema (canonical; Python-mirrored + validated)

```jsonc
{
  "feature": "hrv_rmssd",          // feature/sensor id the condition reads
  "modality": "biometric",         // L1 modality axis (commitment #10)
  "operator": "decrease",          // 'decrease'|'increase'|'gt'|'lt'|'in_band'|'ratio_gt'
  "threshold": null,               // numeric threshold when operator is gt/lt/in_band/ratio_gt
  "window_s": 60,                  // analysis window the condition applies over
  "claim": {
    "axis": "arousal_inferred",    // MUST equal target_axis (validated)
    "direction": "increase",       // 'increase'|'decrease' for directional claims
    "value": null,                 // categorical/continuous value for absolute claims
    "magnitude": "weak"            // qualitative effect size from the source
  },
  "context_gate": { "meta_context": "waking" }  // commitment #14 meta/sub-context bias
}
```

`applicability` example: `{"age_min": 18, "age_max": 65, "excludes": ["beta_blockers"], "meta_context": "waking"}`. The claim value encoding MUST match the #2 `state_declared`/live-axis convention (see open question) so consumers need no per-call translation.

---

## 4. Module layout under `apps/inference/`

Mirrors existing package style (`labels/`, `embeddings/`, `llm/`): thin public `__init__.py`, a `db.py`-backed store, pure logic split from IO so CI is DB-free + LLM-free.

```
apps/inference/literature_priors/
├── __init__.py            # public surface: priors_for, weak_supervision_for, materialize_prior,
│                          #   register_candidate, review_prior, promote_prior, retire_prior
├── models.py              # dataclasses/Pydantic: LiteraturePrior, Rule, RuleClaim, LiteratureSource,
│                          #   Promotion, PriorStatus, PriorOrigin, WeakLabel, SubjectProfile, Context
├── store.py               # DB CRUD over the 0012 tables (uses `from db import get_conn`)
├── rules.py               # PURE: evaluate_rule(rule, features, context) -> RuleClaim|None.
│                          #   No DB, no LLM, no network — the unit-test heart
├── extract.py             # LLM-extraction workflow (LLM_literature_bootstrap candidate proposer)
├── gate.py                # promotion gate: validate_against_ledger() + promote_prior()
├── consume.py             # consumer API: priors_for, weak_supervision_for, materialize_prior, applies_to_user
├── emit.py                # the ONLY place that calls labels.ledger.record_label(...)
├── seed/
│   ├── seed_priors.json   # ~6-12 curated, hand-verified priors (the small seed set)
│   ├── sources.json       # the curated literature_sources rows
│   └── corpus/            # local excerpt files (paper snippets) — committed, no network
├── load_seed.py           # idempotent loader: seed/*.json -> tables (status='reviewed' by default)
├── cli.py                 # `python -m literature_priors.cli` review/promote/list workflow
├── smoke_test.py          # end-to-end (DB+LLM) smoke test, mirrors repo convention
└── README.md              # run instructions + the honesty statement (no scraping)
```

**Conventions:** per CLAUDE.md — `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "inference"))` then `from db import get_conn`; within `apps/inference/` import `labels` directly; `from __future__ import annotations`, full type hints, tz-aware UTC datetimes, `pathlib.Path`.

---

## 5. Key functions / contracts

### 5.1 Registry lifecycle (`store.py` / `gate.py`, re-exported by `__init__.py`)

```python
def register_candidate(prior: LiteraturePrior) -> UUID:
    """Insert a status='candidate' prior. origin must be llm_literature_bootstrap | hand_entered.
    NEVER writes to label_observations. Validates rule.claim.axis == target_axis and
    known_limitations is non-empty (#17)."""

def review_prior(prior_id: UUID, reviewer: str, notes: str | None = None) -> None:
    """Human marks candidate -> reviewed (read + sane)."""

def promote_prior(prior_id: UUID, *, reviewer: str, evidence_user_id: UUID,
                  metric: str = "sign_agreement_rate",
                  min_labels: int = 20, threshold: float = 0.6) -> Promotion:
    """THE GATE. reviewed -> live. Refuses unless validate_against_ledger passes:
       reads ledger evidence via read_labels(evidence_user_id, axis=target_axis,
       sources=[GROUND_TRUTH, SELF_REPORT, OBSERVED_OUTCOME], ...), scores rule predictions,
       writes a literature_prior_promotions row (pass or fail). reviewer is REQUIRED
       (auto-promotion forbidden in v1)."""

def retire_prior(prior_id: UUID, reviewer: str, reason: str,
                 superseded_by: UUID | None = None) -> None:
    """Any status -> retired. Live priors stop being consumable immediately."""
```

### 5.2 Pure rule evaluation (`rules.py`) — the testable core

```python
def evaluate_rule(rule: Rule, features: Mapping[str, float],
                  context: Context | None = None) -> RuleClaim | None:
    """Pure. Returns the predicted claim (direction/value + axis) iff the rule's condition
       AND context_gate are satisfied by `features`/`context`, else None.
       NO DB, NO LLM, NO network."""
```

### 5.3 LLM-extraction workflow (`extract.py`) — human-reviewable seed proposer

```python
def propose_candidates_from_corpus(corpus_dir: Path, axes: Sequence[str],
                                   client: "ChatClient", dry_run: bool = True
                                   ) -> list[LiteraturePrior]:
    """Read LOCAL curated excerpts (corpus_dir only — no network), ask the LLM via
       ChatClient.chat_structured to extract candidate rules in the canonical `rule` schema
       for the given axes, return them as origin='llm_literature_bootstrap',
       status='candidate' objects. dry_run=True (default) returns proposals WITHOUT
       persisting — a human reviews/edits known_limitations/population/confidence, then
       calls register_candidate on the keepers.
       Honesty guard: corpus_dir MUST resolve inside the package seed/ tree (raises otherwise);
       the module imports no HTTP client."""
```

Workflow shape (deliberately not autonomous): human curates excerpt + `literature_sources` row → `propose_candidates_from_corpus(dry_run=True)` → human inspects/edits → `register_candidate` → `review_prior` → `promote_prior` (ledger-validation gate).

### 5.4 Consumer API (`consume.py` + `emit.py`)

```python
def priors_for(axis: str, *, context: Context | None = None,
               subject: SubjectProfile | None = None,
               status: PriorStatus = PriorStatus.LIVE) -> list[LiteraturePrior]:
    """Live priors for an axis, filtered by applies_to_user(prior, subject) so
       population-mismatched priors are excluded. Used by cold-start (#4), L3, L4."""

def weak_supervision_for(axis: str, features: Mapping[str, float],
                         context: Context, subject: SubjectProfile) -> list[WeakLabel]:
    """For a concrete feature window: evaluate every applicable live prior, return satisfied
       claims as down-weighted WeakLabel objects (confidence from the prior; population +
       citation + known_limitations attached). Does NOT write the ledger — L3 fusion / L4
       training decide whether to consume or materialize."""

def materialize_prior(prior_id: UUID, user_id: UUID, window: Window,
                      features: Mapping[str, float], context: Context) -> str | None:
    """COLD-START path (#4). If the live prior fires on this window, write ONE weak label to
       the #1 ledger via emit.record_weak_label (source=LITERATURE_PRIOR, provenance carrying
       {literature_prior_id, citation, population, known_limitations, proposed_source,
       idempotency_key}). Returns the ledger id, or None if the rule didn't fire."""

def applies_to_user(prior: LiteraturePrior, subject: SubjectProfile | None) -> bool:
    """Pure population/applicability gate (age range, excludes, meta_context). True if
       subject is None (unknown) only when prior.applicability has no hard gates."""
```

`emit.py` is the single chokepoint touching the ledger:

```python
def record_weak_label(claim: RuleClaim, prior: LiteraturePrior,
                      user_id: UUID, window: Window) -> str | None:
    """Build LabelRecord(user_id=user_id, axis=claim.axis, value=<encoded claim>,
       confidence=prior.confidence, source=LabelSource.LITERATURE_PRIOR,
       provenance={literature_prior_id, citation, population, known_limitations,
       proposed_source, idempotency_key}, consent_scope='literature_prior_v1',
       meta_context=context.meta_context, observed_at=window.end)
       and call labels.ledger.record_label(record). The ONLY function importing record_label."""
```

### 5.5 Source-set fusion alignment (§6 of ARCHITECTURE.md)

`priors_for`/`weak_supervision_for` always return the **source tag, confidence, and population** so a fusion-evaluation harness (#5) can run leave-one-source-out and measure the marginal value of literature priors vs instrumented/self-report sources. Literature priors are explicitly the **weakest** rung of `LabelSource.TRUST_ORDER` and must be down-weighted relative to instrumented labels; the consumer API never hides the source.

---

## 6. The promotion gate (detail)

`gate.validate_against_ledger(prior, evidence_user_id, metric, min_labels)`:
1. `ledger.read_labels(evidence_user_id, axis=prior.target_axis, sources=[GROUND_TRUTH, SELF_REPORT, OBSERVED_OUTCOME], ...)` fetches evidence labels.
2. For each evidence label with co-located feature data, run `evaluate_rule` and compare predicted direction/value to the observed label.
3. Compute `validation_score` (default `sign_agreement_rate`: fraction of windows where predicted direction matches observed change). Metrics are pluggable (stored on the promotion row).
4. **Pass condition:** `evidence_label_count >= min_labels AND validation_score >= threshold AND reviewer is not None`.
5. On pass: write a `literature_prior_promotions` row (`passed=true`), flip `literature_priors.status='live'`. On fail: write the audit row (`passed=false`), leave status unchanged. Honesty over theater — a prior that can't be validated stays a reviewed candidate.

The cold-start tension is acknowledged: literature priors are most needed exactly when there's least evidence to validate them. `min_labels` is the throttle; an explicit `provisional_live` bypass is a **deferred future**, logged as an open question, not built in v1.

---

## 7. The small curated seed set (data, not a crawler)

`seed/seed_priors.json` ships ~6–12 well-established, textbook-grade priors so the registry is non-empty and the consumer/L3/L4 paths are exercisable immediately. Each carries citation, population, confidence, known_limitations. Examples:
- HRV (RMSSD) decrease → arousal increase — healthy adults — weak; confounded by motion/respiration.
- Frontal theta/beta ratio elevated → cognitive load increase — healthy adults — weak; electrode-placement sensitive.
- Sustained elevated heart rate → arousal increase — general — weak; exercise confound (gate to non-exercise sub-context, #14).
- Reduced HF-HRV power → sympathetic dominance/stress — adults — weak; posture confound.
- Faster speech rate / higher HF speech energy → arousal increase — general — weak; language/individual variation.
- Frontal alpha asymmetry (right > left) → negative affect/withdrawal — adults — contested; low confidence, explicit limitation noted.

Seeds load at `status='reviewed'` (a human curated them) and still must pass `promote_prior` against ledger evidence before going `live` — the seed primes the registry but does NOT bypass the gate.

---

## 8. Testing plan (DB-free + LLM-free CI)

CI must run with **no `DATABASE_URL` and no LLM** (repo convention; the #1 build held the 9-layer suite at 289 passed / 2 skipped). Split tests accordingly.

**Pure / CI-safe (run in CI):**
- `rules.py`: exhaustive `evaluate_rule` table tests — every operator (increase/decrease/gt/lt/in_band/ratio_gt), context_gate satisfied/unsatisfied, claim emission, None when condition unmet, threshold boundaries.
- `models.py`: rule-schema validation — reject `rule.claim.axis != target_axis`, reject confidence ∉ [0,1], require non-empty `known_limitations` (#17 enforced at the type layer).
- `gate.py` scoring math: synthetic (prediction, observed) pairs assert `sign_agreement_rate` + the pass/fail decision via a **dependency-injected fake ledger reader** — no real DB.
- `consume.py` `applies_to_user`: synthetic SubjectProfile/applicability — pure population filtering.
- `extract.py`: parse/validate LLM output with a **stubbed ChatClient** returning canned JSON; assert the corpus-path honesty guard raises on path escape; assert no HTTP import.
- `emit.py`: LabelRecord construction with a **mock ledger** — assert `source=LITERATURE_PRIOR`, `user_id` set, full provenance payload, no DB write.

**DB / LLM smoke (NOT in CI — run locally before declaring done):**
- `smoke_test.py`: apply 0012 to a Neon scratch branch via psycopg; `load_seed`; `propose_candidates_from_corpus(dry_run=True)` against the real ChatClient; `register_candidate`; `review_prior`; `promote_prior` against real ledger labels; `materialize_prior` then assert a `label_observations` row appears with `source=literature_prior` + full provenance via `read_labels`.

Run as `python -m literature_priors.smoke_test`. CI guard: keep `db`/`llm` imports inside functions (not module top-level) so pytest collection stays DB-free/LLM-free.

---

## 9. Commitment alignment

- **#1 (Label Ledger / provenance):** Consumes the frozen ledger as-is. The only writes are weak labels at `LabelSource.LITERATURE_PRIOR` via `record_label`, with full provenance round-tripped. Registry tables reference but never alter `label_observations`.
- **#11 (semantic-first / triggered escalation):** The LLM-extraction pass is *triggered, batch, human-gated* — never continuous, never on raw streams. It reads curated semantic text excerpts. Aligns with "cloud LLM = triggered escalation only."
- **#14 (meta-context bias):** Every rule carries a `context_gate`; `evaluate_rule` refuses to fire outside the gated `(meta, sub)` context, and the materialized label stamps `meta_context`.
- **#17 (Labels are provenance-scoped priors):** The literal embodiment — target axis + rule + citation + population + confidence + known_limitations are all NOT-NULL columns; weak priors never masquerade as ground truth; the source tag travels with every consumed/materialized label; priors sit at the weakest rung of `TRUST_ORDER`.
- **Honesty value:** small curated seed + local corpus + dry-run LLM proposals + mandatory human review + a gate that refuses to promote without ledger evidence. No autonomous scraping; `extract.py` imports no HTTP client and guards corpus paths.

---

## 10. Build-phase sequence

1. **Verify the frozen contract.** Re-read `labels/provenance.py` / `record.py` / `ledger.py` + `migrations/0011_label_ledger.sql` on merged `main`. Confirm `record_label`/`read_labels` signatures (reads key by `user_id`; `sources=` plural), `LabelRecord` fields, `label_observations` columns, and that `LITERATURE_PRIOR` + `LLM_LITERATURE_BOOTSTRAP` exist. Reconcile `emit.py`/`gate.py` to the real signatures.
2. **Migration 0012.** Write `0012_literature_priors.sql` exactly as §3. Apply to a Neon scratch branch via psycopg/Neon MCP; do not alter ledger objects.
3. **Models + pure rules (TDD).** Implement `models.py` (with #17 NOT-NULL/validation invariants) and `rules.py`; write the CI-safe pure tests first.
4. **Store.** Implement `store.py` CRUD + lifecycle transitions over 0012. Local DB test.
5. **Seed.** Author `seed/sources.json`, `seed/seed_priors.json` (~6–12 priors from §7) + corpus excerpts; implement idempotent `load_seed.py`. Tests: load is idempotent; all seed rows satisfy model validation.
6. **Gate.** Implement `gate.py` (`validate_against_ledger` + `promote_prior`) with a dependency-injected ledger reader; CI tests on scoring + pass/fail; local test against real ledger labels.
7. **Consumer + emit.** Implement `consume.py` (`priors_for`, `weak_supervision_for`, `materialize_prior`, `applies_to_user`) and `emit.py` (the single ledger-write chokepoint). CI tests with mock ledger; local test that `materialize_prior` produces a `LITERATURE_PRIOR` row with full provenance.
8. **LLM-extraction.** Implement `extract.py` (dry_run default, path guard) via `ChatClient.auto()` + `chat_structured`. CI test with stubbed client; local dry-run smoke against the real corpus.
9. **CLI + smoke.** Implement `cli.py` (review/promote/list) and `smoke_test.py`; run `python -m literature_priors.smoke_test`.
10. **Wire consumption.** Expose `priors_for`/`weak_supervision_for` to cold-start (#4) and to L3 fusion + L4 training as down-weighted, source-tagged inputs; add the leave-one-source-out hook for §6 source-set fusion evaluation (#5).
11. **Docs + theory-aligner.** Update `docs/STATUS.md` (dated); write `literature_priors/README.md` (incl. the no-scraping honesty statement); invoke the theory-aligner gate to verify alignment with the 17 commitments before declaring shipped (per memory `feedback_theory_aligner_workflow.md`).
