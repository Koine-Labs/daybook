"""Populate and read the regis_self I-Model.

regis_self represents Regis's model of HIMSELF — not the user. Where user_self
is "what we know about Aakash" and regis_of_user is "what Regis has noticed about
Aakash", regis_self is "who Regis is right now": his trait dials + a behavioral
fingerprint summarizing how he's been speaking recently.

Two stores combine:
  - regis_trait_history (already populated by chat.trait_drift) is the canonical
    self-dial state.
  - regis_self_summary (NEW table — created via the i_model_clusters row pattern
    with a sentinel cluster) is a short text fingerprint refreshed by this
    module from his recent moments.

This module is read by composer.py to include "who Regis currently is" in the
system prompt context, so the wisp's voice shifts as it drifts.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402


REGIS_SELF_LABEL = "regis_self_summary"
RECENT_MOMENTS_LIMIT = 30
RECENT_WINDOW_HOURS = 24 * 14


@dataclass
class RegisSelf:
    traits: dict[str, float] = field(default_factory=dict)
    recent_mode_distribution: dict[str, float] = field(default_factory=dict)
    recent_kind_distribution: dict[str, int] = field(default_factory=dict)
    last_moment_at: str | None = None
    moments_in_window: int = 0
    fingerprint: str = ""


def read_regis_self(user_id: str) -> RegisSelf:
    """Build the current snapshot from regis_trait_history + recent regis_moments."""
    traits = _read_traits(user_id)
    moments = _read_recent_moments(user_id)

    if not moments:
        return RegisSelf(traits=traits)

    modes = Counter(m["mode"] for m in moments)
    kinds = Counter(m["kind"] for m in moments)
    total = sum(modes.values())
    mode_dist = {k: round(v / total, 3) for k, v in modes.items()}

    fingerprint = _render_fingerprint(traits=traits, mode_dist=mode_dist, kinds=kinds)
    last_at = moments[0]["occurred_at"]

    return RegisSelf(
        traits=traits,
        recent_mode_distribution=mode_dist,
        recent_kind_distribution=dict(kinds),
        last_moment_at=last_at,
        moments_in_window=len(moments),
        fingerprint=fingerprint,
    )


def refresh_regis_self_cluster(user_id: str) -> str | None:
    """Persist the current fingerprint into a sentinel i_model_clusters row.

    Idempotent: there is one row per user with model_owner='regis_self' and
    label='regis_self_summary'. The centroid_embedding is left NULL — this
    cluster is a label-only row used as a referenceable I-Model id for
    active_i_model_ids in regis_moments.
    """
    snap = read_regis_self(user_id)
    if not snap.fingerprint:
        return None

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text FROM i_model_clusters
            WHERE user_id = %s AND model_owner = 'regis_self' AND label = %s
            LIMIT 1
            """,
            (user_id, REGIS_SELF_LABEL),
        )
        existing = cur.fetchone()

        if existing:
            cluster_id = existing[0]
            cur.execute(
                "UPDATE i_model_clusters SET label = %s WHERE id = %s",
                (REGIS_SELF_LABEL, cluster_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO i_model_clusters (user_id, model_owner, label, centroid_embedding)
                VALUES (%s, 'regis_self', %s, NULL)
                RETURNING id::text
                """,
                (user_id, REGIS_SELF_LABEL),
            )
            cluster_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO i_model_activations
                (cluster_id, activation_strength, source, context)
            VALUES (%s, %s, 'regis_self_refresh', %s::jsonb)
            """,
            (
                cluster_id,
                1.0,
                json.dumps(
                    {
                        "fingerprint": snap.fingerprint,
                        "traits": snap.traits,
                        "mode_distribution": snap.recent_mode_distribution,
                        "kind_distribution": snap.recent_kind_distribution,
                        "moments_in_window": snap.moments_in_window,
                        "last_moment_at": snap.last_moment_at,
                    },
                    default=str,
                ),
            ),
        )
        conn.commit()
    return cluster_id


def _read_traits(user_id: str) -> dict[str, float]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (trait_name) trait_name, value
            FROM regis_trait_history
            WHERE user_id = %s
            ORDER BY trait_name, changed_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    return {r[0]: float(r[1]) for r in rows}


def _read_recent_moments(user_id: str) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENT_WINDOW_HOURS)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT occurred_at, kind, mode
            FROM regis_moments
            WHERE user_id = %s AND occurred_at >= %s
            ORDER BY occurred_at DESC
            LIMIT %s
            """,
            (user_id, cutoff, RECENT_MOMENTS_LIMIT),
        )
        rows = cur.fetchall()
    return [
        {"occurred_at": r[0].isoformat() if r[0] else None, "kind": r[1], "mode": r[2]}
        for r in rows
    ]


def _render_fingerprint(
    *,
    traits: dict[str, float],
    mode_dist: dict[str, float],
    kinds: Counter,
) -> str:
    parts: list[str] = []
    if traits:
        sorted_traits = sorted(traits.items(), key=lambda kv: kv[1], reverse=True)
        top = ", ".join(f"{k}={v:.2f}" for k, v in sorted_traits)
        parts.append(f"traits: {top}")
    if mode_dist:
        m = ", ".join(f"{k} {v:.0%}" for k, v in mode_dist.items())
        parts.append(f"recent posture: {m}")
    if kinds:
        most = ", ".join(f"{k}×{n}" for k, n in kinds.most_common(3))
        parts.append(f"common moments: {most}")
    return " | ".join(parts)
