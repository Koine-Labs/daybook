# Offline Fusion-Ablation Harness — Design Spec (commitment #17, step #5)

**Date:** 2026-05-30
**Branch (per the #1/#2 spec §10 plan):** `feat/fusion-ablation` off merged `main`
**Pre-allocated migration:** `0014` (do not collide with `0012` literature-priors / `0013` cold-start)
**Status:** DESIGN ONLY — no code or migrations written here. This is the executable plan for a later build workflow.

This subsystem builds on top of step **#1** (the evidence ledger substrate — `labels/` package + `label_observations`, being built now on `feat/label-ledger`) and step **#2** (`state_declared`). It consumes the **frozen** ledger contract as-is and **does not** redefine the ledger, the `LabelSource` taxonomy, or `label_observations`.

---

## 1. Why this, why now

ARCHITECTURE.md §3 (Layer 3 — Fusion), under **"Source-set fusion evaluation,"** states the rule directly:

> EEG+EOG is not architecturally special — it is one source set among many. The same evaluation pattern applies to `EEG`, `EOG`, `ECG_watch`, `mic`, `EEG+EOG`, `EOG+mic`, `EEG+ECG_watch`, `EEG+EOG+mic`, and any future modality combination. **Live L3 fusers should not brute-force every permutation on every tick.** Instead, an offline fusion-ablation harness enumerates candidate source sets against provenance-scoped labels and proxy outcomes, measures whether the combination improves calibration or prediction beyond its individual components, and **only promotes the useful combinations into live fusers.** The desktop PC/GPU is the right place for this search; the Pi/Mac hot path reads the promoted rules.

The §9 open-questions log records the two questions this spec answers:

> **Label store shape.** Do labels live in a new `label_observations` table … *(answered by step #1)*.
> **Fusion-ablation harness.** What source-set search space is practical for the desktop PC, and what metrics decide whether `EEG+EOG+mic` beats `EEG+EOG` or `EOG` alone for a target axis?

The §11 Learning gap is explicit: *"Fusion-ablation harness: not built. We do not yet enumerate source sets (`EEG`, `EOG`, `EEG+EOG`, `EOG+mic`, etc.) offline and promote only the combinations that improve calibration."* This build closes that gap.

The #1/#2 design spec's load-bearing decision **D1** is the seam this harness sits on:

> The offline harness (#5) later **joins** `self_report` ledger labels against `user_state_estimate_v2` beliefs on `(user, axis, time)` to grade the inferred axes — separate tables make that join natural.

---

## 2. Scope

**In scope (v1):**
- An **offline** harness that runs as a batch job (CLI / nightly-schedulable), explicitly **NOT** on the L3 hot path. It is allowed to be slow, read the whole history, and use heavy compute.
- An **evaluation loop** that, per target axis: enumerates candidate **source sets**, reconstructs each set's belief, grades it against **provenance-scoped labels** (`self_report` / `ground_truth` / `observed_outcome` from the ledger) plus **proxy outcomes**, and measures whether the combination's calibration/prediction **beats its best individual component** by a margin.
- A **promotion store** (`promoted_source_sets`, migration `0014`) that live L3 fusers read to know which source sets are blessed for which axis.
- An **honest report**: every run records what source sets were tested, how many label/belief pairs each was graded on, the metric per set, what was promoted, what was demoted, and **what was dropped and why** (insufficient data, capped by `max_set_size`, no matched pairs). No silent caps.
- A **runnable scaffold on the Mac** (CPU/MPS), with the **desktop GPU / 4080 swap documented** as a config-only backend swap (per ARCHITECTURE §7 "Embedding compute trajectory" — desktop GPU routing is *not set up yet*).

**Out of scope (deferred, with seams left):**
- The full JEPA/world-model encoder (#16) as the "combiner" — v1 combiners are the same deterministic per-axis combiners L3 already ships; the harness re-runs them over restricted source sets. The `AblationBackend` protocol leaves the encoder slot open.
- Cross-user / population-default promoted sets (N=1 today; `promoted_source_sets.user_id = NULL` slot reserved).
- Literature/demographic priors as graders (those are #3/#4's tables; the harness reads them only if present, never requires them).
- Live L3 *consuming* the promotion (a one-line read helper is specified; wiring each live combiner to honor it is L3-side follow-on work tracked in the gap index).

---

## 3. Load-bearing decisions

**A1 — The harness GRADES, it does not infer live.** It never writes to `user_state_estimate`. Its only writes are to `ablation_runs`, `ablation_results`, and `promoted_source_sets`. This keeps it cleanly offline (commitment #11 spirit: the hot path stays cheap).

**A2 — Truth comes from the ledger, scoped by provenance (commitment #17).** Graders rank by `TRUST_ORDER`: `ground_truth` > `clinician` > `self_report` > `observed_outcome` for grading; `literature_prior`/`demographic_prior`/`llm_literature_bootstrap`/`heuristic` are **never** used as grading truth (they are priors, not truth — that is the entire point of #17). The harness reads labels exclusively through the frozen `labels.ledger.read_labels(...)`.

**A3 — "Better" means beats-its-best-component, not beats-nothing.** A source set `{EEG, EOG, mic}` is only promoted if its graded metric beats the best metric among ALL its strict subsets that were also evaluated (`{EEG,EOG}`, `{EOG,mic}`, `{EEG}`, `{EOG}`, `{mic}`, …) by a configured margin `delta`. This is the literal §6 requirement ("improves calibration or prediction **beyond its individual components**") and is what stops the harness from rewarding "more sensors = always better."

**A4 — No silent caps (honesty value).** When the candidate space is capped (`max_set_size`, time budget, or a set dropped for too few matched pairs), the dropped sets and the reason are recorded in `ablation_runs.manifest` and surfaced in the report. A cap that isn't reported is a lie about what was tested.

**A5 — Promotion is hysteretic.** A set must win on `N` consecutive runs (default 2) to flip to `promoted`; demotion requires sustained regression. Live fusers read only `status='promoted'`. This protects the hot path from churn (A1's offline/online split would be pointless if promotions thrashed).

**A6 — Compute is a swappable backend.** v1 ships `MacScaffoldBackend` (deterministic combiners + numpy metrics, CPU/MPS, runnable today). A `DesktopGPUBackend` slot is documented for when 4080 routing exists; swapping it is config (`ABLATION_BACKEND=desktop`), not a rewrite (commitment #9).

**A7 — The ledger contract is frozen; we read, we never fork it.** No new columns on `label_observations`. No new `LabelSource` values. If the harness needs a derived field it computes it in Python from `read_labels(...)` output.

---

## 4. Data model — migration `0014_promoted_source_sets.sql`

Append-only, additive. Applied to the shared Neon DB via the Neon MCP (`run_sql_transaction`), then verified by a DB-gated smoke (insert → readback → delete), exactly as 0011 was. Mirrors the conventions in 0009/0011: `gen_random_uuid()` default, `i_model_id UUID NULL` (commitment #1), `meta_context TEXT NULL` (commitment #14), tz-aware `TIMESTAMPTZ`, JSONB for polymorphic payloads, and `(user_id, …)` composite indexes.

```sql
-- 0014_promoted_source_sets.sql
-- Offline fusion-ablation harness (commitment #17 step #5, ARCHITECTURE §3 L3
-- "Source-set fusion evaluation"). Three tables:
--   promoted_source_sets — the blessed combos live L3 fusers read (the output)
--   ablation_runs        — one row per harness invocation (the manifest / audit)
--   ablation_results     — one row per (run, axis, source_set) graded (the evidence)
-- Reads truth from label_observations (0011) via labels.ledger; never alters it.

BEGIN;

-- =============================================================================
-- 1. promoted_source_sets — what live L3 fusers read (the only hot-path read)
-- =============================================================================
CREATE TABLE IF NOT EXISTS promoted_source_sets (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NULL,                 -- NULL = population default (reserved; N=1 uses the real user_id)
    axis           TEXT NOT NULL,             -- target axis, e.g. 'arousal_inferred', 'sleep_stage'
    meta_context   TEXT NULL,                 -- commitment #14; NULL = applies to all meta-contexts
    source_set     TEXT[] NOT NULL,           -- canonical sorted set, e.g. ARRAY['eeg','eog','mic']
    weights        JSONB NOT NULL DEFAULT '{}'::jsonb,  -- optional per-source weight hint {"eeg":0.5,"eog":0.3,"mic":0.2}
    status         TEXT NOT NULL DEFAULT 'candidate'    -- 'candidate' | 'promoted' | 'demoted'
                     CHECK (status IN ('candidate','promoted','demoted')),
    metric_name    TEXT NOT NULL,             -- which metric promoted it: 'brier','nll','crps','auroc',...
    metric_value   DOUBLE PRECISION,          -- the winning set's score
    component_best DOUBLE PRECISION,          -- best score among strict subsets (for the margin)
    margin         DOUBLE PRECISION,          -- metric_value vs component_best (signed, lower-is-better normalized)
    n_eval_pairs   INTEGER NOT NULL DEFAULT 0,-- matched label/belief pairs the verdict rests on (honesty)
    win_streak     INTEGER NOT NULL DEFAULT 0,-- consecutive winning runs (hysteresis, decision A5)
    promoted_run_id UUID NULL,                -- ablation_runs.id that last promoted/updated this
    i_model_id     UUID NULL,                 -- commitment #1
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, axis, meta_context, source_set)
);

CREATE INDEX IF NOT EXISTS idx_pss_live_read
    ON promoted_source_sets (user_id, axis, meta_context)
    WHERE status = 'promoted';

-- =============================================================================
-- 2. ablation_runs — one row per harness invocation (manifest + honest report)
-- =============================================================================
CREATE TABLE IF NOT EXISTS ablation_runs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NULL,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ NULL,
    backend        TEXT NOT NULL DEFAULT 'mac_scaffold',  -- 'mac_scaffold' | 'desktop_gpu'
    axes_evaluated TEXT[] NOT NULL DEFAULT '{}',
    config         JSONB NOT NULL DEFAULT '{}'::jsonb,    -- {max_set_size, delta, min_labels, tol_window_s, split}
    manifest       JSONB NOT NULL DEFAULT '{}'::jsonb,    -- what was tested / dropped / capped + WHY (decision A4)
    git_sha        TEXT NULL,                             -- code version that produced the verdicts
    status         TEXT NOT NULL DEFAULT 'running'
                     CHECK (status IN ('running','complete','failed')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ablation_runs_user_time
    ON ablation_runs (user_id, started_at DESC);

-- =============================================================================
-- 3. ablation_results — one row per (run, axis, source_set) graded (the evidence)
-- =============================================================================
CREATE TABLE IF NOT EXISTS ablation_results (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         UUID NOT NULL REFERENCES ablation_runs(id) ON DELETE CASCADE,
    user_id        UUID NULL,
    axis           TEXT NOT NULL,
    meta_context   TEXT NULL,
    source_set     TEXT[] NOT NULL,
    metrics        JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {"brier":0.12,"nll":0.9,"calibration_error":0.04}
    n_train_pairs  INTEGER NOT NULL DEFAULT 0,
    n_eval_pairs   INTEGER NOT NULL DEFAULT 0,           -- honesty: verdict-supporting sample size
    grader         TEXT NOT NULL,                        -- 'self_report' | 'ground_truth' | 'observed_outcome_proxy'
    label_sources  TEXT[] NOT NULL DEFAULT '{}',         -- which LabelSource tiers supplied truth
    beat_components BOOLEAN NULL,                          -- did it beat its best strict-subset by delta?
    dropped_reason TEXT NULL,                             -- NULL = graded; else 'insufficient_data'|'no_matched_pairs'|'capped_by_max_set_size'
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ablation_results_run_axis
    ON ablation_results (run_id, axis);
CREATE INDEX IF NOT EXISTS idx_ablation_results_user_axis_set
    ON ablation_results (user_id, axis, source_set);

COMMIT;
```

**Notes on the schema choices:**
- `source_set TEXT[]` stored **canonically sorted** so `{eog,eeg}` and `{eeg,eog}` are one set (the `UNIQUE` constraint then works). The Python layer always sorts before write.
- `dropped_reason` on `ablation_results` is how A4 ("no silent caps") is enforced at the row level: even a set that was *not graded* gets a row with the reason. The report selects these directly.
- `n_eval_pairs` lives on both the result and the promotion so a promotion can never be read without its supporting sample size.
- `weights JSONB` is the optional per-source weight hint; live L3 may use it or ignore it (open question O4) — the harness writes it either way.

**TS mirror:** add `PromotedSourceSet`, `AblationRun`, `AblationResult` entity shapes to `packages/shared/src/types.ts` (DB is the source of truth; keep TS in sync per convention).

---

## 5. Module layout — `apps/inference/ablation/`

New package, mirroring the `labels/` and `fusion/` layout (one concern per file, `from __future__ import annotations`, crash-safe DB I/O via `from db import get_conn`, tz-aware UTC, `DEFAULT_USER_ID` constant).

```
apps/inference/ablation/
├── __init__.py            # exports: run_ablation, AblationConfig, SourceSet, list_promoted
├── config.py              # AblationConfig dataclass + defaults + env overrides
├── source_sets.py         # candidate enumeration (power-set, max_set_size cap, greedy mode)
├── dataset.py             # the train/eval split: join ledger labels ↔ user_state_estimate beliefs
├── backend.py             # AblationBackend protocol + MacScaffoldBackend (v1); DesktopGPUBackend slot
├── combiners.py           # restrict a live L3 combiner to a source set; produce a graded belief series
├── metrics.py             # brier / nll / crps / auroc / calibration_error (pure numpy, LLM-free)
├── grader.py              # rank truth by TRUST_ORDER; self_report + ground_truth + proxy graders
├── evaluate.py            # the evaluation loop: per axis × source_set → ablation_results rows
├── promote.py             # beats-components + hysteresis → promoted_source_sets writes
├── store.py               # crash-safe writers/readers for the 3 new tables (mirrors fusion/writer.py)
├── report.py              # honest run report (stdout markdown + manifest dict): tested/dropped/capped
├── runner.py              # orchestrates: dataset → evaluate → promote → report → ablation_runs row
├── cli.py                 # python -m ablation.run  (--axis, --user, --backend, --max-set-size, --dry-run)
├── smoke_test.py          # end-to-end on synthetic labels+beliefs, DB mocked (mirrors fusion/smoke_test.py)
└── test_*.py              # unit tests per module (DB-free + LLM-free)
```

**Live-fuser read seam (not new code in this package):** `ablation/store.py::list_promoted(user_id, axis, meta_context) -> list[SourceSet]` is the single function L3 combiners call. It is crash-safe (returns `[]` when DB absent) so the hot path never breaks — matching the L3 "hot paths never crash on optional reads" rule (ARCHITECTURE §8 Error handling). Wiring each live combiner to actually honor the allowlist is L3 follow-on, tracked in the gap index; v1 ships the read function + one example call site in `fusion/axes/arousal_inferred.py` guarded behind a feature flag (`ABLATION_PROMOTIONS=1`, default off) so default behavior is unchanged.

---

## 6. Key functions / contracts

### 6.1 `config.py`
```python
@dataclass(frozen=True)
class AblationConfig:
    max_set_size: int = 3          # cap on |source_set|; REPORTED, never silent (A4)
    delta: float = 0.0             # margin a set must beat its best component by (A3)
    min_labels: int = 8            # min graded pairs or status='insufficient_data' (risk: N=1)
    tol_window_s: int = 300        # ±window for the label↔belief as-of join
    promote_streak: int = 2        # consecutive wins before promotion (A5 hysteresis)
    split: str = "time_holdout"    # 'time_holdout' (older→train, newer→eval); no overlap (leakage)
    backend: str = "mac_scaffold"  # 'mac_scaffold' | 'desktop_gpu'
    greedy: bool = False           # forward-selection instead of full power-set when K large
```
Env overrides (`ABLATION_BACKEND`, `ABLATION_MAX_SET_SIZE`, …) so the desktop swap and CI tuning are config-only.

### 6.2 `source_sets.py`
```python
SourceSet = tuple[str, ...]   # canonical sorted tuple of source tokens

def enumerate_candidates(
    available_sources: list[str], cfg: AblationConfig
) -> tuple[list[SourceSet], list[tuple[SourceSet, str]]]:
    """Return (candidates, dropped). `dropped` carries (set, reason) for sets the
    cap excluded — feeds the honest manifest (A4). Greedy mode returns a forward-
    selection path instead of the full power-set when len(available) is large."""
```
`available_sources` for an axis is derived from which modalities have ever written a `FeatureSnapshot`/belief contributing to that axis (read from `user_state_estimate.source` history + the axis's declared inputs). Tokens are normalized (`eeg`, `eog`, `ecg_watch`, `mic`, `vision`, `text`).

### 6.3 `dataset.py` — the train/eval split (the D1 join)
```python
@dataclass
class GradedPair:
    observed_at: datetime
    truth_value: Any           # from a ledger LabelRecord (self_report/ground_truth/outcome)
    truth_source: LabelSource
    truth_confidence: float
    belief_inputs: dict[str, Any]  # per-source feature/belief contributions at ~observed_at

def build_dataset(
    user_id: str, axis: str, cfg: AblationConfig
) -> tuple[list[GradedPair], list[GradedPair]]:
    """Join ledger labels ↔ user_state_estimate beliefs on (user, axis, time±tol).
    Truth: labels.ledger.read_labels(user_id, axis=axis,
            sources=[GROUND_TRUTH, CLINICIAN, SELF_REPORT, OBSERVED_OUTCOME]).
    Beliefs: latest user_state_estimate row per source at-or-before each label's
            observed_at within tol_window_s.
    Split by time_holdout: older fraction → train, newer → eval, no overlap."""
```
This is the literal realization of D1 from the #1/#2 spec. It reads truth ONLY through the frozen `read_labels` and beliefs from `user_state_estimate` (the renamed v2 table). `heuristic`/`literature_prior`/etc. are excluded from truth by construction (A2).

### 6.4 `backend.py`
```python
class AblationBackend(Protocol):
    def reconstruct_belief(self, axis: str, source_set: SourceSet,
                           pair: GradedPair, trained_params: Any) -> Any: ...
    def fit(self, axis: str, source_set: SourceSet,
            train: list[GradedPair]) -> Any: ...   # returns trained_params (weights)

class MacScaffoldBackend:   # v1, runs today on Mac CPU/MPS
    """Wraps the existing deterministic L3 combiner, restricted to source_set:
    fit = least-squares / grid weights over the set; reconstruct = the combiner's
    rule on the restricted inputs. Pure numpy. No GPU, no LLM."""

# DesktopGPUBackend — DOCUMENTED SLOT (not built v1).
#   When 4080 routing exists (ARCHITECTURE §7 embedding trajectory), this backend
#   trains a small JEPA-family encoder (#16) over the source_set and reconstructs
#   belief from latent. Selected via ABLATION_BACKEND=desktop. Same Protocol →
#   evaluate.py / promote.py unchanged (commitment #9: v1 composes forward).
```

### 6.5 `metrics.py`
Pure-numpy, deterministic, LLM-free. Per axis-type:
- **categorical** (`sleep_stage`, `meta_context`): multiclass Brier score + log-loss + expected calibration error (ECE).
- **continuous** (`arousal_inferred`, `affect_prosody`): negative log-likelihood under predicted Gaussian + CRPS + reliability.
- **binary-event** (e.g. `user_speaking_within_10min`): AUROC + Brier.

Each returns a dict written into `ablation_results.metrics`. A `LOWER_IS_BETTER: set[str]` constant normalizes margin sign for A3.

### 6.6 `grader.py`
```python
def select_truth_grader(pairs: list[GradedPair]) -> str:
    """Pick the grader by TRUST_ORDER over the truth_sources present:
    ground_truth/clinician → 'ground_truth'; self_report → 'self_report';
    else observed_outcome → 'observed_outcome_proxy'. Returns the grader name
    recorded in ablation_results.grader."""
```
The **proxy grader** maps `observed_outcome` ledger rows (and, optionally, `prediction_log` reconciliation) to an axis-error signal. v1 ships the `self_report`/`ground_truth` graders fully and the proxy grader as a documented stub with a stable contract (open question O2).

### 6.7 `evaluate.py`
```python
def evaluate_axis(user_id, axis, cfg, backend, run_id) -> list[AblationResult]:
    """For each candidate source_set: build train/eval, fit on train, reconstruct
    on eval, score with metrics, write one ablation_results row. Sets with
    n_eval_pairs < min_labels → row with dropped_reason='insufficient_data'.
    Sets capped by max_set_size → row with dropped_reason='capped_by_max_set_size'.
    Sets with zero matched pairs → 'no_matched_pairs'. Nothing is silently skipped."""
```

### 6.8 `promote.py`
```python
def decide_promotions(results: list[AblationResult], cfg, user_id) -> list[PromotionDecision]:
    """For each fully-graded set: compute component_best over its strict subsets
    that were graded; beat_components = (score beats component_best by delta).
    Apply hysteresis (win_streak) against existing promoted_source_sets rows.
    Returns decisions: promote / hold-candidate / demote. Writes via store.py."""
```

### 6.9 `runner.py` + `report.py`
`run_ablation(user_id, axes, cfg)` opens an `ablation_runs` row (`status='running'`, `git_sha`), runs `evaluate_axis` per axis, runs `decide_promotions`, writes the manifest (tested / dropped / capped, with reasons), closes the run (`status='complete'`), and prints the markdown report. The report is the honesty surface: a table of every source set, its metric, its sample size, its verdict, and a "Dropped" section listing every untested set with its reason.

### 6.10 CLI
`python -m ablation.run --axis arousal_inferred --user <id> --max-set-size 3 --backend mac_scaffold --dry-run` (mirrors `recall.capture` / `chat.cli` ergonomics; `--dry-run` evaluates + reports without writing promotions).

---

## 7. How it reads the #1 ledger (frozen contract — read-only)

The harness touches the ledger through **exactly** the frozen API, nothing else:
- `from labels import read_labels, LabelSource, TRUST_ORDER, LabelRecord` (the package `__init__` exports).
- Truth fetch: `read_labels(user_id, axis=axis, sources=[LabelSource.GROUND_TRUTH, LabelSource.CLINICIAN, LabelSource.SELF_REPORT, LabelSource.OBSERVED_OUTCOME], since=window_start)`.
- It uses `TRUST_ORDER` to rank which grader applies when multiple truth tiers coexist.
- It **never** writes to `label_observations`, never adds a `LabelSource` value, never alters the table. (A7.)
- `classify_source` is available if the harness needs to interpret a belief's freetext `source` from `user_state_estimate`, but it does not normalize ledger rows (those already carry typed `LabelSource`).

This is the same consumption pattern the #1/#2 spec §10 mandates: "the frozen `labels/ledger.py` read/write API (none may fork it)."

---

## 8. Testing plan (TDD, DB-free + LLM-free CI)

Tests written first, per component, mirroring `labels/test_*.py` and `fusion/test_*.py`. The CI-mirror suite must stay green with **no `DATABASE_URL`** and **no LLM auth** (the repo's "green from clean caches" convention; the `labels`/`state` dirs join the existing `core sensors features fusion prediction decision output bci vision` list).

- **`config.py`**: defaults + env overrides; frozen dataclass immutability.
- **`source_sets.py`**: power-set correctness; canonical sorting; `max_set_size` cap returns the dropped sets with reason (A4); greedy mode path.
- **`dataset.py`**: the join — `read_labels` and `get_conn` monkeypatched to synthetic data; assert label↔belief matching within `tol_window_s`; assert time-holdout split has **no overlap** (leakage guard); assert `heuristic`/`literature_prior` truth is excluded.
- **`backend.py`**: `MacScaffoldBackend.fit`/`reconstruct_belief` deterministic on a synthetic set; `DesktopGPUBackend` slot raises `NotImplementedError` until wired (documented, like the LLM gateway stub).
- **`metrics.py`**: known-input → known-output for brier/nll/crps/auroc/ECE (pure numpy, no DB/LLM); `LOWER_IS_BETTER` sign normalization.
- **`grader.py`**: `select_truth_grader` honors `TRUST_ORDER`; proxy-grader stub contract.
- **`evaluate.py`**: every candidate yields a row; insufficient/no-pair/capped sets get the right `dropped_reason`; nothing silently skipped.
- **`promote.py`**: beats-best-component math; `delta` margin; hysteresis (`win_streak` increments, promotes on streak, demotes on sustained regression).
- **`store.py`**: crash-safe writers/readers with `get_conn` monkeypatched (DB-free) + a `DATABASE_URL`-gated real round trip (insert→readback→delete) for migration `0014`, exactly like `labels/test_ledger.py::test_real_db_round_trip`.
- **`runner.py` + `report.py`**: end-to-end on synthetic labels+beliefs (DB + LLM mocked) → manifest lists tested + dropped + capped sets with reasons; a winning set promotes only after `promote_streak` runs.
- **`smoke_test.py`**: `python -m ablation.smoke_test` runs the full loop on synthetic data with DB mocked, asserting a known set wins.
- **Migration smoke (DB-gated):** table-exists + insert→readback→delete for all three tables, applied via Neon MCP.

---

## 9. Commitment alignment (theory-aligner gate before merge)

- **#1 (I-Model polymorphism):** `promoted_source_sets.i_model_id` and `ablation_results` carry `i_model_id UUID NULL`; promoted sets can later be scoped to a discovered I-Model.
- **#11 (Semantic-first / hot path stays cheap):** the harness is strictly **offline**; the live read seam (`list_promoted`) is one crash-safe SELECT. Live L3 fusers never brute-force permutations — they read the promoted allowlist (the literal §6 rule).
- **#14 (Meta-context biases every layer):** `meta_context` is a first-class column on promotions, results, and the dataset join; promotions are scoped per `(axis, meta_context)`, matching L3's faithful-per-context combiner pattern.
- **#17 (Labels are provenance-scoped priors):** truth is read through the frozen `labels/` package and ranked by `TRUST_ORDER`; only `ground_truth`/`clinician`/`self_report`/`observed_outcome` grade; priors (`literature`/`demographic`/`llm_bootstrap`/`heuristic`) are explicitly excluded from grading. This is #17 operationalized for source-set evaluation.
- **#9 (Continuous build):** `MacScaffoldBackend` runs today on the Mac; the `DesktopGPUBackend` slot composes forward to the 4080 (and to the #16 JEPA encoder) with a config swap, not a rewrite.
- **Honesty value (no silent caps):** every untested/dropped/capped set is recorded with a reason in `ablation_results.dropped_reason` + `ablation_runs.manifest` and surfaced in the report; promotions always carry `n_eval_pairs`; leakage is prevented by an enforced, recorded train/eval split. The proxy grader and the desktop backend ship as **labeled stubs**, not as silently-faked capability.

---

## 10. Build-phase sequence (workflow phases)

1. **Foundation (sequential, single author):** migration `0014` + `ablation/store.py` (crash-safe writers/readers for the 3 tables) + `config.py` + tests. The persistence + config spine. Apply `0014` via Neon MCP; run the DB-gated table smoke.
2. **Dataset + metrics (sequential, single author):** `source_sets.py`, `dataset.py` (the D1 ledger↔belief join), `metrics.py`, `grader.py` + tests. This is the load-bearing evaluation math; it stays single-author because `dataset.py` is the contract everything downstream depends on.
3. **Backend + evaluate + promote (sequential, single author):** `backend.py` (MacScaffold + documented DesktopGPU slot), `combiners.py`, `evaluate.py`, `promote.py` + tests. Registers nothing shared; produces the verdicts.
4. **Orchestration + surfaces (sequential):** `runner.py`, `report.py`, `cli.py`, `smoke_test.py` + the L3 read seam `list_promoted` + the feature-flagged example call site in `fusion/axes/arousal_inferred.py` (default off) + tests.
5. **Adversarial review (parallel lenses):** data-model correctness (the join + leakage + margin math); architecture-cohesion + commitment alignment (#1/#11/#14/#17 + honesty); build-feasibility / blast-radius / test-coverage.
6. **Controller integration:** apply `0014` via Neon MCP (if not in phase 1), run full DB-free + LLM-free suite + DB-gated smokes, fix review findings, run `theory-aligner`, update `STATUS.md` (date the change) and remove the "Fusion-ablation harness: not built" line from ARCHITECTURE §11, commit, fast-forward-merge to `main`.

Guardrails (per the #1/#2 spec §10): migration number `0014` is pre-allocated and must not collide with `0012`/`0013`; the frozen `labels/ledger.py` read API must not be forked; #5 is only meaningful once real `self_report`/`ground_truth` labels exist in the ledger — which step #1 creates, so this lands *after* `feat/label-ledger` merges.

---

## 11. Relevant absolute paths

- Spec grounding: `/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook-label-ledger/docs/ARCHITECTURE.md` (commitment #17 ~line 210; §3 L3 "Source-set fusion evaluation" ~line 399; §9 "Label store shape" ~line 927 + "Fusion-ablation harness" ~line 931).
- Frozen #1/#2 design: `/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook-label-ledger/docs/superpowers/specs/2026-05-30-label-ledger-state-declared-design.md` (decision D1, §10 back-half plan).
- Frozen ledger package (read-only dependency): `/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook-label-ledger/apps/inference/labels/{provenance.py,record.py,ledger.py,__init__.py}`.
- Truth table: `/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook-label-ledger/apps/inference/migrations/0011_label_ledger.sql`.
- Belief table (the join target, renamed from v2): `/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook-label-ledger/apps/inference/migrations/0009_per_axis_state_and_prediction_log.sql`.
- Patterns to mirror: `apps/inference/fusion/{writer.py,loader.py}` (crash-safe DB I/O), `apps/inference/fusion/axes/arousal_inferred.py` (live combiner / `SOURCE`), `apps/inference/prediction/registry.py` (registry pattern), `apps/inference/db.py` (`get_conn`).
- New package to create: `/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook-label-ledger/apps/inference/ablation/`.
- New migration to create: `/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook-label-ledger/apps/inference/migrations/0014_promoted_source_sets.sql`.
