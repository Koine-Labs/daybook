# apps/inference/decision/outcome_log.py
"""L5 decision writer — every ActionDecision becomes an outcome-labelable row.

Target table is interject_decisions (migration 0005), NOT user_actions:
user_actions is the user->Regis gesture backchannel, while interject_decisions
is the purpose-built "should I speak now?" log documented as the training data
for the learned decider (#13). The gate_trace is persisted whole as
context_snapshot — it already records the labelable context (policy, every
gate verdict, transition + cooldown details).

Crash-safe like fusion/writer.py + labels/ledger.py: a missing/unreachable DB
logs a warning and returns None, never crashes the bus. The connection seam is
injectable (defaults to db.get_conn) so unit tests run DB-free with fakes.

Requires migration 0015 (mode + content_kind columns on interject_decisions).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, ContextManager

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from core.protocol.payloads import ActionDecision  # noqa: E402

logger = logging.getLogger(__name__)

ConnFactory = Callable[[], ContextManager[Any]]

_INSERT_SQL = """
INSERT INTO interject_decisions
  (user_id, decided_at, trigger_kind, context_snapshot, decision, reason,
   resulting_moment_id, mode, content_kind, i_model_id)
VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
RETURNING id
"""

UNGRADED_COLUMNS = (
    "id", "user_id", "decided_at", "trigger_kind", "context_snapshot",
    "decision", "reason", "mode", "content_kind", "i_model_id",
)

_UNGRADED_SQL = f"""
SELECT {", ".join(UNGRADED_COLUMNS)}
FROM interject_decisions
WHERE user_outcome IS NULL AND decided_at >= %s
ORDER BY decided_at
"""


class DecisionLogWriter:
    """Persists L5 ActionDecisions to interject_decisions via an injectable conn seam."""

    def __init__(self, conn_factory: ConnFactory | None = None) -> None:
        self._conn_factory: ConnFactory = conn_factory if conn_factory is not None else get_conn

    def write(
        self,
        decision: ActionDecision,
        *,
        trigger_kind: str,
        resulting_moment_id: str | None = None,
    ) -> str | None:
        """INSERT one decision (hold AND interject); returns its id, or None (DB absent)."""
        try:
            with self._conn_factory() as conn, conn.cursor() as cur:
                cur.execute(
                    _INSERT_SQL,
                    (
                        decision.user_id,
                        decision.decided_at,
                        trigger_kind,
                        json.dumps(decision.gate_trace),
                        decision.action == "interject",
                        decision.rationale,
                        resulting_moment_id,
                        decision.mode,
                        decision.content_kind,
                        decision.i_model_id,
                    ),
                )
                new_id = str(cur.fetchone()[0])
                conn.commit()
            return new_id
        except Exception as exc:  # noqa: BLE001 — crash-safe: log and continue
            logger.warning("interject_decisions write failed (DB absent or error): %s", exc)
            return None


def label_outcomes(conn: Any, since: datetime) -> list[dict[str, Any]]:
    """Nightly grading job entrypoint (#13): return ungraded decision rows since `since`.

    SQL-read skeleton only — grading logic (inferring user_outcome from trailing
    user_actions: acknowledge=positive, dismiss=negative) is NOT built here; the
    Thompson bandit consumes the rows once the grader fills user_outcome.
    """
    with conn.cursor() as cur:
        cur.execute(_UNGRADED_SQL, (since,))
        return [dict(zip(UNGRADED_COLUMNS, row)) for row in cur.fetchall()]


__all__ = ["UNGRADED_COLUMNS", "DecisionLogWriter", "label_outcomes"]
