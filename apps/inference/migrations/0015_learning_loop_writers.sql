-- 0015_learning_loop_writers.sql
-- Learning-loop plumbing: reshape prediction_log to the L4 forecast schema and
-- add the decision-outcome columns the L5 writer persists on interject_decisions.
--
-- prediction_log as created in 0009 was shaped as a Regis action-choice log
-- (action_type / state_before / observed_state_after) — that purpose is served
-- by interject_decisions (0005, now extended below). It has had ZERO Python
-- writers since 0009 landed, so the table is empty in production and safe to
-- reshape in place. The new shape stores every non-OFFLINE L4 Prediction so
-- forecasts can be graded against later observed state (#13 outcome labels,
-- #16 world-model flywheel). Writers: prediction/prediction_log.py and
-- decision/outcome_log.py.
--
-- Apply via psycopg from a Python smoke test, NOT psql (Neon conn string).

BEGIN;

-- =============================================================================
-- 1. prediction_log v2 — one row per L4 forecast
-- =============================================================================

DROP TABLE prediction_log;

CREATE TABLE prediction_log (
  id                       UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                  UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  axis                     TEXT         NOT NULL,           -- 'rem', 'meta_context', 'audio_social_context', ...
  meta_context             TEXT,                            -- envelope meta-context at prediction time (#14)
  made_at                  TIMESTAMPTZ  NOT NULL,
  horizon_seconds          INTEGER      NOT NULL,
  prediction               JSONB        NOT NULL,           -- {"distribution": ..., "confidence": ..., "provenance": ...}
  action_conditioned_on    JSONB,                           -- NULL = baseline; non-null = counterfactual branch (#15)
  model_id                 TEXT         NOT NULL,
  inputs_used              JSONB,                           -- the L3 estimate / L2 features the predictor consumed
  cold_start               BOOLEAN      NOT NULL DEFAULT FALSE,
  action_conditioning_kind TEXT         NOT NULL DEFAULT 'none',  -- 'none' | 'naive_placeholder' (v1, #15)
  observed_value           JSONB,                           -- filled by the nightly grader: state observed at made_at + horizon
  graded_at                TIMESTAMPTZ,
  i_model_id               UUID,                            -- commitment #1
  created_at               TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_prediction_log_user_axis_made ON prediction_log(user_id, axis, made_at DESC);
CREATE INDEX idx_prediction_log_ungraded ON prediction_log(user_id, made_at) WHERE graded_at IS NULL;

-- =============================================================================
-- 2. interject_decisions — posture + content columns for outcome labels
-- =============================================================================
-- The L5 DecisionLogWriter persists mode/content_kind so outcome labels can
-- condition on Witness/Companion posture and content kind (#5, #13).
-- i_model_id was already added by 0010.

ALTER TABLE interject_decisions
  ADD COLUMN IF NOT EXISTS mode         TEXT,
  ADD COLUMN IF NOT EXISTS content_kind TEXT;

COMMIT;
