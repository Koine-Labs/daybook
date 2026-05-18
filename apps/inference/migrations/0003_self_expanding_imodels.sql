-- Daybook 0003: Self-expanding I-Models + BGE-M3 embedding dim + moment polymorphism
-- Drafted 2026-05-17
--
-- Three architectural moves:
--   1. Change embedding columns from vector(1536) → vector(1024) for BGE-M3.
--      (Safe: vector tables are all empty.)
--   2. Add self-expansion infrastructure for I-Models:
--        - embedding_cluster_memberships (many-to-many — your "neurons fire
--          across multiple I-Models" insight)
--        - i_model_activations (which I-Models are active at a given moment)
--        - i_model_novelty_log (pre-clustering buffer of "doesn't fit any
--          existing cluster" observations)
--   3. Add regis_moments — generalized "anything Regis ever did" log that
--      subsumes cue_events for the always-on companion architecture.
--      (cue_events stays for backward compat; new code writes regis_moments.)
--
-- To apply:
--   psql $DATABASE_URL -f apps/inference/migrations/0003_self_expanding_imodels.sql

-- =============================================================================
-- 1. CHANGE EMBEDDING DIM 1536 → 1024 (BGE-M3 dense)
-- =============================================================================

-- Drop the HNSW index on embeddings.embedding (must drop before ALTER on a vector col)
DROP INDEX IF EXISTS idx_embeddings_vector_cosine;

-- Embeddings table
ALTER TABLE embeddings
  ALTER COLUMN embedding TYPE vector(1024);

-- I-Model clusters centroid
ALTER TABLE i_model_clusters
  ALTER COLUMN centroid_embedding TYPE vector(1024);

-- Regis observations embedding (from migration 0002)
ALTER TABLE regis_observations
  ALTER COLUMN embedding TYPE vector(1024);

-- Drop any HNSW index on regis_observations.embedding if it exists
DROP INDEX IF EXISTS idx_regis_observations_embedding;

-- Recreate HNSW indexes on the new-dim columns
CREATE INDEX idx_embeddings_vector_cosine
  ON embeddings
  USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_regis_observations_embedding
  ON regis_observations
  USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- 2. EMBEDDING ↔ CLUSTER MEMBERSHIPS (many-to-many)
-- =============================================================================
-- Each embedding can belong to multiple I-Models with different similarity
-- scores (Aakash's "neurons fire across multiple I-Models" insight).

CREATE TABLE IF NOT EXISTS embedding_cluster_memberships (
  embedding_id  UUID         NOT NULL REFERENCES embeddings(id) ON DELETE CASCADE,
  cluster_id    UUID         NOT NULL REFERENCES i_model_clusters(id) ON DELETE CASCADE,
  similarity    REAL         NOT NULL CHECK (similarity >= -1 AND similarity <= 1),
  assigned_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  assignment_source TEXT     NOT NULL DEFAULT 'clusterer',
  PRIMARY KEY (embedding_id, cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_embedding_cluster_memberships_cluster
  ON embedding_cluster_memberships(cluster_id, similarity DESC);

-- =============================================================================
-- 3. I-MODEL ACTIVATIONS — which clusters are "active" at a given moment
-- =============================================================================
-- Written by the activator job at decision-time. Used to query "what context
-- was the system in when Regis composed this utterance" later.

CREATE TABLE IF NOT EXISTS i_model_activations (
  id                  UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  cluster_id          UUID         NOT NULL REFERENCES i_model_clusters(id) ON DELETE CASCADE,
  activated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  activation_strength REAL         NOT NULL CHECK (activation_strength >= 0 AND activation_strength <= 1),
  source              TEXT         NOT NULL DEFAULT 'activator_job',
  context             JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_i_model_activations_cluster_activated
  ON i_model_activations(cluster_id, activated_at DESC);

-- =============================================================================
-- 4. I-MODEL NOVELTY LOG — pre-clustering buffer
-- =============================================================================
-- When current state doesn't fit any existing I-Model well, observation lands
-- here. Enough accumulated novelty triggers a new clustering run that may
-- crystallize a new I-Model.

CREATE TABLE IF NOT EXISTS i_model_novelty_log (
  id                      UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                 UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  observed_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  state_snapshot          JSONB        NOT NULL,
  embedding               vector(1024),
  nearest_cluster_id      UUID         REFERENCES i_model_clusters(id) ON DELETE SET NULL,
  nearest_similarity      REAL,
  flagged_for_clustering  BOOLEAN      NOT NULL DEFAULT FALSE,
  clustered_into_id       UUID         REFERENCES i_model_clusters(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_i_model_novelty_log_user_observed
  ON i_model_novelty_log(user_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_i_model_novelty_log_flagged
  ON i_model_novelty_log(flagged_for_clustering, observed_at DESC)
  WHERE flagged_for_clustering = TRUE;

-- =============================================================================
-- 5. REGIS_MOMENTS — generalized any-context Regis action log
-- =============================================================================
-- Subsumes cue_events for the always-on companion architecture. Any context
-- where Regis ever speaks or acts gets a row: sleep cue, morning recall prompt,
-- walking remark, post-conversation tease, news-pull comment, etc.
--
-- cue_events stays for backward compat; new code writes regis_moments.

CREATE TABLE IF NOT EXISTS regis_moments (
  id                  UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id             UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id          UUID         REFERENCES sleep_sessions(id) ON DELETE SET NULL,
  occurred_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

  -- Polymorphic kind: 'rem_whisper' | 'pre_sleep_greeting' | 'intent_setting'
  -- | 'wake_greeting' | 'morning_recall_prompt' | 'capture_ack' | 'walking_remark'
  -- | 'conversation_tease' | 'news_pull_comment' | 'mood_check' | ... (future kinds)
  kind                TEXT         NOT NULL,

  -- Dual-mode tag: 'witness' (during sleep, reverent) | 'companion' (awake, dry)
  -- | 'neutral' (mode-agnostic, e.g., admin actions)
  mode                TEXT         NOT NULL CHECK (mode IN ('witness', 'companion', 'neutral')),

  -- What Regis said / did
  content             TEXT         NOT NULL,
  content_source      TEXT         NOT NULL CHECK (content_source IN ('scripted_variant', 'generative_llm', 'system')),

  -- Optional audio artifact
  audio_ref           TEXT,
  audio_duration_ms   INTEGER,

  -- Snapshot of state used to compose this moment
  triggering_context  JSONB        NOT NULL DEFAULT '{}'::jsonb,

  -- I-Models active at the moment (composite link to the activator's snapshot)
  active_i_model_ids  UUID[]       NOT NULL DEFAULT '{}',

  -- Primary i_model link for backward compat with the i_model_id pattern
  i_model_id          UUID         REFERENCES i_model_clusters(id) ON DELETE SET NULL,

  -- Observed reaction (dismissed, lingered, captured, ignored, etc.)
  user_response       JSONB,

  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_regis_moments_user_occurred
  ON regis_moments(user_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_regis_moments_session
  ON regis_moments(session_id);

CREATE INDEX IF NOT EXISTS idx_regis_moments_kind
  ON regis_moments(kind);

CREATE INDEX IF NOT EXISTS idx_regis_moments_mode
  ON regis_moments(mode);

-- =============================================================================
-- END OF 0003_self_expanding_imodels.sql
-- =============================================================================
