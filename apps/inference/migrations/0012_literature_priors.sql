BEGIN;

DO $$ BEGIN
    CREATE TYPE literature_prior_status AS ENUM (
        'candidate',   -- proposed (LLM bootstrap / hand-entry / seed); NOT consumable
        'reviewed',    -- a human has read it; awaiting validation evidence
        'live',        -- passed the promotion gate; consumable + materializable
        'retired'      -- superseded / refuted / withdrawn
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE literature_prior_origin AS ENUM (
        'llm_literature_bootstrap',  -- proposed by the LLM-extraction pass
        'hand_entered',              -- a human typed it directly
        'seed'                       -- shipped in the curated seed set
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- A curated source document (paper / dataset / textbook chapter / review).
-- Local + cited; this is the corpus the extraction reads from.
CREATE TABLE IF NOT EXISTS literature_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citation        TEXT        NOT NULL,        -- human-readable citation string
    doi             TEXT        NULL,
    url             TEXT        NULL,            -- canonical link (NOT fetched at runtime)
    corpus_path     TEXT        NULL,            -- local path to the curated excerpt (inside seed/)
    source_kind     TEXT        NOT NULL,        -- 'paper' | 'dataset' | 'textbook' | 'review'
    population_note TEXT        NULL,            -- study sample (e.g. 'healthy adults 18-35, N=42')
    added_by        TEXT        NOT NULL DEFAULT 'human',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (citation)
);

-- The registry: each row is one weak, citation-backed prior (a reusable, population-level rule).
-- NOT a label_observations row. Carries NO user_id. Becomes a ledger label only at materialization.
CREATE TABLE IF NOT EXISTS literature_priors (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- WHAT IT CLAIMS (commitment #17 required fields)
    target_axis         TEXT        NOT NULL,    -- references an axis id from #2 state_declared / live axes
    rule                JSONB       NOT NULL,    -- the feature-condition -> claimed-value rule (schema in §3.1)
    claim_summary       TEXT        NOT NULL,    -- one-line human-readable claim
    population          TEXT        NOT NULL,    -- applicable population (e.g. 'healthy adults')
    applicability       JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- structured gates (age range, context, modality)
    confidence          REAL        NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    known_limitations   TEXT        NOT NULL,    -- honest caveats; NOT NULL on purpose (#17)

    -- PROVENANCE
    source_id           UUID        NOT NULL REFERENCES literature_sources(id),
    origin              literature_prior_origin NOT NULL,
    extracted_excerpt   TEXT        NULL,        -- the exact text the rule was drawn from

    -- LIFECYCLE
    status              literature_prior_status NOT NULL DEFAULT 'candidate',
    superseded_by       UUID        NULL REFERENCES literature_priors(id),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lit_priors_axis_status
    ON literature_priors (target_axis, status);
CREATE INDEX IF NOT EXISTS idx_lit_priors_status
    ON literature_priors (status);

-- Audit trail of every promotion-gate decision. The gate is the ONLY path candidate/reviewed -> live.
CREATE TABLE IF NOT EXISTS literature_prior_promotions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prior_id             UUID        NOT NULL REFERENCES literature_priors(id),
    from_status          literature_prior_status NOT NULL,
    to_status            literature_prior_status NOT NULL,

    -- VALIDATION EVIDENCE (READ from the #1 ledger; summarized here, not duplicated)
    evidence_user_id     UUID        NULL,       -- the user whose ledger supplied evidence (N=1 today)
    evidence_axis        TEXT        NOT NULL,
    evidence_label_count INTEGER     NOT NULL,   -- how many ledger labels were compared
    evidence_sources     TEXT[]      NOT NULL,   -- which LabelSource values supplied evidence
    validation_metric    TEXT        NOT NULL,   -- e.g. 'sign_agreement_rate'
    validation_score     REAL        NULL,       -- the measured statistic
    passed               BOOLEAN     NOT NULL,
    decided_by           TEXT        NOT NULL,   -- human reviewer id; auto-promotion forbidden in v1
    rationale            TEXT        NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lit_promotions_prior
    ON literature_prior_promotions (prior_id, created_at DESC);

COMMIT;
