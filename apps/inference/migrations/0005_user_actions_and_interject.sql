-- Daybook 0005: User actions (gestures + explicit commands) + interject decisions
-- Drafted 2026-05-17
--
-- Captures the "silent back-channel" inputs from user to Regis (taps, head
-- nods, voice grunts, eye blinks, explicit commands) — distinct from voice
-- speech (which goes through chat_messages) and continuous context (which
-- goes through sensor_readings).
--
-- Also captures the auto-interjection decider's "should I speak now?"
-- decisions for later analysis and learning.
--
-- To apply:
--   psql $DATABASE_URL -f apps/inference/migrations/0005_user_actions_and_interject.sql

CREATE TABLE IF NOT EXISTS user_actions (
  id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  occurred_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

  -- Polymorphic kind:
  --   'gesture_tap'         | bone-conduction headphone tap (single/double/long)
  --   'gesture_nod'         | head nod (yes)
  --   'gesture_shake'       | head shake (no)
  --   'gesture_wave'        | camera-detected wave (dismiss)
  --   'gesture_thumbs_up'   | camera-detected thumbs (acknowledge)
  --   'gesture_thumbs_down' | camera-detected (negative)
  --   'gesture_blink'       | EOG-detected blink pattern (v3 — needs BCI)
  --   'voice_grunt'         | mm-hmm / mm-mm / sigh (non-word audio response)
  --   'explicit_command'    | typed or voiced explicit command like "see this" / "listen"
  kind          TEXT         NOT NULL,

  -- What input device produced this
  --   'headphone_button' | 'apple_watch' | 'camera' | 'mic' | 'cli' | ...
  source        TEXT         NOT NULL,

  -- Inferred user intent — populated where determinable
  --   'acknowledge'  | 'dismiss'    | 'see'        | 'listen'
  --   'expand'       | 'silence'    | 'yes'        | 'no'
  --   'not_now'      | 'unknown'
  intent        TEXT,

  -- Free-form context (signal strength, audio sample id, frame ref, etc.)
  context       JSONB        NOT NULL DEFAULT '{}'::jsonb,

  -- If this action was a response to a specific Regis output, link to it
  triggered_by  UUID         REFERENCES regis_moments(id) ON DELETE SET NULL,

  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_actions_user_occurred
  ON user_actions(user_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_actions_kind
  ON user_actions(kind);

CREATE INDEX IF NOT EXISTS idx_user_actions_triggered_by
  ON user_actions(triggered_by);

-- ============================================================================
-- INTERJECT DECISIONS — log of "should I speak now?" decisions
-- ============================================================================
-- Every time the auto-interject decider runs (whether it fires or not), log
-- the inputs + decision + outcome. This is the training data for the eventual
-- learned decider (RL or bandit).

CREATE TABLE IF NOT EXISTS interject_decisions (
  id                  UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id             UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  decided_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

  trigger_kind        TEXT         NOT NULL,
    -- 'post_recall' | 'mood_shift' | 'novel_scene' | 'post_conversation' | ...

  -- Inputs the decider considered
  context_snapshot    JSONB        NOT NULL DEFAULT '{}'::jsonb,
  --   { "user_receptivity": 0.7, "novelty": 0.8, "recent_silence_ms": 600000,
  --     "active_traits": {...}, "time_of_day_score": 0.4 }

  decision            BOOLEAN      NOT NULL,
    -- TRUE = spoke, FALSE = held silence

  reason              TEXT,
    -- short human-readable explanation

  -- If decision = TRUE, link to the resulting moment
  resulting_moment_id UUID         REFERENCES regis_moments(id) ON DELETE SET NULL,

  -- Outcome observed (filled in later, possibly never)
  --   'positive' | 'neutral' | 'negative' | NULL (unobserved)
  -- Inferred from user_action that follows (acknowledge=positive, dismiss=negative)
  user_outcome        TEXT,

  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interject_decisions_user_decided
  ON interject_decisions(user_id, decided_at DESC);

CREATE INDEX IF NOT EXISTS idx_interject_decisions_trigger_kind
  ON interject_decisions(trigger_kind);

-- =============================================================================
-- END OF 0005_user_actions_and_interject.sql
-- =============================================================================
