"""Persist promotion-gate audit rows. Crash-safe; never writes the ledger."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from uuid import UUID

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from .models import Promotion

logger = logging.getLogger(__name__)


def write_promotion(promo: Promotion) -> UUID | None:
    """INSERT one literature_prior_promotions row. Returns id or None when DB absent."""
    from db import get_conn

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO literature_prior_promotions
                  (prior_id, from_status, to_status, evidence_user_id, evidence_axis,
                   evidence_label_count, evidence_sources, validation_metric,
                   validation_score, passed, decided_by, rationale)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    str(promo.prior_id),
                    promo.from_status.value,
                    promo.to_status.value,
                    str(promo.evidence_user_id) if promo.evidence_user_id is not None else None,
                    promo.evidence_axis,
                    promo.evidence_label_count,
                    promo.evidence_sources,
                    promo.validation_metric,
                    promo.validation_score,
                    promo.passed,
                    promo.decided_by,
                    promo.rationale,
                ),
            )
            new_id = UUID(str(cur.fetchone()[0]))
            conn.commit()
        return new_id
    except Exception as exc:  # noqa: BLE001 — crash-safe
        logger.warning("write_promotion failed (DB absent or error): %s", exc)
        return None
