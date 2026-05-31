"""DB CRUD + lifecycle over the 0012 registry tables. Crash-safe (mirrors fusion).

NEVER writes to label_observations (that is emit.py's job alone). `from db import
get_conn` is imported inside functions so pytest collection stays DB-free.
register_candidate re-validates the #17 invariants before insert.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from .models import (  # noqa: E402
    LiteraturePrior,
    LiteratureSource,
    PriorOrigin,
    PriorStatus,
    Rule,
)

logger = logging.getLogger(__name__)


def insert_source(source: LiteratureSource) -> UUID | None:
    """Insert a curated source row (idempotent on citation). Returns id or None."""
    from db import get_conn

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO literature_sources
                  (citation, doi, url, corpus_path, source_kind, population_note, added_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (citation) DO UPDATE SET citation = EXCLUDED.citation
                RETURNING id
                """,
                (
                    source.citation,
                    source.doi,
                    source.url,
                    source.corpus_path,
                    source.source_kind,
                    source.population_note,
                    source.added_by,
                ),
            )
            new_id = UUID(str(cur.fetchone()[0]))
            conn.commit()
        return new_id
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("insert_source failed (DB absent or error): %s", exc)
        return None


def register_candidate(prior: LiteraturePrior) -> UUID | None:
    """Insert a status='candidate' prior. Re-validates #17 invariants. Returns id or None."""
    if prior.origin not in (PriorOrigin.LLM_LITERATURE_BOOTSTRAP, PriorOrigin.HAND_ENTERED):
        raise ValueError(
            "register_candidate origin must be llm_literature_bootstrap | hand_entered "
            f"(got {prior.origin.value})"
        )
    if prior.rule.claim.axis != prior.target_axis:
        raise ValueError("rule.claim.axis must equal target_axis (#17)")
    if not prior.known_limitations.strip():
        raise ValueError("known_limitations must be non-empty (#17)")

    from db import get_conn

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO literature_priors
                  (target_axis, rule, claim_summary, population, applicability,
                   confidence, known_limitations, source_id, origin, extracted_excerpt, status)
                VALUES (%s, %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, 'candidate')
                RETURNING id
                """,
                (
                    prior.target_axis,
                    json.dumps(prior.rule.to_dict()),
                    prior.claim_summary,
                    prior.population,
                    json.dumps(prior.applicability),
                    prior.confidence,
                    prior.known_limitations,
                    str(prior.source_id),
                    prior.origin.value,
                    prior.extracted_excerpt,
                ),
            )
            new_id = UUID(str(cur.fetchone()[0]))
            conn.commit()
        return new_id
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("register_candidate failed (DB absent or error): %s", exc)
        return None


def _set_status(prior_id: UUID, new_status: PriorStatus, *, superseded_by: UUID | None = None) -> bool:
    from db import get_conn

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE literature_priors
                SET status = %s, superseded_by = COALESCE(%s, superseded_by), updated_at = now()
                WHERE id = %s
                """,
                (
                    new_status.value,
                    str(superseded_by) if superseded_by is not None else None,
                    str(prior_id),
                ),
            )
            updated = cur.rowcount
            conn.commit()
        return updated > 0
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("_set_status failed (DB absent or error): %s", exc)
        return False


def review_prior(prior_id: UUID, reviewer: str, notes: str | None = None) -> bool:
    """Human marks candidate -> reviewed. Returns True if a row was updated."""
    logger.info("review_prior %s by %s: %s", prior_id, reviewer, notes or "")
    return _set_status(prior_id, PriorStatus.REVIEWED)


def retire_prior(
    prior_id: UUID, reviewer: str, reason: str, superseded_by: UUID | None = None
) -> bool:
    """Any status -> retired. Live priors stop being consumable immediately."""
    logger.info("retire_prior %s by %s: %s", prior_id, reviewer, reason)
    return _set_status(prior_id, PriorStatus.RETIRED, superseded_by=superseded_by)


def get_prior(prior_id: UUID) -> LiteraturePrior | None:
    """Load one prior (joined with its citation). Returns None when absent."""
    from db import get_conn

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(_SELECT_PRIOR + " WHERE p.id = %s", (str(prior_id),))
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("get_prior failed (DB absent or error): %s", exc)
        return None
    return _row_to_prior(row) if row else None


def list_priors(
    *, axis: str | None = None, status: PriorStatus | None = None
) -> list[LiteraturePrior]:
    """List priors filtered by axis/status. [] when the DB is absent."""
    from db import get_conn

    clauses: list[str] = []
    params: list[Any] = []
    if axis is not None:
        clauses.append("p.target_axis = %s")
        params.append(axis)
    if status is not None:
        clauses.append("p.status = %s")
        params.append(status.value)
    sql = _SELECT_PRIOR
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY p.created_at DESC"
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("list_priors failed (DB absent or error): %s", exc)
        return []
    return [_row_to_prior(r) for r in rows]


_SELECT_PRIOR = """
SELECT p.id, p.target_axis, p.rule, p.claim_summary, p.population, p.applicability,
       p.confidence, p.known_limitations, p.source_id, p.origin, p.extracted_excerpt,
       p.status, p.superseded_by, s.citation
FROM literature_priors p
JOIN literature_sources s ON s.id = p.source_id
"""


def _row_to_prior(row: tuple) -> LiteraturePrior:
    (
        pid,
        target_axis,
        rule,
        claim_summary,
        population,
        applicability,
        confidence,
        known_limitations,
        source_id,
        origin,
        extracted_excerpt,
        status,
        superseded_by,
        citation,
    ) = row
    rule_dict = rule if isinstance(rule, dict) else json.loads(rule)
    appl = applicability if isinstance(applicability, dict) else (json.loads(applicability) if applicability else {})
    return LiteraturePrior(
        id=UUID(str(pid)),
        target_axis=target_axis,
        rule=Rule.from_dict(rule_dict),
        claim_summary=claim_summary,
        population=population,
        applicability=appl,
        confidence=confidence,
        known_limitations=known_limitations,
        source_id=UUID(str(source_id)),
        origin=PriorOrigin(origin),
        extracted_excerpt=extracted_excerpt,
        status=PriorStatus(status),
        superseded_by=UUID(str(superseded_by)) if superseded_by is not None else None,
        citation=citation,
    )
