-- 0010_imodel_id_sweep_event_tables.sql
-- Commitment #1 sweep: every EVENT entity must carry `i_model_id UUID NULL`.
--
-- Migration 0009 added i_model_id only to the new tables it introduced
-- (user_state_estimate v2, prediction_log). The earlier event tables from
-- 0001/0004 and the L3/L4/decision tables never received it. This migration
-- backfills the column (nullable, additive, idempotent) across the remaining
-- event tables so the I-Model polymorphism commitment holds uniformly.
--
-- Swept here (9 event tables, verified lacking the column in production):
--   sensor_readings, chat_messages, chat_conversations, regis_observations,
--   interject_decisions, user_actions, i_model_activations,
--   i_model_novelty_log, regis_trait_history
--
-- Per table:
--   ADD COLUMN IF NOT EXISTS i_model_id UUID NULL  (no FK -- see below)
--   partial index on i_model_id WHERE i_model_id IS NOT NULL
--
-- No FK constraint: commitment #6 (self-expanding I-Models) means the I-Model
-- registry shape is still evolving; we keep i_model_id as a soft reference for
-- now and add referential integrity once the registry stabilizes.
--
-- Intentionally EXCLUDED:
--   * Registry / structural tables (not event entities):
--       users, i_models, i_model_clusters, embedding_cluster_memberships
--   * Tables that already carry i_model_id:
--       user_state_estimate + prediction_log (added in 0009)
--       cue_events, dream_recalls, intents, mood_reports, regis_moments,
--       sleep_sessions, wisp_utterances (added in 0002/0003)
--
-- No explicit BEGIN/COMMIT: the Neon MCP migration tool wraps this script in
-- its own transaction. An explicit BEGIN caused a parse error in 0009.

-- =============================================================================
-- 1. sensor_readings
-- =============================================================================
ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS i_model_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_sensor_readings_i_model_id
  ON sensor_readings(i_model_id) WHERE i_model_id IS NOT NULL;

-- =============================================================================
-- 2. chat_messages
-- =============================================================================
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS i_model_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_chat_messages_i_model_id
  ON chat_messages(i_model_id) WHERE i_model_id IS NOT NULL;

-- =============================================================================
-- 3. chat_conversations
-- =============================================================================
ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS i_model_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_chat_conversations_i_model_id
  ON chat_conversations(i_model_id) WHERE i_model_id IS NOT NULL;

-- =============================================================================
-- 4. regis_observations
-- =============================================================================
ALTER TABLE regis_observations ADD COLUMN IF NOT EXISTS i_model_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_regis_observations_i_model_id
  ON regis_observations(i_model_id) WHERE i_model_id IS NOT NULL;

-- =============================================================================
-- 5. interject_decisions
-- =============================================================================
ALTER TABLE interject_decisions ADD COLUMN IF NOT EXISTS i_model_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_interject_decisions_i_model_id
  ON interject_decisions(i_model_id) WHERE i_model_id IS NOT NULL;

-- =============================================================================
-- 6. user_actions
-- =============================================================================
ALTER TABLE user_actions ADD COLUMN IF NOT EXISTS i_model_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_user_actions_i_model_id
  ON user_actions(i_model_id) WHERE i_model_id IS NOT NULL;

-- =============================================================================
-- 7. i_model_activations
-- =============================================================================
ALTER TABLE i_model_activations ADD COLUMN IF NOT EXISTS i_model_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_i_model_activations_i_model_id
  ON i_model_activations(i_model_id) WHERE i_model_id IS NOT NULL;

-- =============================================================================
-- 8. i_model_novelty_log
-- =============================================================================
ALTER TABLE i_model_novelty_log ADD COLUMN IF NOT EXISTS i_model_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_i_model_novelty_log_i_model_id
  ON i_model_novelty_log(i_model_id) WHERE i_model_id IS NOT NULL;

-- =============================================================================
-- 9. regis_trait_history
-- =============================================================================
ALTER TABLE regis_trait_history ADD COLUMN IF NOT EXISTS i_model_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_regis_trait_history_i_model_id
  ON regis_trait_history(i_model_id) WHERE i_model_id IS NOT NULL;
