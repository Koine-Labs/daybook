-- 0009_per_axis_state_and_prediction_log.sql
-- Reshape user_state_estimate (wide-row → per-axis-row), add prediction_log,
-- add consent metadata columns on sensor_readings.
--
-- Aligned to ARCHITECTURE.md §3 L3 (per-axis storage with freshness policy)
-- and commitment #13 (outcome-driven action selection).
--
-- Backfill: existing user_state_estimate rows (sleep classifier output) are
-- migrated to per-axis-rows in the same transaction. One wide row in →
-- up to N per-axis rows out (one per non-NULL axis).

BEGIN;

-- =============================================================================
-- 1. user_state_estimate v2 — per-axis-row
-- =============================================================================

CREATE TABLE user_state_estimate_v2 (
  id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  axis          TEXT         NOT NULL,                -- 'arousal_inferred', 'meta_context', 'sleep_stage', 'state_declared', 'audio_social_context', 'cognitive_load'
  timestamp     TIMESTAMPTZ  NOT NULL,
  value         JSONB        NOT NULL,                -- {"category": "focused"} or {"scalar": 0.55} or {"label": "REM", "prob": 0.71}
  confidence    DOUBLE PRECISION CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  source        TEXT,                                 -- 'L3.fusion.meta_context', 'classifier.binary_rem', etc.
  meta_context  TEXT,                                 -- 'waking', 'sleep', or sub-context like 'waking/focused' — denormalized for fast filter
  i_model_id    UUID,                                 -- commitment #1
  session_id    UUID         REFERENCES sleep_sessions(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_use_v2_user_axis_ts ON user_state_estimate_v2(user_id, axis, timestamp DESC);
CREATE INDEX idx_use_v2_user_ts_meta ON user_state_estimate_v2(user_id, timestamp DESC) WHERE meta_context IS NOT NULL;

-- Backfill from existing wide-row user_state_estimate.
-- One row in → multiple per-axis rows out for each non-NULL column.

-- sleep_stage axis (from stage_proba)
INSERT INTO user_state_estimate_v2 (user_id, axis, timestamp, value, confidence, source, session_id)
SELECT
  user_id,
  'sleep_stage',
  estimated_at,
  stage_proba,
  confidence,
  source,
  session_id
FROM user_state_estimate
WHERE stage_proba IS NOT NULL;

-- arousal_inferred axis (from arousal scalar)
INSERT INTO user_state_estimate_v2 (user_id, axis, timestamp, value, confidence, source, session_id)
SELECT
  user_id,
  'arousal_inferred',
  estimated_at,
  jsonb_build_object('scalar', arousal),
  confidence,
  source,
  session_id
FROM user_state_estimate
WHERE arousal IS NOT NULL;

-- valence axis (from valence scalar) — kept for backward-compat even though
-- v1 L3 doesn't fuse it yet. We can extend later without touching schema.
INSERT INTO user_state_estimate_v2 (user_id, axis, timestamp, value, confidence, source, session_id)
SELECT
  user_id,
  'valence_inferred',
  estimated_at,
  jsonb_build_object('scalar', valence),
  confidence,
  source,
  session_id
FROM user_state_estimate
WHERE valence IS NOT NULL;

-- presence axis (from presence scalar) — same rationale
INSERT INTO user_state_estimate_v2 (user_id, axis, timestamp, value, confidence, source, session_id)
SELECT
  user_id,
  'presence_inferred',
  estimated_at,
  jsonb_build_object('scalar', presence),
  confidence,
  source,
  session_id
FROM user_state_estimate
WHERE presence IS NOT NULL;

-- Drop wide-row table; rename v2 into place.
DROP TABLE user_state_estimate;
ALTER TABLE user_state_estimate_v2 RENAME TO user_state_estimate;
ALTER INDEX idx_use_v2_user_axis_ts RENAME TO idx_use_user_axis_ts;
ALTER INDEX idx_use_v2_user_ts_meta RENAME TO idx_use_user_ts_meta;

-- =============================================================================
-- 2. prediction_log — every Regis discrete-action choice for #13 outcome-driven learning
-- =============================================================================

CREATE TABLE prediction_log (
  id                     UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ts                     TIMESTAMPTZ  NOT NULL,
  action_type            TEXT         NOT NULL,           -- 'interject', 'no_interject', 'chat_response'
  action_kind            TEXT,                            -- 'witness', 'companion', 'check_in', 'capture_ack', etc.
  state_before           JSONB        NOT NULL,           -- snapshot of relevant axes at decision time
  expected_state_after   JSONB,                           -- L4 predictor's forecast (naive in v1)
  observed_state_after   JSONB,                           -- filled by reconciler 5-15min later
  user_response_label    TEXT         CHECK (user_response_label IS NULL OR user_response_label IN ('accepted','rejected','ignored','unknown')),
  user_response_signal   JSONB,                           -- raw signal (next-utterance prosody, HR delta, etc.)
  i_model_id             UUID,                            -- commitment #1
  created_at             TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_prediction_log_user_ts ON prediction_log(user_id, ts DESC);
CREATE INDEX idx_prediction_log_user_action_ts ON prediction_log(user_id, action_type, ts DESC);

-- =============================================================================
-- 3. sensor_readings consent metadata columns
-- =============================================================================

ALTER TABLE sensor_readings
  ADD COLUMN consent_scope  TEXT,         -- 'mic_continuous_v1', 'cam_continuous_v1', etc. — indexes consent record at write time
  ADD COLUMN suppressed_for JSONB;        -- {"reason": "other_voice_present", "window_start": "..."} — when pipeline paused but row still landed

CREATE INDEX idx_sensor_readings_consent_scope ON sensor_readings(consent_scope) WHERE consent_scope IS NOT NULL;

COMMIT;
