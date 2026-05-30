BEGIN;

CREATE TABLE IF NOT EXISTS label_observations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL,
    axis          TEXT NOT NULL,              -- target axis the label speaks to (arousal, fatigue, cognitive_load, sleep_stage, focus, mood, ...)
    value         JSONB NOT NULL,             -- scalar / category / distribution claimed for the axis
    confidence    REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),  -- [0,1] strength of THIS label
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
