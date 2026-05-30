# Design Spec — Cold-Start Arbitration (commitment #4)

> **Status:** DESIGN ONLY. No code or migrations written here. A later build
> workflow executes this against the main `daybook` tree. Owns migration
> **0013**. Builds strictly on top of the FROZEN label-ledger contract
> (`docs/superpowers/specs/2026-05-30-label-ledger-state-declared-design.md`):
> the `labels/` package (`LabelSource`, `LabelRecord`, `ledger.record_label`,
> `ledger.read_labels`) and the `label_observations` table. This spec **consumes
> that contract as-is** and does **not** redefine the ledger, the `LabelSource`
> taxonomy, or `label_observations`.

---

## 0. One-paragraph summary

For each affect axis, the system holds a **mixing weight** `w_personal ∈ [0,1]`
governing how much a fused/predicted estimate trusts **personal evidence**
(self-report labels, observed outcomes, Apple-Health history, repeated sensor
patterns) versus **population priors** (literature defaults + opt-in demographic
modifiers). Per commitment #17 the mixing weight is **itself model state**, is
**per-axis**, starts **population-weighted**, and **shifts to person-weighted as
personal evidence accumulates**. A `calibration_state` machine
(`cold_start → calibrating → calibrated`) is surfaced per axis. The arbitration
function `blend(axis)` reads tiered label counts/recency from the ledger
(`ledger.read_labels`) plus optional opt-in demographic priors, and returns the
weight + calibration_state. L3 fusion and L4 prediction both read it through one
seam.

---

## 1. Scope

### In scope
- A per-axis, per-user **mixing weight** (`w_personal`, with `w_population = 1 - w_personal`).
- A per-axis **`calibration_state`** enum machine: `cold_start | calibrating | calibrated`.
- Persistent storage of both (migration **0013**): `axis_calibration` (current
  materialized state), `cold_start_profiles` (per-axis tuning + literature priors),
  `demographic_priors` (opt-in, provenance-marked uncertainty modifiers),
  `axis_calibration_history` (append-only audit of weight/state transitions).
- The arbitration module `apps/inference/arbitration/` with the pure functions
  `blend(axis, ...)`, `recompute_axis(axis, ...)`, and `calibration_state_for(...)`.
- The read path for L3 fusion and L4 prediction (how they consume the weight).
- A DB-free + LLM-free test plan.

### Out of scope (explicitly deferred)
- Writing labels (that is #1/#2; this subsystem is a **reader** of `label_observations`).
- Source-set fusion math beyond the population↔personal blend seam (that is #4's
  sibling "Source-set fusion evaluation"; this spec provides the weight it needs).
- Causal action-conditioning of the weight (#15/#16) — the blend output is a
  scalar mixing weight, not a world-model.
- Any consent/opt-in UI for demographics (only the storage + bias-safe contract here).
- Horizon-discounted weighting for long-range L4 (documented hook only).

---

## 2. Conceptual model

### 2.1 What "population" vs "personal" means per source tier

The frozen ledger's `LabelSource` taxonomy maps directly onto the two poles:

| `LabelSource`         | Pole     | Person-specificity | Notes |
|-----------------------|----------|--------------------|-------|
| `SELF_REPORT`         | personal | highest            | ground-truth-grade; #2 state_declared writes these |
| `OBSERVED_OUTCOME`    | personal | high               | downstream behavior confirmed/refuted a prior label |
| `SENSOR_INFERRED`     | personal | medium             | L3 fusion output from this person's biometrics + repeated sensor patterns |
| `POPULATION_PRIOR`    | population | lowest (by definition) | literature/demographic default |

Apple-Health history and "repeated sensor patterns" are **not new source tiers**
— they enter the ledger as `SENSOR_INFERRED` (or `OBSERVED_OUTCOME` where a HK
event confirms a prior). This subsystem reads them through their existing tier so
it never redefines the taxonomy. Demographic modifiers are an **opt-in overlay on
the population pole only** (see §5); they are never their own `LabelSource` and
never write to `label_observations`.

### 2.2 The weight is model state (#17)

`w_personal` is stored, audited, and recomputable. It is **not** recomputed
ad hoc inside L3/L4 — they read the materialized `axis_calibration` row (fast
path) and trust that a single writer keeps it consistent with a pure recompute
(`recompute_axis`). Any reader can reproduce the value from the ledger summary,
so the materialized row is a cache, not a second source of truth.

### 2.3 Evidence accumulation → weight shift

Per axis we compute an **effective personal-evidence mass** `E_personal`:

```
E_personal(axis) = Σ_tier  tier_trust[tier] · Σ_label decay(now − observed_at) · confidence
```

- `tier_trust` is a fixed per-tier multiplier (self_report > observed_outcome >
  sensor_inferred), so high-volume low-trust streams (Apple-Health) cannot swamp
  self-report. Contribution **saturates** (log or bounded sum) so raw volume
  cannot beat trust.
- `decay(Δt)` is a per-tier exponential half-life (recency), so stale evidence
  fades and the weight can move back toward population if the person stops
  reporting.
- `confidence` is the ledger's producer-self-assessed `[0,1]`.

The weight is a saturating function of `E_personal` relative to a per-axis
**half-saturation constant** `E_half` (from `cold_start_profiles`):

```
w_personal(axis) = E_personal / (E_personal + E_half)     # ∈ [0,1), monotone, smooth
```

At zero personal evidence `w_personal = 0` (fully population). As evidence grows,
`w_personal → 1`. `E_half` is the amount of effective personal evidence at which
the system trusts person and population equally (`w_personal = 0.5`).

### 2.4 The calibration_state machine

`calibration_state` is a coarse, surfaced-to-the-user view of the same evidence,
with **hysteresis** so it does not flap:

```
cold_start    : E_personal < E_cs_enter          (no/near-zero personal evidence)
calibrating   : E_cs_enter ≤ E_personal < E_cal_enter
calibrated    : E_personal ≥ E_cal_enter
```

Transitions are one-directional-with-hysteresis: to drop back from `calibrated`
to `calibrating`, evidence must fall below `E_cal_exit < E_cal_enter` (decay can
do this if the person goes silent for a long time). Same for `calibrating →
cold_start` via `E_cs_exit`. Thresholds live in `cold_start_profiles` per axis
(defaults global). Every transition is written to `axis_calibration_history`.

---

## 3. Data model — migration 0013 (full DDL)

> Append-only, additive, numbered 0013. Applied via psycopg in a Python smoke
> test (never `psql`). Mirrors existing migration header style. All event-ish
> rows carry `i_model_id UUID NULL` per commitment #1 (I-Model polymorphism).
> `label_observations` is referenced **read-only** and is **not** altered.

```sql
-- 0013_cold_start_arbitration.sql
-- Cold-start arbitration (commitment #4): per-axis population<->personal mixing
-- weight + calibration_state machine. Consumes the frozen label ledger
-- (label_observations, LabelSource) read-only. Builds on baseline 0012.
-- Append-only / additive. Apply via psycopg smoke test, never psql.

-- ---------------------------------------------------------------------------
-- 3.1 cold_start_profiles
-- Per-axis tuning + literature/population point prior. One row per (user, axis).
-- Seeded at axis-registration time with literature defaults (#3). The literature
-- prior is the population-pole estimate that blend() leans on while cold.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cold_start_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    axis                TEXT NOT NULL,              -- e.g. 'arousal','valence','affect_prosody'
    i_model_id          UUID NULL,                 -- commitment #1

    -- population-pole estimate (literature #3)
    population_value    DOUBLE PRECISION NOT NULL, -- literature default point estimate on axis
    population_variance DOUBLE PRECISION NOT NULL,  -- uncertainty of the literature prior
    literature_source   TEXT NULL,                  -- citation / provenance string (auditability)

    -- evidence-accumulation tuning (defaults copied from module constants on insert)
    e_half              DOUBLE PRECISION NOT NULL DEFAULT 8.0,   -- half-saturation evidence mass
    e_cs_enter          DOUBLE PRECISION NOT NULL DEFAULT 0.5,   -- cold_start upper bound
    e_cs_exit           DOUBLE PRECISION NOT NULL DEFAULT 0.25,  -- hysteresis: calibrating->cold_start
    e_cal_enter         DOUBLE PRECISION NOT NULL DEFAULT 6.0,   -- calibrating->calibrated
    e_cal_exit          DOUBLE PRECISION NOT NULL DEFAULT 4.0,   -- hysteresis: calibrated->calibrating

    -- per-tier trust + half-life (seconds). NULL => fall back to module defaults.
    tier_trust          JSONB NULL,   -- {"self_report":1.0,"observed_outcome":0.7,"sensor_inferred":0.35}
    tier_halflife_s     JSONB NULL,   -- {"self_report":2592000,"observed_outcome":1209600,"sensor_inferred":604800}

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, axis)
);
CREATE INDEX IF NOT EXISTS idx_cold_start_profiles_user_axis
    ON cold_start_profiles (user_id, axis);

-- ---------------------------------------------------------------------------
-- 3.2 axis_calibration
-- The MATERIALIZED current state per (user, axis): the weight + calibration_state.
-- This is the fast-path row L3/L4 read. It is a cache of recompute_axis(); a
-- single writer keeps it consistent. One row per (user, axis).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS axis_calibration (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    axis                TEXT NOT NULL,
    i_model_id          UUID NULL,                 -- commitment #1

    w_personal          DOUBLE PRECISION NOT NULL DEFAULT 0.0,  -- [0,1]; 0 = fully population
    calibration_state   TEXT NOT NULL DEFAULT 'cold_start'
        CHECK (calibration_state IN ('cold_start','calibrating','calibrated')),

    -- diagnostics / reproducibility (so any reader can audit the cached value)
    e_personal          DOUBLE PRECISION NOT NULL DEFAULT 0.0,  -- effective evidence mass at compute time
    evidence_by_tier    JSONB NOT NULL DEFAULT '{}'::jsonb,     -- {tier: {count, effective_mass, last_observed_at}}
    demographics_applied BOOLEAN NOT NULL DEFAULT false,        -- did opt-in demographics modify the prior?

    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),     -- when recompute_axis last ran
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, axis)
);
CREATE INDEX IF NOT EXISTS idx_axis_calibration_user_axis
    ON axis_calibration (user_id, axis);

-- ---------------------------------------------------------------------------
-- 3.3 axis_calibration_history
-- Append-only audit of every weight/state change. Honesty value: the system can
-- always explain WHY it trusts person vs population for an axis.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS axis_calibration_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    axis                TEXT NOT NULL,
    i_model_id          UUID NULL,

    w_personal          DOUBLE PRECISION NOT NULL,
    calibration_state   TEXT NOT NULL,
    prev_state          TEXT NULL,                 -- NULL on first row
    e_personal          DOUBLE PRECISION NOT NULL,
    evidence_by_tier    JSONB NOT NULL,
    reason              TEXT NULL,                 -- 'recompute' | 'state_transition' | 'profile_edit'
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_axis_calibration_history_user_axis_time
    ON axis_calibration_history (user_id, axis, recorded_at DESC);

-- ---------------------------------------------------------------------------
-- 3.4 demographic_priors  (OPT-IN, provenance-marked, bias-aware)
-- Uncertainty MODIFIERS only. They widen/narrow or nudge the POPULATION prior;
-- they never hard-classify and never produce a label. Ships EMPTY + feature-off.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS demographic_priors (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    axis                TEXT NOT NULL,
    cohort_key          TEXT NOT NULL,   -- e.g. 'age_band','reported_gender' (free-form, auditable)
    cohort_value        TEXT NOT NULL,   -- e.g. '25-34'

    -- modifiers applied to the population prior ONLY:
    value_shift         DOUBLE PRECISION NOT NULL DEFAULT 0.0,   -- additive nudge to population_value
    variance_scale      DOUBLE PRECISION NOT NULL DEFAULT 1.0,   -- multiplies population_variance (>=1 widens)
    max_abs_shift       DOUBLE PRECISION NOT NULL DEFAULT 0.0,   -- hard cap on |value_shift| effect

    -- provenance + bias audit (mandatory, non-null source)
    source              TEXT NOT NULL,           -- citation / dataset provenance
    bias_notes          TEXT NULL,               -- known representativeness caveats
    enabled             BOOLEAN NOT NULL DEFAULT false,  -- global feature flag; default OFF
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (axis, cohort_key, cohort_value)
);

-- ---------------------------------------------------------------------------
-- 3.5 user_demographics  (OPT-IN consent gate — which cohorts a user allows)
-- Absence of a row => demographics NOT used for that user (privacy default).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_demographics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    cohort_key          TEXT NOT NULL,
    cohort_value        TEXT NOT NULL,
    consented           BOOLEAN NOT NULL DEFAULT false,  -- explicit opt-in
    consented_at        TIMESTAMPTZ NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, cohort_key)
);
```

> Note: `new_tables` in the structured output lists the four arbitration-owned
> tables; `user_demographics` (3.5) is the consent gate that pairs with
> `demographic_priors` and is included in the DDL above for completeness.

---

## 4. Module layout — `apps/inference/arbitration/`

Mirrors the existing per-subsystem package pattern (`classifier/`, `embeddings/`,
`llm/` each a package with a `smoke_test.py`).

```
apps/inference/arbitration/
├── __init__.py          # re-exports: blend, recompute_axis, CalibrationState, BlendResult
├── constants.py         # default tier_trust, tier_halflife_s, E_* thresholds, axis registry hook
├── evidence.py          # pure: summarize ledger reads -> per-tier effective evidence mass
├── blend.py             # pure: blend(axis,...) -> BlendResult (weight + state + diagnostics)
├── arbiter.py           # impure seam: recompute_axis() reads ledger + DB, writes axis_calibration + history
├── demographics.py      # pure: apply opt-in, capped, provenance-marked modifiers to the population prior
├── read.py              # fast-path read: get_calibration(user_id, axis) -> BlendResult from axis_calibration
└── smoke_test.py        # DB-free + LLM-free; runs as `python -m arbitration.smoke_test`
```

DB access uses the repo convention: `from db import get_conn` after the standard
`sys.path.insert(0, ...inference)` shim (same as sibling packages). All pure
modules (`evidence`, `blend`, `demographics`, `constants`) import **nothing** that
touches DB/network, so they are unit-testable with hand-built inputs.

---

## 5. Key functions / contracts

### 5.1 Types (`__init__.py` / `blend.py`)

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class CalibrationState(str, Enum):
    COLD_START  = "cold_start"
    CALIBRATING = "calibrating"
    CALIBRATED  = "calibrated"

@dataclass(frozen=True)
class TierEvidence:
    tier: str                 # value of LabelSource (read from ledger, not redefined)
    count: int                # raw label count in window
    effective_mass: float     # tier_trust * Σ decay * confidence  (saturating)
    last_observed_at: datetime | None

@dataclass(frozen=True)
class BlendResult:
    axis: str
    w_personal: float         # [0,1]
    w_population: float        # = 1 - w_personal
    calibration_state: CalibrationState
    e_personal: float
    evidence_by_tier: dict[str, TierEvidence]
    population_value: float    # literature prior (post opt-in demographic modifier, if any)
    population_variance: float
    demographics_applied: bool
```

### 5.2 The arbitration function `blend(axis)` — PURE

```python
def blend(
    axis: str,
    tier_evidence: dict[str, TierEvidence],   # from evidence.summarize(ledger.read_labels(...))
    profile: ProfileParams,                   # from cold_start_profiles row (or defaults)
    population_value: float,                   # literature prior, AFTER demographics.apply()
    population_variance: float,
    *,
    now: datetime,
) -> BlendResult:
    """Pure. No DB, no clock-of-its-own, no network. now is injected for testability."""
```

- Computes `e_personal = Σ_tier effective_mass` (already tier-trust-weighted and
  decayed by `evidence.summarize`).
- `w_personal = e_personal / (e_personal + profile.e_half)`.
- `calibration_state` via `calibration_state_for(e_personal, prev_state, profile)`
  with the hysteresis thresholds in §2.4.
- Returns `BlendResult`. **No I/O.** This is the testable heart.

### 5.3 `evidence.summarize(...)` — PURE adapter over the ledger read

```python
def summarize(
    label_rows: Sequence[LabelRecord],   # EXACTLY the ledger's LabelRecord, unchanged
    profile: ProfileParams,
    *, now: datetime,
) -> dict[str, TierEvidence]:
    """Group the frozen-contract LabelRecords by source tier; apply per-tier
    half-life decay + confidence + saturating tier-trust. Population_prior rows
    are NOT counted as personal evidence (they are the population pole)."""
```

The caller (`arbiter.recompute_axis`) obtains `label_rows` via the frozen
contract: `ledger.read_labels(user_id=..., axis=axis, sources=[...personal tiers...])`.
This subsystem never reads `label_observations` SQL directly — it goes through
`ledger.read_labels` so the ledger stays the single owner of its table.

### 5.4 `demographics.apply(...)` — PURE, bias-safe

```python
def apply(
    population_value: float,
    population_variance: float,
    cohorts: Sequence[ConsentedCohort],   # only consented rows from user_demographics
    modifiers: Sequence[DemographicModifier],  # enabled demographic_priors rows
) -> tuple[float, float, bool]:
    """Return (modified_value, modified_variance, applied_flag).
    Rules (locked):
      - Only consented + enabled modifiers apply; otherwise return inputs unchanged.
      - value_shift is clamped to ±max_abs_shift (never dominates).
      - variance_scale >= 1 is allowed to WIDEN uncertainty; narrowing below the
        literature variance is rejected (demographics may add doubt, not certainty).
      - Effect is on the POPULATION pole only; it never touches w_personal or any
        personal-tier evidence. It cannot hard-classify."""
```

This encodes the honesty/bias-aware contract: demographics are **opt-in
uncertainty modifiers only, auditable, never hard-classifying**.

### 5.5 `arbiter.recompute_axis(...)` — IMPURE writer (single source of truth)

```python
def recompute_axis(user_id: str, axis: str, *, conn=None) -> BlendResult:
    """1. Load cold_start_profiles row (or seed defaults).
       2. label_rows = ledger.read_labels(user_id, axis, personal tiers).
       3. tier_evidence = evidence.summarize(label_rows, profile, now=utcnow()).
       4. (pop_v, pop_var, applied) = demographics.apply(...) using consented cohorts.
       5. result = blend(axis, tier_evidence, profile, pop_v, pop_var, now=utcnow()).
       6. UPSERT axis_calibration; if state changed OR scheduled, INSERT history row.
       7. return result."""
```

Triggered: (a) after each `ledger.record_label` for that axis (cheap incremental
recompute), and/or (b) a periodic consolidation job. L3/L4 do **not** call this on
the hot path.

### 5.6 `read.get_calibration(...)` — fast read for L3/L4

```python
def get_calibration(user_id: str, axis: str, *, conn=None) -> BlendResult:
    """Read the materialized axis_calibration row. If missing, lazily seed
    cold_start (w_personal=0, state=cold_start) from cold_start_profiles. Hot-path
    safe (single indexed row read)."""
```

---

## 6. How L3 fusion and L4 prediction read it

Both layers consume **one seam**: `arbitration.read.get_calibration(user_id, axis)`.

### L3 fusion (`Fuse`)
When producing the per-axis fused estimate, L3 already blends modality channels.
It additionally blends the **personal fused estimate** against the **population
prior** using the arbitration weight:

```
estimate(axis)  = w_personal · personal_fused(axis)
                + w_population · population_value(axis)
variance(axis)  = combine(w_personal · personal_var, w_population · population_variance)
```

- While `cold_start`, `w_personal ≈ 0` ⇒ L3 reports essentially the literature
  prior (honest "I don't know you yet on this axis").
- As evidence accrues, the fused estimate becomes person-specific.
- L3 attaches `calibration_state` to the fused-state metadata so downstream
  (L5/L6, Regis) can speak honestly ("still calibrating your arousal baseline").

This is the seam the sibling **"Source-set fusion evaluation"** note plugs into:
arbitration supplies the population↔personal mixing weight; source-set fusion
decides how the personal-tier sources combine *within* `personal_fused(axis)`.

### L4 prediction (`Predict`)
L4's per-axis predictors (JEPA-family scaffolds today, #16) read the same weight
to set the **prior pull** of their forecasts: a cold axis regresses predictions
toward the population prior; a calibrated axis trusts the person-specific latent
trajectory. v1: `predict(axis, horizon, action)` shrinks its output toward
`population_value` by `w_population`. **Documented hook:** v2 may horizon-discount
(longer horizons trust population more) — out of scope here, flagged in open
questions.

Neither layer recomputes the weight; both treat `axis_calibration` as read-only
state owned by this subsystem.

---

## 7. How this reads the #1 ledger (contract boundary)

- **Reads only** via `ledger.read_labels(user_id, axis, sources=...)` returning
  `Sequence[LabelRecord]` (the frozen dataclass). No direct SQL against
  `label_observations`.
- **Never writes** labels. Arbitration emits no `LabelRecord`; demographics emit
  no labels.
- **Never redefines** `LabelSource`. Personal tiers are referenced by importing
  the enum: `from labels import LabelSource`. The personal-evidence set is
  `{SELF_REPORT, OBSERVED_OUTCOME, SENSOR_INFERRED}`; `POPULATION_PRIOR` rows (if
  present in the ledger) are excluded from `e_personal` because they are the
  population pole, not personal evidence.
- Recompute is triggered by the ledger write path but lives in this package, so
  the ledger has no dependency on arbitration (one-way arrow: arbitration → ledger).

---

## 8. Testing plan (DB-free + LLM-free CI)

All CI tests are pure-Python, no Postgres, no network. The package is structured
so the math lives in pure modules.

### 8.1 Pure unit tests (no DB, no LLM)
- **`blend()` monotonicity:** more `e_personal` ⇒ non-decreasing `w_personal`;
  `e_personal=0 ⇒ w_personal=0`; `w_personal→1` as evidence→∞.
- **Saturation / anti-swamp:** N synthetic `SENSOR_INFERRED` labels (high volume,
  low trust) must NOT push `w_personal` above a single high-confidence
  `SELF_REPORT` past a documented bound — proves Apple-Health volume cannot beat
  self-report.
- **Recency decay:** old labels (large `now − observed_at`) contribute less;
  going silent moves `w_personal` back down (with `now` injected).
- **State machine + hysteresis:** sweep `e_personal` up then down; assert
  `cold_start→calibrating→calibrated` on the way up and that it does NOT flap on
  the way down until below the `*_exit` thresholds.
- **`demographics.apply()` bias-safety:** `value_shift` is clamped to
  `±max_abs_shift`; `variance_scale<1` rejected (cannot narrow below literature);
  no consented cohort ⇒ inputs returned unchanged + `applied=False`; disabled
  modifier ignored.
- **Determinism:** same inputs + same injected `now` ⇒ identical `BlendResult`
  (reproducibility / audit guarantee).
- **`evidence.summarize()` tier grouping:** `POPULATION_PRIOR` rows excluded from
  `e_personal`; unknown source values handled gracefully.

### 8.2 Ledger-contract conformance (DB-free)
- Feed hand-built `LabelRecord` instances (the frozen dataclass) straight into
  `evidence.summarize` — proves consumption of the contract WITHOUT a DB. Use a
  tiny in-memory fake of `ledger.read_labels` returning fixtures.

### 8.3 `smoke_test.py` (`python -m arbitration.smoke_test`)
- Runs the full pure path end-to-end on fixtures (fake ledger reader) and prints
  a human-readable trace of weight + state for a cold axis vs a calibrated axis.
- Guarded so it does NOT require Neon: if `get_conn` import succeeds but no DB is
  reachable, the smoke test runs the pure path only and skips the UPSERT step
  (mirrors how sibling smoke tests degrade), so CI stays DB-free.

### 8.4 Migration application test (local-only, not CI)
- A separate `apply_0013.py`-style smoke test applies 0013 via psycopg (never
  `psql`), idempotent (`IF NOT EXISTS`), checks existing tables empty before any
  index-affecting change. Run locally against the Neon dev branch, excluded from
  the DB-free CI lane.

---

## 9. Commitment alignment

- **#1 (I-Model polymorphism):** every new table carries `i_model_id UUID NULL`.
- **#1 / ledger contract (FROZEN):** consumes `labels/` + `ledger.read_labels` +
  `label_observations` **as-is**; redefines nothing; one-way dependency.
- **#11 (semantic-first continuous sensing):** Apple-Health and repeated sensor
  patterns enter as `SENSOR_INFERRED` semantic labels via the ledger — arbitration
  reads summaries, never raw streams. Consistent with discard-raw architecture.
- **#14 (meta-context biases every layer):** `blend()` is axis-keyed and
  context-agnostic at v1, but `cold_start_profiles` is per-axis and can be
  extended to per-`(meta,sub)` rows later; L3/L4 already condition on context, so
  the weight composes under the active meta-context without rewiring. (Documented
  extension point, not built in v1.)
- **#17 (Labels are provenance-scoped priors):** the mixing weight **is model
  state**, **per-axis**, **starts population-weighted**, and **shifts to
  person-weighted as personal evidence accumulates** — implemented literally by
  `axis_calibration.w_personal` driven by tiered ledger evidence. `calibration_state`
  is surfaced per axis exactly as the architecture requires.
- **Honesty value:** demographics are opt-in, capped, provenance-marked,
  uncertainty-widening-only, never hard-classifying; cold axes report the
  population prior + a `cold_start` flag so Regis can say "I don't know you on
  this yet" rather than faking person-specific certainty;
  `axis_calibration_history` makes every weight/state change auditable.
- **Theory-aligner gate:** before shipping, invoke theory-aligner to confirm
  alignment with #1/#11/#14/#17 + honesty value (per the team's documented
  milestone workflow).

---

## 10. Build-phase sequence

1. **Phase 0 — package skeleton + constants.** Create `apps/inference/arbitration/`
   with `__init__.py`, `constants.py` (default `tier_trust`, `tier_halflife_s`,
   `E_*` thresholds), and the `CalibrationState` / `BlendResult` / `TierEvidence`
   types. No DB. (Theory-aligner: types match #17 wording.)
2. **Phase 1 — pure math + tests.** Implement `evidence.summarize`, `blend`,
   `calibration_state_for`. Write the §8.1 pure unit tests first (TDD). Green,
   DB-free, LLM-free.
3. **Phase 2 — demographics (bias-safe), default OFF.** Implement
   `demographics.apply` + §8.1 bias-safety tests. Ship the modifier path but with
   `demographic_priors.enabled` default false and `user_demographics` empty.
4. **Phase 3 — migration 0013.** Author `0013_cold_start_arbitration.sql` (§3),
   plus the local-only `apply_0013` smoke test (psycopg, idempotent). Seed
   `cold_start_profiles` literature priors for the current live L3 axes
   (arousal, valence, affect_prosody, arousal_inferred, … the 7 live axes).
5. **Phase 4 — arbiter + read seam.** Implement `arbiter.recompute_axis` (consumes
   `ledger.read_labels`, UPSERTs `axis_calibration`, appends history) and
   `read.get_calibration`. Wire the recompute trigger into the ledger write path
   (one-way).
6. **Phase 5 — L3/L4 consumption.** Wire L3 fusion and L4 prediction to read
   `get_calibration` and apply the population↔personal blend (§6). Update fused-
   state metadata to carry `calibration_state`.
7. **Phase 6 — smoke + theory-aligner + STATUS.** Run `python -m
   arbitration.smoke_test`; run theory-aligner against #1/#11/#14/#17 + honesty;
   update `docs/STATUS.md` (dated) and the commitments lineage. Merge
   `feat/...` back to the main daybook tree.

Each phase is independently reviewable; Phases 0–2 are fully DB-free/LLM-free and
constitute the CI-gated core. Phases 3+ touch the DB but keep CI green by keeping
all DB work out of the CI lane (local smoke tests only).
