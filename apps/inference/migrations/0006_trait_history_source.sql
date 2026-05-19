-- Daybook 0006: Add source TEXT column to regis_trait_history
-- Drafted 2026-05-19
--
-- Context (audit item #1 Option C — trait decay toward learned baseline):
-- regis_trait_history is becoming polymorphic across multiple writers.
-- Today only conversational/dream rules write rows; soon the nightly decay
-- engine + baseline computer will also write rows. We need to distinguish:
--
--   source IS NULL or 'heuristic' or 'dream' — real signal from interaction
--   source = 'decay'                          — nightly pull toward baseline
--   source = 'baseline'                       — nightly snapshot of EWMA history
--
-- The daily cap on trait_drift writes (4 * MAX_DELTA per UTC day) excludes
-- decay/baseline rows from the budget — only real signal counts toward the cap.
--
-- Purely additive: nullable TEXT, no constraint, no index churn. Existing
-- rows remain valid (source = NULL).
--
-- To apply:
--   from db import get_conn; ALTER TABLE regis_trait_history ADD COLUMN ...
--   (or psql, but per repo convention apply via psycopg)

ALTER TABLE regis_trait_history
  ADD COLUMN IF NOT EXISTS source TEXT;

-- No CHECK constraint on purpose: source values evolve (decay, baseline, plus
-- any future writers). If we ever need to enforce, add an enum migration later.

-- Lightweight index for queries like "sum of today's non-decay deltas for
-- trait X" used by the daily-cap enforcement in trait_drift.
CREATE INDEX IF NOT EXISTS idx_regis_trait_history_user_trait_source_changed
  ON regis_trait_history(user_id, trait_name, source, changed_at DESC);
