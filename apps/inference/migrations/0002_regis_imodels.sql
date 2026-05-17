-- Daybook 0002: Regis I-Models + empathic state stream
-- Drafted 2026-05-17
--
-- Adds the substrate for Regis-as-character (not just config):
--   1. Extends i_model_clusters with `model_owner` so we can have
--      user-self clusters AND regis-of-user clusters in one table.
--   2. regis_observations  -- what Regis has noticed about the user (embeddable)
--   3. regis_trait_history -- Regis's drifting personality dials over time
--   4. user_state_estimate -- continuous empathic read produced by RealtimeClassifier
--
-- v1 (scripted utterances): only user_state_estimate writes happen passively.
-- v1.5+: regis_observations and regis_trait_history start populating.
--
-- To apply:
--   psql $DATABASE_URL -f apps/inference/migrations/0002_regis_imodels.sql

-- =============================================================================
-- 1. EXTEND i_model_clusters with model_owner
-- =============================================================================
-- Existing rows are treated as user-self clusters (the original intent).
-- New owners: 'regis_of_user' (Regis's model of the user) and
-- 'regis_self' (Regis's self-model — though we'll mostly use regis_trait_history
-- for self-state rather than clustering).

ALTER TABLE i_model_clusters
  ADD COLUMN IF NOT EXISTS model_owner TEXT NOT NULL DEFAULT 'user_self'
    CHECK (model_owner IN ('user_self', 'regis_of_user', 'regis_self'));

CREATE INDEX IF NOT EXISTS idx_i_model_clusters_user_owner
  ON i_model_clusters(user_id, model_owner);

-- =============================================================================
-- 2. REGIS_OBSERVATIONS — what Regis has noticed about the user
-- =============================================================================
-- Each row is a discrete observation Regis has formed. Embeddable so we can
-- retrieve "Regis's relevant memories about this user given current context."
-- Decays via `weight` (or `expires_at` later) so old observations matter less.

CREATE TABLE IF NOT EXISTS regis_observations (
  id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  observed_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  observation   TEXT         NOT NULL,
  context       JSONB        NOT NULL DEFAULT '{}'::jsonb,
  embedding     vector(1536),
  weight        REAL         NOT NULL DEFAULT 1.0 CHECK (weight >= 0 AND weight <= 1),
  source        TEXT         NOT NULL DEFAULT 'regis_inference'
);

CREATE INDEX IF NOT EXISTS idx_regis_observations_user_observed
  ON regis_observations(user_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_regis_observations_embedding
  ON regis_observations
  USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- 3. REGIS_TRAIT_HISTORY — drifting personality dials over time
-- =============================================================================
-- Each row is a snapshot of a trait value at a moment. Latest row per
-- (user_id, trait_name) is the current value. Older rows are the lineage.

CREATE TABLE IF NOT EXISTS regis_trait_history (
  id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  trait_name    TEXT         NOT NULL,
  value         REAL         NOT NULL CHECK (value >= 0 AND value <= 1),
  changed_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  delta         REAL,
  reason        TEXT
);

CREATE INDEX IF NOT EXISTS idx_regis_trait_history_user_trait_changed
  ON regis_trait_history(user_id, trait_name, changed_at DESC);

-- Common trait_name values to seed eventually (not enforced at DB level):
--   'playfulness'   — 0.0 reverent, 1.0 chatty/teasing
--   'reverence'     — 0.0 casual, 1.0 ceremonious
--   'chattiness'    — 0.0 silent, 1.0 verbose
--   'directness'    — 0.0 hedged, 1.0 blunt
--   'familiarity'   — 0.0 formal, 1.0 intimate
--   'humor'         — 0.0 dry, 1.0 absurd

-- =============================================================================
-- 4. USER_STATE_ESTIMATE — continuous empathic read
-- =============================================================================
-- Written by RealtimeClassifier.predict_at() at every epoch. v1 fills only
-- stage_proba (REM prob); v1.5+ fills arousal/valence/presence from EEG.
-- This is the substrate Regis queries to "know" what the user is feeling
-- without being told.

CREATE TABLE IF NOT EXISTS user_state_estimate (
  id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id    UUID         REFERENCES sleep_sessions(id) ON DELETE CASCADE,
  estimated_at  TIMESTAMPTZ  NOT NULL,
  stage_proba   JSONB,       -- {"AWAKE": 0.1, "REM": 0.7, ...} or {"REM": 0.7} for binary
  arousal       REAL         CHECK (arousal IS NULL OR (arousal >= -1 AND arousal <= 1)),
  valence       REAL         CHECK (valence IS NULL OR (valence >= -1 AND valence <= 1)),
  presence      REAL         CHECK (presence IS NULL OR (presence >= 0 AND presence <= 1)),
  confidence    REAL         CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  source        TEXT         NOT NULL,         -- 'realtime_v1' | 'realtime_v1_5_eeg' etc
  features      JSONB                          -- snapshot of feature vector for debugging
);

CREATE INDEX IF NOT EXISTS idx_user_state_estimate_user_estimated
  ON user_state_estimate(user_id, estimated_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_state_estimate_session_estimated
  ON user_state_estimate(session_id, estimated_at);

-- =============================================================================
-- END OF 0002_regis_imodels.sql
-- =============================================================================
