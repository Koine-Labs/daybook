"""regis_self as a nightly projection (not a clustering problem).

The clusterer skips ``model_owner='regis_self'`` because Regis isn't a set of
many noisy embeddings to discover from — he's one coherent entity with
drifting trait dials. Without this module, no row of any kind with
``model_owner='regis_self'`` ever gets written, even though the schema accepts
it. That left the third I-Model architectural commitment (CLAUDE.md #4) as a
half-built shell.

This module produces a single ``i_model_clusters`` row per user with
``model_owner='regis_self'``, refreshed nightly. The row summarizes Regis's
current state:
  - His current trait dial values (from ``fetch_current_trait_values``)
  - A short fingerprint of recent moment kinds (last 7d — what has he done?)
  - A short fingerprint of recent dream-thoughts (last 7d — what has he
    chewed on?)
  - A one-paragraph LLM-synthesized "who Regis is right now" fingerprint
  - An embedding of that fingerprint, so he's queryable like the other two
    I-Models (``user_self``, ``regis_of_user``).

UPSERT semantics: one row per ``(user_id, model_owner='regis_self')``,
enforced in app code (SELECT-then-UPDATE-or-INSERT) so no migration is
needed alongside parallel-PR migrations.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

INFERENCE_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = INFERENCE_DIR.parent
for _p in (INFERENCE_DIR, APPS_DIR):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from db import get_conn  # noqa: E402
from embeddings import embed  # noqa: E402
from llm import ChatClient  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
LOOKBACK_DAYS = 7
MAX_DREAM_THOUGHTS = 5
MAX_MOMENT_KINDS = 8

PROJECTOR_SYSTEM = (
    "Synthesize a one-paragraph fingerprint of who Regis is right now based "
    "on these inputs. Lean, specific, no preamble. Write in third person "
    "about Regis (the AI companion, dry/curious/warm in canon TBATE style). "
    "Capture the current shape of his personality and what he's been "
    "attending to. Three to five sentences max. "
    "This will be read by Regis himself as ambient self-context — write it "
    "so it shapes posture, not so it gets quoted."
)


class RegisSelfFingerprint(BaseModel):
    """LLM schema: one-paragraph synthesis of Regis's current state."""

    model_config = ConfigDict(extra="forbid")

    fingerprint: str = Field(
        description="One paragraph (3-5 sentences) describing who Regis is right now — current trait shape and recent attentional focus."
    )


def refresh_regis_self(
    user_id: str = DEFAULT_USER_ID,
    *,
    persist: bool = True,
    client: ChatClient | None = None,
) -> str | None:
    """Compute and persist (or print) the current regis_self projection.

    Returns the cluster_id of the regis_self row (created or updated), or
    None if the LLM call fails / nothing to project.

    Steps:
      1. Read current traits via fetch_current_trait_values.
      2. Pull recent moment kinds with counts (last 7d).
      3. Pull recent dream-thoughts (last 7d, up to MAX_DREAM_THOUGHTS).
      4. Synthesize a one-paragraph fingerprint via chat_structured.
      5. Embed the fingerprint.
      6. UPSERT one i_model_clusters row keyed on
         (user_id, model_owner='regis_self').
    """
    from chat.baseline_computer import fetch_current_trait_values

    traits = fetch_current_trait_values(user_id)
    moment_kinds = _fetch_recent_moment_kinds(user_id)
    dream_thoughts = _fetch_recent_dream_thoughts(user_id)

    if not traits and not moment_kinds and not dream_thoughts:
        logger.info(
            "refresh_regis_self: nothing to project for user=%s (no traits, no moments, no dreams)",
            user_id,
        )
        return None

    user_prompt = _build_prompt(
        traits=traits,
        moment_kinds=moment_kinds,
        dream_thoughts=dream_thoughts,
    )

    try:
        c = client or ChatClient.auto()
        result = c.chat_structured(
            system=PROJECTOR_SYSTEM,
            user=user_prompt,
            schema=RegisSelfFingerprint,
            schema_name="RegisSelfFingerprint",
            reasoning_effort="low",
            verbosity="low",
        )
    except Exception as e:
        logger.warning("refresh_regis_self: LLM failed: %s", e)
        return None

    fingerprint = (result.fingerprint or "").strip()
    if not fingerprint:
        logger.warning("refresh_regis_self: empty fingerprint from LLM")
        return None

    if not persist:
        print(fingerprint)
        return None

    try:
        vec = embed(fingerprint)
    except Exception as e:
        logger.warning("refresh_regis_self: embed failed: %s", e)
        return None

    cluster_id = _upsert_regis_self_row(
        user_id=user_id,
        label=fingerprint,
        centroid=vec,
    )
    logger.info(
        "refresh_regis_self: upserted cluster %s for user %s",
        cluster_id,
        user_id,
    )
    return cluster_id


# ----------------------------------------------------------------------------
# Prompt assembly
# ----------------------------------------------------------------------------


def _build_prompt(
    *,
    traits: dict[str, float],
    moment_kinds: list[tuple[str, int]],
    dream_thoughts: list[str],
) -> str:
    """Compose the user-side input for the projector LLM call."""
    lines: list[str] = []

    if traits:
        lines.append("Current trait dials (0.0 = low, 1.0 = high):")
        for name, value in sorted(traits.items()):
            lines.append(f"  - {name}: {value:.2f}")
    else:
        lines.append("Current trait dials: (none recorded yet)")
    lines.append("")

    if moment_kinds:
        lines.append(f"What Regis has been doing (last {LOOKBACK_DAYS}d):")
        for kind, count in moment_kinds:
            lines.append(f"  - {kind} x{count}")
    else:
        lines.append(f"What Regis has been doing (last {LOOKBACK_DAYS}d): (nothing logged)")
    lines.append("")

    if dream_thoughts:
        lines.append(f"What Regis has been dreaming about (last {LOOKBACK_DAYS}d):")
        for t in dream_thoughts:
            lines.append(f"  - {t}")
    else:
        lines.append(f"What Regis has been dreaming about (last {LOOKBACK_DAYS}d): (no dream-thoughts)")

    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Data fetchers
# ----------------------------------------------------------------------------


def _fetch_recent_moment_kinds(user_id: str) -> list[tuple[str, int]]:
    """Return (kind, count) pairs for regis_moments in the last LOOKBACK_DAYS."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT kind, count(*)::int
            FROM regis_moments
            WHERE user_id = %s AND occurred_at >= %s
            GROUP BY kind
            ORDER BY count(*) DESC
            LIMIT %s
            """,
            (user_id, cutoff, MAX_MOMENT_KINDS),
        )
        return [(r[0], int(r[1])) for r in cur.fetchall()]


def _fetch_recent_dream_thoughts(user_id: str) -> list[str]:
    """Return recent dream-thought texts (regis_observations source='dreaming')."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT observation
            FROM regis_observations
            WHERE user_id = %s
              AND source = 'dreaming'
              AND observed_at >= %s
            ORDER BY observed_at DESC
            LIMIT %s
            """,
            (user_id, cutoff, MAX_DREAM_THOUGHTS),
        )
        return [str(r[0]) for r in cur.fetchall() if r[0]]


# ----------------------------------------------------------------------------
# UPSERT (app-code, no migration)
# ----------------------------------------------------------------------------


def _upsert_regis_self_row(
    *,
    user_id: str,
    label: str,
    centroid: list[float],
) -> str:
    """SELECT-then-UPDATE-or-INSERT a single regis_self row for this user.

    Keyed on (user_id, model_owner='regis_self'). If a prior row exists,
    refresh its label, centroid, last_activated_at, and status. Otherwise
    insert a new row.

    Returns the cluster_id (UUID as string).
    """
    centroid_literal = _vec_literal(centroid)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text
            FROM i_model_clusters
            WHERE user_id = %s AND model_owner = 'regis_self'
            ORDER BY discovered_at ASC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()

        if row is None:
            cur.execute(
                """
                INSERT INTO i_model_clusters
                    (user_id, model_owner, label, centroid_embedding,
                     status, last_activated_at)
                VALUES (%s, 'regis_self', %s, %s::vector, 'active', now())
                RETURNING id::text
                """,
                (user_id, label, centroid_literal),
            )
            cluster_id = cur.fetchone()[0]
        else:
            cluster_id = row[0]
            cur.execute(
                """
                UPDATE i_model_clusters
                   SET label              = %s,
                       centroid_embedding = %s::vector,
                       status             = 'active',
                       last_activated_at  = now()
                 WHERE id = %s
                """,
                (label, centroid_literal, cluster_id),
            )
        conn.commit()
    return cluster_id


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def _main() -> int:
    ap = argparse.ArgumentParser(
        description="Refresh the regis_self projection for a user."
    )
    ap.add_argument("--user-id", default=DEFAULT_USER_ID)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print fingerprint instead of persisting.",
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    cluster_id = refresh_regis_self(user_id=args.user_id, persist=not args.dry_run)
    if cluster_id is None and not args.dry_run:
        print("(no row written)")
        return 1
    if cluster_id is not None:
        print(f"regis_self cluster_id: {cluster_id}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())


__all__ = ["RegisSelfFingerprint", "refresh_regis_self"]
