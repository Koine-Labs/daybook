"""Stage A — outcome labeler for interject_decisions.

Reads chat_messages following each decision=true row and backfills
user_outcome using simple heuristics. Designed to run nightly.

Heuristics (in order, first match wins):
  - 0 user messages in the 3-min window after decided_at  -> 'ignored'
  - any user message contains a dismissive marker         -> 'negative'
  - longest user message < 15 chars                       -> 'neutral'
  - longest user message >= 15 chars AND shares >=1 token
    with the interjection's trigger_payload thought       -> 'positive'
  - default                                               -> 'neutral'

decision=false rows are skipped — we cannot observe the outcome of silence.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402

from .triggers import register  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
DEFAULT_LOOKBACK_HOURS = 48
RESPONSE_WINDOW_MINUTES = 3
SHORT_USER_MSG_CHAR_LIMIT = 15

DISMISSIVE_MARKERS: tuple[str, ...] = (
    "stop",
    "shut up",
    "later",
    "no thanks",
    "no thank",
    "busy",
    "not now",
    "leave me alone",
    "go away",
    "shush",
    "quiet",
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "is", "it", "to", "of",
        "in", "on", "at", "for", "with", "as", "by", "be", "are", "was",
        "were", "this", "that", "these", "those", "i", "you", "we", "they",
        "he", "she", "him", "her", "them", "my", "your", "our", "their",
        "me", "us", "do", "does", "did", "so", "not", "no", "yes", "ok",
        "okay", "just", "have", "has", "had", "from", "about", "what",
        "when", "where", "who", "how", "why", "can", "could", "would",
        "should", "will", "shall", "may", "might", "been", "being",
        "there", "here", "all", "any", "some", "more", "less", "very",
    }
)


@register("outcome_labeler")
def label_recent_decisions(
    user_id: str = DEFAULT_USER_ID,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
) -> int:
    """Backfill user_outcome on recent decision=true rows. Returns count labeled."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    try:
        rows = _fetch_unlabeled_decisions(user_id=user_id, cutoff=cutoff)
    except Exception as e:
        logger.warning("[outcome_labeler] fetch failed: %s", e)
        return 0

    labeled = 0
    for decision_id, decided_at, context_snapshot in rows:
        try:
            user_msgs = _user_messages_after(
                user_id=user_id, decided_at=decided_at,
            )
            outcome = _classify(user_msgs=user_msgs, context_snapshot=context_snapshot)
            if _write_outcome(decision_id=decision_id, outcome=outcome):
                labeled += 1
                logger.info(
                    "[outcome_labeler] %s -> %s (%d user msgs)",
                    decision_id, outcome, len(user_msgs),
                )
        except Exception as e:
            logger.warning("[outcome_labeler] %s skipped: %s", decision_id, e)

    return labeled


def _fetch_unlabeled_decisions(
    *, user_id: str, cutoff: datetime,
) -> list[tuple[str, datetime, dict]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, decided_at, context_snapshot
            FROM interject_decisions
            WHERE user_id = %s
              AND decision = TRUE
              AND user_outcome IS NULL
              AND decided_at >= %s
            ORDER BY decided_at ASC
            """,
            (user_id, cutoff),
        )
        out: list[tuple[str, datetime, dict]] = []
        for row in cur.fetchall():
            decision_id, decided_at, snapshot = row
            if isinstance(snapshot, str):
                try:
                    snapshot = json.loads(snapshot)
                except Exception:
                    snapshot = {}
            out.append((str(decision_id), decided_at, snapshot or {}))
        return out


def _user_messages_after(*, user_id: str, decided_at: datetime) -> list[str]:
    window_end = decided_at + timedelta(minutes=RESPONSE_WINDOW_MINUTES)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT content FROM chat_messages
            WHERE user_id = %s
              AND role = 'user'
              AND sent_at BETWEEN %s AND %s
            ORDER BY sent_at ASC
            """,
            (user_id, decided_at, window_end),
        )
        return [r[0] for r in cur.fetchall() if r[0]]


def _classify(*, user_msgs: list[str], context_snapshot: dict) -> str:
    if not user_msgs:
        return "ignored"

    joined_lower = " \n ".join(m.lower() for m in user_msgs)
    for marker in DISMISSIVE_MARKERS:
        if marker in joined_lower:
            return "negative"

    longest = max(user_msgs, key=len)
    if len(longest.strip()) < SHORT_USER_MSG_CHAR_LIMIT:
        return "neutral"

    if _topic_related(user_msgs=user_msgs, context_snapshot=context_snapshot):
        return "positive"

    return "neutral"


def _topic_related(*, user_msgs: list[str], context_snapshot: dict) -> bool:
    payload = context_snapshot.get("trigger_payload") or {}
    thought = payload.get("thought") or ""
    if not thought:
        return False
    interject_tokens = _content_tokens(thought)
    if not interject_tokens:
        return False
    user_tokens = _content_tokens(" ".join(user_msgs))
    return len(interject_tokens & user_tokens) >= 1


def _content_tokens(text: str) -> set[str]:
    return {
        t for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 2 and t not in _STOPWORDS
    }


def _write_outcome(*, decision_id: str, outcome: str) -> bool:
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE interject_decisions
                SET user_outcome = %s
                WHERE id = %s AND user_outcome IS NULL
                """,
                (outcome, decision_id),
            )
            updated = cur.rowcount
            conn.commit()
        return updated > 0
    except Exception as e:
        logger.warning("[outcome_labeler] write failed for %s: %s", decision_id, e)
        return False


def _main() -> int:
    ap = argparse.ArgumentParser(description="Label recent interject_decisions outcomes.")
    ap.add_argument("--user-id", default=DEFAULT_USER_ID)
    ap.add_argument("--lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    n = label_recent_decisions(
        user_id=args.user_id, lookback_hours=args.lookback_hours,
    )
    print(f"{n} labeled")
    return 0


if __name__ == "__main__":
    sys.exit(_main())


__all__ = ["label_recent_decisions"]
