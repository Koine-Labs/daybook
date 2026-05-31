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
