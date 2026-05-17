-- Daybook v0 initial schema
-- Drafted 2026-05-17
--
-- This file is the DATABASE source of truth. It must stay in sync with the
-- TypeScript types in packages/shared/src/types.ts.
--
-- Conventions:
--   - All IDs are UUID (Postgres-native uuid-ossp).
--   - All timestamps are TIMESTAMPTZ (with timezone). Never use TIMESTAMP.
--   - i_model_id is nullable on every event entity per the I-Model commitment.
--   - sensor_readings is a plain table (Neon doesn't support TimescaleDB; we'll
--     migrate to native PG partitioning or another host if/when scale demands).
--   - embeddings uses pgvector with HNSW index for cosine similarity search.
--   - Polymorphic content uses `kind TEXT` + `payload JSONB` pattern.
--
-- To apply locally (against a Neon connection):
--   psql $DATABASE_URL -f apps/inference/migrations/0001_initial.sql

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- USERS
-- =============================================================================

CREATE TABLE users (
  id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  email         TEXT         NOT NULL UNIQUE,
  display_name  TEXT         NOT NULL,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- I-MODEL CLUSTERS
-- Populated post-hoc by ML clustering on accumulated embeddings.
-- Schema is present from day 1 per the I-Model architectural commitment.
-- =============================================================================

CREATE TABLE i_model_clusters (
  id                  UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id             UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  label               TEXT,
  centroid_embedding  vector(1536),
  discovered_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_i_model_clusters_user
  ON i_model_clusters(user_id);

-- =============================================================================
-- SLEEP SESSIONS
-- =============================================================================

CREATE TABLE sleep_sessions (
  id                UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id           UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  started_at        TIMESTAMPTZ  NOT NULL,
  ended_at          TIMESTAMPTZ  NOT NULL,
  duration_seconds  INTEGER      NOT NULL,
  sensor_sources    TEXT[]       NOT NULL DEFAULT '{}',
  i_model_id        UUID         REFERENCES i_model_clusters(id) ON DELETE SET NULL,
  notes             TEXT,
  created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sleep_sessions_user_started
  ON sleep_sessions(user_id, started_at DESC);

-- =============================================================================
-- SLEEP STAGE CLASSIFICATIONS
-- Multiple sources can classify the same epoch; useful for cross-validation.
-- =============================================================================

CREATE TABLE sleep_stage_classifications (
  id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id      UUID         NOT NULL REFERENCES sleep_sessions(id) ON DELETE CASCADE,
  epoch_start_at  TIMESTAMPTZ  NOT NULL,
  stage           TEXT         NOT NULL CHECK (stage IN ('AWAKE','REM','CORE','DEEP','UNKNOWN')),
  source          TEXT         NOT NULL,
  confidence      REAL         CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sleep_stage_classifications_session_epoch
  ON sleep_stage_classifications(session_id, epoch_start_at);

CREATE INDEX idx_sleep_stage_classifications_source
  ON sleep_stage_classifications(source);

-- =============================================================================
-- SENSOR READINGS (high-volume time series)
-- Plain Postgres table (Neon doesn't support TimescaleDB).
-- Polymorphic via `kind` + `payload`. Good indexes carry us a long way at v0
-- scale; migrate to native PG declarative partitioning when needed.
-- =============================================================================

CREATE TABLE sensor_readings (
  id           UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id   UUID         REFERENCES sleep_sessions(id) ON DELETE CASCADE,
  user_id      UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  recorded_at  TIMESTAMPTZ  NOT NULL,
  source       TEXT         NOT NULL,
  kind         TEXT         NOT NULL,
  payload      JSONB        NOT NULL
);

CREATE INDEX idx_sensor_readings_user_recorded
  ON sensor_readings(user_id, recorded_at DESC);

CREATE INDEX idx_sensor_readings_session_recorded
  ON sensor_readings(session_id, recorded_at);

CREATE INDEX idx_sensor_readings_kind
  ON sensor_readings(kind);

CREATE INDEX idx_sensor_readings_user_kind_recorded
  ON sensor_readings(user_id, kind, recorded_at DESC);

-- =============================================================================
-- DREAM RECALLS
-- v1's primary success-measurement substrate.
-- =============================================================================

CREATE TABLE dream_recalls (
  id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id      UUID         REFERENCES sleep_sessions(id) ON DELETE SET NULL,
  captured_at     TIMESTAMPTZ  NOT NULL,
  depth           TEXT         NOT NULL CHECK (depth IN ('NONE','FRAGMENT','SCENE','NARRATIVE')),
  raw_text        TEXT         NOT NULL,
  voice_memo_url  TEXT,
  themes          TEXT[]       NOT NULL DEFAULT '{}',
  i_model_id      UUID         REFERENCES i_model_clusters(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dream_recalls_user_captured
  ON dream_recalls(user_id, captured_at DESC);

CREATE INDEX idx_dream_recalls_session
  ON dream_recalls(session_id);

-- =============================================================================
-- WISP UTTERANCES
-- The wisp's conversational moments (vs. cues, which are different).
-- =============================================================================

CREATE TABLE wisp_utterances (
  id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id    UUID         REFERENCES sleep_sessions(id) ON DELETE SET NULL,
  kind          TEXT         NOT NULL,
  triggered_at  TIMESTAMPTZ  NOT NULL,
  text_content  TEXT         NOT NULL,
  audio_ref     TEXT,
  i_model_id    UUID         REFERENCES i_model_clusters(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_wisp_utterances_user_triggered
  ON wisp_utterances(user_id, triggered_at DESC);

CREATE INDEX idx_wisp_utterances_kind
  ON wisp_utterances(kind);

-- =============================================================================
-- CUE EVENTS
-- TMR-style audio cues delivered during sleep. Not conversational.
-- `content_type` is the content-polymorphism hook.
-- =============================================================================

CREATE TABLE cue_events (
  id                         UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                    UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id                 UUID         NOT NULL REFERENCES sleep_sessions(id) ON DELETE CASCADE,
  delivered_at               TIMESTAMPTZ  NOT NULL,
  cue_content                TEXT         NOT NULL,
  content_type               TEXT         NOT NULL,
  target_stage               TEXT         NOT NULL,
  actual_stage_at_delivery   TEXT,
  audio_duration_ms          INTEGER      NOT NULL,
  audio_ref                  TEXT         NOT NULL,
  response_detected          BOOLEAN,
  i_model_id                 UUID         REFERENCES i_model_clusters(id) ON DELETE SET NULL
);

CREATE INDEX idx_cue_events_session_delivered
  ON cue_events(session_id, delivered_at);

CREATE INDEX idx_cue_events_content_type
  ON cue_events(content_type);

-- =============================================================================
-- EMBEDDINGS (pgvector store for the personal model)
-- =============================================================================

CREATE TABLE embeddings (
  id           UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id      UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_type  TEXT          NOT NULL,
  source_id    UUID          NOT NULL,
  embedding    vector(1536)  NOT NULL,
  model        TEXT          NOT NULL,
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_embeddings_user_source
  ON embeddings(user_id, source_type);

-- HNSW index for fast cosine-similarity nearest-neighbor search.
CREATE INDEX idx_embeddings_vector_cosine
  ON embeddings
  USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- INTENTS (pre-sleep intent setting)
-- =============================================================================

CREATE TABLE intents (
  id                  UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id             UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  set_at              TIMESTAMPTZ  NOT NULL,
  intent_text         TEXT         NOT NULL,
  target_session_id   UUID         REFERENCES sleep_sessions(id) ON DELETE SET NULL,
  i_model_id          UUID         REFERENCES i_model_clusters(id) ON DELETE SET NULL
);

CREATE INDEX idx_intents_user_set
  ON intents(user_id, set_at DESC);

-- =============================================================================
-- MOOD REPORTS (valence + arousal, Russell's circumplex)
-- =============================================================================

CREATE TABLE mood_reports (
  id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reported_at   TIMESTAMPTZ  NOT NULL,
  valence       REAL         NOT NULL CHECK (valence >= -1 AND valence <= 1),
  arousal       REAL         NOT NULL CHECK (arousal >= -1 AND arousal <= 1),
  notes         TEXT,
  i_model_id    UUID         REFERENCES i_model_clusters(id) ON DELETE SET NULL
);

CREATE INDEX idx_mood_reports_user_reported
  ON mood_reports(user_id, reported_at DESC);

-- =============================================================================
-- END OF 0001_initial.sql
-- =============================================================================
