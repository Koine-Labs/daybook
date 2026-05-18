-- Daybook 0004: Chat conversations + messages
-- Drafted 2026-05-17
--
-- Adds the substrate for chat Regis — a text-based interactive conversation
-- with the Daybook AI companion. Each conversation is a ChatGPT-style thread;
-- each row in chat_messages is one turn (user or assistant).
--
-- chat_messages.embedding_id points at embeddings(id) so semantic recall over
-- past chat works the same way as recall over dreams/intents/observations.
--
-- To apply:
--   psql $DATABASE_URL -f apps/inference/migrations/0004_chat_messages.sql

-- =============================================================================
-- 1. CHAT_CONVERSATIONS — a thread, like a ChatGPT conversation
-- =============================================================================

CREATE TABLE IF NOT EXISTS chat_conversations (
  id          UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id     UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  started_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  ended_at    TIMESTAMPTZ,
  title       TEXT,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_user_started
  ON chat_conversations(user_id, started_at DESC);

-- =============================================================================
-- 2. CHAT_MESSAGES — one row per turn
-- =============================================================================

CREATE TABLE IF NOT EXISTS chat_messages (
  id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  conversation_id UUID         NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  user_id         UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role            TEXT         NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content         TEXT         NOT NULL,
  sent_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  embedding_id    UUID         REFERENCES embeddings(id) ON DELETE SET NULL,
  metadata        JSONB        NOT NULL DEFAULT '{}'::jsonb,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_sent
  ON chat_messages(conversation_id, sent_at);

CREATE INDEX IF NOT EXISTS idx_chat_messages_user_sent
  ON chat_messages(user_id, sent_at DESC);

-- =============================================================================
-- END OF 0004_chat_messages.sql
-- =============================================================================
