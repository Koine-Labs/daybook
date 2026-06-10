"""Idempotent loader: seed/*.json -> registry tables (priors land status='reviewed').

A human curated the seed, so seeds enter as 'reviewed' (not 'candidate') but STILL must
pass promote_prior against ledger evidence before going 'live'. Idempotent: sources are
upserted on citation; a seed prior is skipped if a same-(target_axis, claim_summary,
source) row already exists. Crash-safe: returns (0, 0) when the DB is absent.
`from db import get_conn` is imported inside the function so importing this module is
DB-free.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from .models import LiteraturePrior, PriorOrigin, PriorStatus, Rule, RuleClaim  # noqa: E402

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).resolve().parent / "seed"


def load_seed_priors() -> list[LiteraturePrior]:
    """Parse seed_priors.json into validated LiteraturePrior objects (pure, no DB).

    source_id is left as a sentinel until the DB load resolves citations to ids.
    Validation runs here so a malformed seed fails fast.
    """
    raw = json.loads((SEED_DIR / "seed_priors.json").read_text(encoding="utf-8"))
    priors: list[LiteraturePrior] = []
    from uuid import UUID

    for entry in raw:
        rd = entry["rule"]
        rule = Rule(
            feature=rd["feature"],
            operator=rd["operator"],
            claim=RuleClaim.from_dict(rd["claim"]),
            modality=rd.get("modality", "biometric"),
            threshold=(tuple(rd["threshold"]) if isinstance(rd.get("threshold"), list) else rd.get("threshold")),
            window_s=rd.get("window_s", 60),
            context_gate=rd.get("context_gate", {}) or {},
        )
        priors.append(
            LiteraturePrior(
                target_axis=entry["target_axis"],
                rule=rule,
                claim_summary=entry["claim_summary"],
                population=entry["population"],
                confidence=float(entry["confidence"]),
                known_limitations=entry["known_limitations"],
                applicability=entry.get("applicability", {}) or {},
                extracted_excerpt=entry.get("extracted_excerpt"),
                source_id=UUID(int=0),  # resolved at DB-load time via source_citation
                origin=PriorOrigin.SEED,
                status=PriorStatus.REVIEWED,
                citation=entry["source_citation"],
            )
        )
    return priors


def load_seed() -> tuple[int, int]:
    """Load sources + priors into the DB idempotently. Returns (sources, priors) inserted."""
    from db import get_conn

    sources_raw = json.loads((SEED_DIR / "sources.json").read_text(encoding="utf-8"))
    priors = load_seed_priors()

    try:
        with get_conn() as conn, conn.cursor() as cur:
            citation_to_id: dict[str, str] = {}
            for s in sources_raw:
                cur.execute(
                    """
                    INSERT INTO literature_sources
                      (citation, doi, url, corpus_path, source_kind, population_note)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (citation) DO UPDATE SET citation = EXCLUDED.citation
                    RETURNING id
                    """,
                    (
                        s["citation"],
                        s.get("doi"),
                        s.get("url"),
                        s.get("corpus_path"),
                        s["source_kind"],
                        s.get("population_note"),
                    ),
                )
                citation_to_id[s["citation"]] = str(cur.fetchone()[0])

            sources_n = len(citation_to_id)
            priors_n = 0
            for p in priors:
                source_id = citation_to_id.get(p.citation or "")
                if source_id is None:
                    cur.execute(
                        "SELECT id FROM literature_sources WHERE citation = %s",
                        (p.citation,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        logger.warning("seed prior references unknown source: %s", p.citation)
                        continue
                    source_id = str(row[0])

                cur.execute(
                    """
                    SELECT 1 FROM literature_priors
                    WHERE target_axis = %s AND claim_summary = %s AND source_id = %s
                    """,
                    (p.target_axis, p.claim_summary, source_id),
                )
                if cur.fetchone() is not None:
                    continue

                cur.execute(
                    """
                    INSERT INTO literature_priors
                      (target_axis, rule, claim_summary, population, applicability,
                       confidence, known_limitations, source_id, origin, extracted_excerpt, status)
                    VALUES (%s, %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s, 'seed', %s, 'reviewed')
                    """,
                    (
                        p.target_axis,
                        json.dumps(p.rule.to_dict()),
                        p.claim_summary,
                        p.population,
                        json.dumps(p.applicability),
                        p.confidence,
                        p.known_limitations,
                        source_id,
                        p.extracted_excerpt,
                    ),
                )
                priors_n += 1
            conn.commit()
        return sources_n, priors_n
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("load_seed failed (DB absent or error): %s", exc)
        return 0, 0
