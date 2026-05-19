"""LLM-driven naming pass for discovered I-Model clusters.

The nightly clusterer creates `i_model_clusters` rows with `label IS NULL`.
This module reads each unlabeled cluster's nearest members, resolves them back
to their source text (chat_messages / regis_observations / dream_recalls /
intents / mood_reports), and asks the LLM for a short noun-phrase facet name
plus a one-sentence description of when the facet appears.

Storage note: `i_model_clusters` only has a `label TEXT NULL` column today —
no description column, no jsonb metadata. We pack both fields into `label`
joined by an em-dash separator: ``"<name> — <description>"``. Activator
consumers split on the em-dash if they want them separately.
"""
from __future__ import annotations

import logging
import re
import string
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402
from llm import ChatClient  # noqa: E402

logger = logging.getLogger(__name__)

MAX_MEMBERS = 8
MIN_RESOLVABLE_MEMBERS = 3
TEXT_TRUNCATE = 200
NAME_MAX_LEN = 40
LABEL_SEPARATOR = " — "  # em-dash with spaces


LABELER_SYSTEM = (
    "You name a mental facet of this person. Given several things they said "
    "or observations about them, what's the through-line? Reply with one short "
    "noun phrase (2-3 words, lowercase, no punctuation) plus one sentence "
    "describing when this facet shows up in the person."
)


class ClusterLabel(BaseModel):
    """LLM schema: a short facet name plus one sentence of context."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description="2-3 word lowercase noun phrase naming this facet"
    )
    description: str = Field(
        description="One sentence describing when this facet appears in the person."
    )


def label_cluster(
    cluster_id: str,
    *,
    client: ChatClient | None = None,
    persist: bool = True,
) -> tuple[str, str] | None:
    """Label a single I-Model cluster. Returns (name, description) or None.

    Returns None when the cluster has too few resolvable members, the LLM call
    fails, or the model returns an empty/unusable name.
    """
    members = _fetch_top_members(cluster_id, limit=MAX_MEMBERS)
    if not members:
        logger.warning("label_cluster: cluster %s has no members", cluster_id)
        return None

    texts = _resolve_member_texts(members)
    if len(texts) < MIN_RESOLVABLE_MEMBERS:
        logger.warning(
            "label_cluster: cluster %s has only %d resolvable members (need >= %d), skipping",
            cluster_id,
            len(texts),
            MIN_RESOLVABLE_MEMBERS,
        )
        return None

    user_prompt = "\n".join(f"- {t}" for t in texts)

    try:
        c = client or ChatClient.auto()
        result = c.chat_structured(
            system=LABELER_SYSTEM,
            user=user_prompt,
            schema=ClusterLabel,
            schema_name="ClusterLabel",
            reasoning_effort="low",
            verbosity="low",
        )
    except Exception as e:
        logger.warning("label_cluster: LLM failed for cluster %s: %s", cluster_id, e)
        return None

    name = _clean_name(result.name)
    description = (result.description or "").strip()
    if not name:
        logger.warning(
            "label_cluster: cluster %s produced empty name after cleanup (raw=%r)",
            cluster_id,
            result.name,
        )
        return None
    if not description:
        description = ""

    if persist:
        try:
            _persist_label(cluster_id, name=name, description=description)
        except Exception as e:
            logger.warning(
                "label_cluster: persist failed for cluster %s: %s", cluster_id, e
            )
            return None

    return name, description


def label_unlabeled_clusters(
    user_id: str,
    *,
    client: ChatClient | None = None,
) -> int:
    """Label every i_model_clusters row for this user where label IS NULL.

    Returns the count of clusters that were successfully labeled. Each cluster
    is committed independently so a single LLM failure does not roll back
    earlier successes.
    """
    cluster_ids = _fetch_unlabeled_cluster_ids(user_id=user_id)
    if not cluster_ids:
        return 0

    c = client or ChatClient.auto()
    labeled = 0
    for cid in cluster_ids:
        result = label_cluster(cid, client=c, persist=True)
        if result is not None:
            labeled += 1
            logger.info(
                "labeled cluster %s -> %s: %s",
                cid,
                result[0],
                result[1],
            )
    return labeled


def _fetch_unlabeled_cluster_ids(*, user_id: str) -> list[str]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text
            FROM i_model_clusters
            WHERE user_id = %s AND label IS NULL
            ORDER BY discovered_at ASC
            """,
            (user_id,),
        )
        return [r[0] for r in cur.fetchall()]


def _fetch_top_members(cluster_id: str, *, limit: int) -> list[tuple[str, str]]:
    """Return up to ``limit`` (source_type, source_id) pairs nearest centroid."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.source_type, e.source_id::text
            FROM embedding_cluster_memberships m
            JOIN embeddings e ON e.id = m.embedding_id
            WHERE m.cluster_id = %s
            ORDER BY m.similarity DESC
            LIMIT %s
            """,
            (cluster_id, limit),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


def _resolve_member_texts(members: list[tuple[str, str]]) -> list[str]:
    """Polymorphically resolve (source_type, source_id) to truncated source text.

    Missing rows (deleted source) are skipped silently. Empty strings are skipped.
    """
    texts: list[str] = []
    for source_type, source_id in members:
        try:
            raw = _resolve_one(source_type, source_id)
        except Exception as e:
            logger.warning(
                "_resolve_member_texts: failed to resolve %s/%s: %s",
                source_type,
                source_id,
                e,
            )
            continue
        if not raw:
            continue
        cleaned = " ".join(raw.split())
        if len(cleaned) > TEXT_TRUNCATE:
            cleaned = cleaned[: TEXT_TRUNCATE - 1].rstrip() + "…"
        texts.append(cleaned)
    return texts


def _resolve_one(source_type: str, source_id: str) -> str | None:
    """Look up the original text for one (source_type, source_id) pair."""
    queries: dict[str, tuple[str, str]] = {
        "chat_message": ("chat_messages", "content"),
        "regis_observation": ("regis_observations", "observation"),
        "dream_recall": ("dream_recalls", "raw_text"),
        "intent": ("intents", "intent_text"),
        "mood": ("mood_reports", "notes"),
        "mood_report": ("mood_reports", "notes"),
    }
    entry = queries.get(source_type)
    if entry is None:
        logger.warning("_resolve_one: unknown source_type=%s", source_type)
        return None
    table, column = entry
    sql = f"SELECT {column} FROM {table} WHERE id = %s"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, (source_id,))
        row = cur.fetchone()
    if row is None:
        return None
    value = row[0]
    if value is None:
        return None
    return str(value)


def _clean_name(raw: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, cap length."""
    if not raw:
        return ""
    cleaned = raw.strip().lower()
    cleaned = cleaned.translate(str.maketrans("", "", string.punctuation))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > NAME_MAX_LEN:
        cleaned = cleaned[:NAME_MAX_LEN].rstrip()
    return cleaned


def _persist_label(cluster_id: str, *, name: str, description: str) -> None:
    """UPDATE i_model_clusters.label with packed ``name <em-dash> description``."""
    if description:
        label = f"{name}{LABEL_SEPARATOR}{description}"
    else:
        label = name
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE i_model_clusters SET label = %s WHERE id = %s",
            (label, cluster_id),
        )
        conn.commit()


__all__ = ["ClusterLabel", "label_cluster", "label_unlabeled_clusters"]
