"""Label ledger read/write — crash-safe (mirrors fusion/writer.py + loader.py).

Writes swallow DB errors with a logged warning so a missing/unreachable DB never
crashes the arc; reads return [] in the same case. `from db import get_conn` is
the single connection seam (never re-implemented).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from .provenance import LabelSource
from .record import LabelRecord

logger = logging.getLogger(__name__)


def record_label(rec: LabelRecord) -> str | None:
    """INSERT one label; return its id, or None when the DB is absent/unreachable."""
    user_id, axis, value, confidence, source, provenance, consent_scope, i_model_id, meta_context, observed_at = rec.to_row()
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO label_observations
                  (user_id, axis, value, confidence, source, provenance,
                   consent_scope, i_model_id, meta_context, observed_at)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    user_id,
                    axis,
                    json.dumps(value),
                    confidence,
                    source,
                    json.dumps(provenance),
                    consent_scope,
                    i_model_id,
                    meta_context,
                    observed_at,
                ),
            )
            new_id = str(cur.fetchone()[0])
            conn.commit()
        return new_id
    except Exception as exc:  # noqa: BLE001 — crash-safe: log and continue
        logger.warning("record_label failed (DB absent or error): %s", exc)
        return None


def record_labels(recs: list[LabelRecord]) -> int:
    """Atomically batch-write labels in one transaction; return the count written.

    All rows commit together or none do: on any error the transaction rolls back
    and 0 is returned. Crash-safe — a missing/unreachable DB returns 0, never raises.
    """
    if not recs:
        return 0
    try:
        with get_conn() as conn, conn.cursor() as cur:
            try:
                for rec in recs:
                    (user_id, axis, value, confidence, source, provenance,
                     consent_scope, i_model_id, meta_context, observed_at) = rec.to_row()
                    cur.execute(
                        """
                        INSERT INTO label_observations
                          (user_id, axis, value, confidence, source, provenance,
                           consent_scope, i_model_id, meta_context, observed_at)
                        VALUES (%s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s, %s)
                        """,
                        (
                            user_id,
                            axis,
                            json.dumps(value),
                            confidence,
                            source,
                            json.dumps(provenance),
                            consent_scope,
                            i_model_id,
                            meta_context,
                            observed_at,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return len(recs)
    except Exception as exc:  # noqa: BLE001 — crash-safe: log and continue
        logger.warning("record_labels failed (DB absent or error): %s", exc)
        return 0


def read_labels(
    user_id: str,
    *,
    axis: str | None = None,
    sources: list[LabelSource | str] | None = None,
    since: datetime | None = None,
    limit: int | None = None,
) -> list[LabelRecord]:
    """Read labels for a user, newest first; [] when the DB is absent/unreachable."""
    clauses = ["user_id = %s"]
    params: list[object] = [user_id]
    if axis is not None:
        clauses.append("axis = %s")
        params.append(axis)
    if sources:
        norm = [s.value if isinstance(s, LabelSource) else s for s in sources]
        clauses.append("source = ANY(%s)")
        params.append(norm)
    if since is not None:
        clauses.append("observed_at >= %s")
        params.append(since)
    sql = (
        "SELECT user_id, axis, value, confidence, source, provenance, "
        "consent_scope, i_model_id, meta_context, observed_at "
        "FROM label_observations WHERE " + " AND ".join(clauses) +
        " ORDER BY observed_at DESC"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — crash-safe: log and return []
        logger.warning("read_labels failed (DB absent or error): %s", exc)
        return []
    out: list[LabelRecord] = []
    for user_id_, axis_, value, confidence, source, provenance, consent_scope, i_model_id, meta_context, observed_at in rows:
        try:
            label_source = LabelSource(source)
        except ValueError:  # off-taxonomy source — skip this row, keep the batch alive.
            logger.warning("read_labels skipping row with unknown source: %r", source)
            continue
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        out.append(
            LabelRecord(
                user_id=str(user_id_),
                axis=axis_,
                value=value,
                source=label_source,
                observed_at=observed_at,
                confidence=confidence,
                provenance=provenance if isinstance(provenance, dict) else {},
                consent_scope=consent_scope,
                i_model_id=str(i_model_id) if i_model_id is not None else None,
                meta_context=meta_context,
            )
        )
    return out
