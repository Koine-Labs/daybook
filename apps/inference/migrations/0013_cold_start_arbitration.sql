-- 0013_cold_start_arbitration.sql
-- Cold-start arbitration (commitment #4): per-axis population<->personal mixing
-- weight + calibration_state machine. Consumes the frozen label ledger
-- (label_observations, LabelSource) read-only. Builds on baseline 0012.
-- Append-only / additive. Apply via psycopg smoke test, never psql.
--
-- Baseline: builds on 0012 (literature_priors) + 0011 (label_observations).
-- Does NOT alter label_observations. All event-ish rows carry i_model_id (#1).

BEGIN;

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
    tier_trust          JSONB NULL,   -- {"self_report":1.0,"observed_outcome":0.7,"heuristic":0.35}
    tier_halflife_s     JSONB NULL,   -- {"self_report":2592000,"observed_outcome":1209600,"heuristic":604800}

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

COMMIT;
