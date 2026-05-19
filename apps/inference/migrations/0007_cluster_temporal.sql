-- Daybook 0006: Cluster dormancy + lineage (audit item #1 Option D)
-- Drafted 2026-05-19
--
-- I-Model clusters had no lifecycle — they persisted in the same shape forever,
-- and any re-clustering silently overwrote yesterday's shape. The thesis
-- "Regis knows you over years" requires recognizing phases, noticing when old
-- patterns return, and tracking how clusters evolve.
--
-- This migration:
--   1. Adds `status` ('active' | 'dormant') and `last_activated_at` to
--      i_model_clusters so the activator can filter to currently-firing
--      clusters and the dormancy sweep can age out unused ones.
--   2. Backfills `last_activated_at` from `discovered_at` so existing clusters
--      aren't all marked stale on day one.
--   3. Creates `i_model_cluster_lineage` recording how new clusters relate to
--      prior ones (supersedes / merged_into / split_from) — so when nightly
--      clustering produces a centroid sufficiently similar to an existing
--      cluster we record the relationship rather than overwriting silently.
--
-- To apply (via psycopg from a Python smoke test — NOT psql; Neon URL has
-- special chars):
--   python -c "from db import get_conn; import pathlib; \
--     sql = pathlib.Path('migrations/0006_cluster_temporal.sql').read_text(); \
--     [c.execute(sql) for _ in [None] for c in [get_conn().__enter__().cursor()]]"

-- Lifecycle columns on i_model_clusters
ALTER TABLE i_model_clusters
  ADD COLUMN IF NOT EXISTS last_activated_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS status            TEXT NOT NULL DEFAULT 'active';

-- Constrain `status` to the two valid lifecycle values. Without this a typo
-- ('Dormant', 'inactive', 'archived', ...) writes silently and disappears
-- from `get_active_clusters` (which filters status='active') with no error.
-- Idempotent via the DO block — pg_constraint lookup before adding.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'i_model_clusters_status_check'
       AND conrelid = 'i_model_clusters'::regclass
  ) THEN
    ALTER TABLE i_model_clusters
      ADD CONSTRAINT i_model_clusters_status_check
      CHECK (status IN ('active', 'dormant'));
  END IF;
END $$;

-- Backfill last_activated_at for existing rows so they start fresh, not stale.
-- The table has no updated_at / created_at — discovered_at is the only
-- creation timestamp available.
UPDATE i_model_clusters
   SET last_activated_at = COALESCE(discovered_at, now())
 WHERE last_activated_at IS NULL;

-- Index: dormancy sweep walks (user_id, status, last_activated_at) regularly.
CREATE INDEX IF NOT EXISTS idx_i_model_clusters_status_last_activated
  ON i_model_clusters (user_id, status, last_activated_at DESC);

-- Lineage table — records how clusters relate to each other across nightly runs.
CREATE TABLE IF NOT EXISTS i_model_cluster_lineage (
  id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  parent_cluster_id   UUID         NOT NULL REFERENCES i_model_clusters(id) ON DELETE CASCADE,
  child_cluster_id    UUID         NOT NULL REFERENCES i_model_clusters(id) ON DELETE CASCADE,
  relation            TEXT         NOT NULL,  -- 'supersedes' | 'merged_into' | 'split_from'
  similarity          DOUBLE PRECISION,
  recorded_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
  context             JSONB
);

CREATE INDEX IF NOT EXISTS idx_lineage_parent
  ON i_model_cluster_lineage (user_id, parent_cluster_id);
CREATE INDEX IF NOT EXISTS idx_lineage_child
  ON i_model_cluster_lineage (user_id, child_cluster_id);
