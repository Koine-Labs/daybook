-- Drop unused regis_moments.user_response column.
-- Audit #10 in Koine-Labs/daybook#2.
-- The parallel column interject_decisions.user_outcome is the source of truth
-- (filled by outcome_labeler, consumed by learned_decider Thompson bandit).
-- This column was added in migration 0003 but never populated.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'regis_moments' AND column_name = 'user_response'
  ) THEN
    ALTER TABLE regis_moments DROP COLUMN user_response;
  END IF;
END $$;
