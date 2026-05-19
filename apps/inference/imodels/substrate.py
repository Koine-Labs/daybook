"""Shared 'who is Regis talking to right now' substrate.

Single source of truth for the user-state slice both chat (companion turns)
and wisp (autonomous moments) need. Each surface pulls from the same well so
trait drift / I-Model activations / current prosody learned via chat transfer
to wisp's sleep cues, walking remarks, post-recall reflections, inner pulses.

What lives here:
  - regis_traits           (delegates to chat.baseline_computer.fetch_current_trait_values)
  - current_user_state     (latest user_state_estimate, ≤1h fresh)
  - current_prosody        (last 10min of audio_context sensor_readings)
  - active_i_models        (top-K via get_active_clusters; requires embedding)
  - relevant_observations  (top-N regis_observations by similarity; requires embedding)

What does NOT live here (chat-specific, stays in chat.retrieval.gather_context):
  - current_conversation_recent
  - similar_past_exchanges
  - relevant_health_data (keyword-gated, only on opt-in phrasing)

Callers:
  - apps/chat/retrieval.py::gather_context   -> wraps + adds conversation reads
  - apps/wisp/composer.py::compose_utterance -> uses directly
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Path setup so we can import db helper + embeddings store
INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402
from embeddings import retrieve_similar  # noqa: E402

from .activator import get_active_clusters  # noqa: E402


# Only treat user_state_estimate as "current" if it's at most 1 hour old.
# Otherwise we'd inject stale snapshots into prompts (e.g., a sleep
# estimate from last night doesn't mean Aakash is asleep right now).
USER_STATE_FRESHNESS_SECONDS = 60 * 60
PROSODY_WINDOW_MINUTES = 10
PROSODY_LIMIT = 3
ACTIVE_IMODEL_TOP_K = 3
ACTIVE_IMODEL_MIN_SIM = 0.4
OBSERVATION_TOP_K = 3


@dataclass
class SubstrateContext:
    """The shared substrate: who Regis is talking to right now."""

    regis_traits: dict[str, float] = field(default_factory=dict)
    current_user_state: dict[str, Any] | None = None
    current_prosody: list[dict[str, Any]] = field(default_factory=list)
    active_i_models: list[dict[str, Any]] = field(default_factory=list)
    relevant_observations: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Flat dict view (the shape chat's gather_context returns)."""
        return {
            "regis_traits": self.regis_traits,
            "current_user_state": self.current_user_state,
            "current_prosody": self.current_prosody,
            "active_i_models": self.active_i_models,
            "relevant_observations": self.relevant_observations,
        }

    @property
    def active_i_model_cluster_ids(self) -> list[str]:
        """Just the cluster_id strings (for persistence on regis_moments)."""
        return [im["cluster_id"] for im in self.active_i_models if "cluster_id" in im]

    @property
    def primary_i_model_cluster_id(self) -> str | None:
        """Top-1 cluster id (for regis_moments.i_model_id), or None."""
        ids = self.active_i_model_cluster_ids
        return ids[0] if ids else None


def gather_substrate(
    *,
    user_id: str,
    query_embedding: list[float] | None = None,
) -> SubstrateContext:
    """Assemble the shared substrate for one prompt-building moment.

    `query_embedding` is optional because wisp doesn't always have a "current
    query." When None, embedding-dependent reads (active_i_models,
    relevant_observations) are skipped gracefully — the caller still gets
    traits + state + prosody.
    """
    ctx = SubstrateContext(
        regis_traits=_current_traits(user_id),
        current_user_state=_latest_user_state(user_id),
        current_prosody=_recent_prosody(user_id),
    )
    if query_embedding is not None:
        ctx.active_i_models = _active_i_models(
            user_id=user_id, user_embedding=query_embedding
        )
        ctx.relevant_observations = _relevant_observations(
            user_id=user_id, qvec=query_embedding, top_k=OBSERVATION_TOP_K
        )
    return ctx


# ---------------------------------------------------------------------------
# Internal readers
# ---------------------------------------------------------------------------


def _current_traits(user_id: str) -> dict[str, float]:
    """Latest signal-sourced trait values. Delegates to the canonical reader
    in chat.baseline_computer so the source-filter convention (exclude
    baseline/decay) lives in one place. Imported lazily so this module
    doesn't pull all of chat at import time."""
    try:
        from chat.baseline_computer import fetch_current_trait_values  # type: ignore
    except Exception:
        # Fallback: try as a relative-style path. If chat isn't on sys.path
        # for some reason, surface empty rather than crash the substrate.
        return {}
    return fetch_current_trait_values(user_id)


def _latest_user_state(user_id: str) -> dict[str, Any] | None:
    """Latest user_state_estimate row, only if fresh (≤1h old).

    Stale rows from past sessions or smoke tests are dropped: they would
    mislead Regis into thinking the user is currently in REM, etc.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=USER_STATE_FRESHNESS_SECONDS
    )
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT estimated_at, stage_proba, arousal, valence, presence,
                       confidence, source
                FROM user_state_estimate
                WHERE user_id = %s
                  AND estimated_at >= %s
                ORDER BY estimated_at DESC
                LIMIT 1
                """,
                (user_id, cutoff),
            )
            row = cur.fetchone()
    except Exception:
        return None
    if row is None:
        return None
    return {
        "estimated_at": row[0].isoformat() if row[0] else None,
        "stage_proba": row[1],
        "arousal": row[2],
        "valence": row[3],
        "presence": row[4],
        "confidence": row[5],
        "source": row[6],
    }


def _recent_prosody(
    user_id: str, limit: int = PROSODY_LIMIT
) -> list[dict[str, Any]]:
    """Last `limit` audio_context sensor_readings in the past 10 minutes."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=PROSODY_WINDOW_MINUTES)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT recorded_at, payload
                FROM sensor_readings
                WHERE user_id = %s
                  AND kind = 'audio_context'
                  AND recorded_at >= %s
                ORDER BY recorded_at DESC
                LIMIT %s
                """,
                (user_id, cutoff, limit),
            )
            rows = cur.fetchall()
    except Exception:
        return []
    return [
        {
            "recorded_at": r[0].isoformat(),
            "tone": (r[1] or {}).get("tone"),
            "energy": (r[1] or {}).get("energy"),
            "pitch_mean_hz": (r[1] or {}).get("pitch_mean_hz"),
            "pitch_std_hz": (r[1] or {}).get("pitch_std_hz"),
            "speaking_rate_wpm": (r[1] or {}).get("speaking_rate_wpm"),
            "vad_active": (r[1] or {}).get("vad_active"),
        }
        for r in rows
    ]


def _active_i_models(
    *, user_id: str, user_embedding: list[float]
) -> list[dict[str, Any]]:
    """Top-K I-Model clusters firing for the current embedding.

    Returns dicts shaped for prompt rendering AND persistence. `cluster_id`
    is included so callers (e.g. wisp composer) can stash real UUIDs on
    regis_moments.active_i_model_ids instead of the hardcoded [] of yore.
    """
    try:
        active = get_active_clusters(
            user_id=user_id,
            query_embedding=user_embedding,
            top_k=ACTIVE_IMODEL_TOP_K,
            min_similarity=ACTIVE_IMODEL_MIN_SIM,
        )
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for c in active:
        label = c.label or f"unlabeled cluster #{c.cluster_id[:8]}"
        out.append(
            {
                "cluster_id": c.cluster_id,
                "label": label,
                "similarity": round(c.similarity, 3),
                "model_owner": c.model_owner,
            }
        )
    return out


def _relevant_observations(
    *, user_id: str, qvec: list[float], top_k: int
) -> list[dict[str, Any]]:
    """Top-N regis_observations by embedding similarity, with full text."""
    try:
        hits = retrieve_similar(
            qvec,
            user_id=user_id,
            top_k=top_k,
            source_types=["regis_observation"],
        )
    except Exception as e:
        return [{"_retrieval_error": str(e)}]

    if not hits:
        return []

    obs_ids = [h.source_id for h in hits]
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, observation, observed_at
                FROM regis_observations
                WHERE id = ANY(%s)
                """,
                (obs_ids,),
            )
            rows = {str(r[0]): r for r in cur.fetchall()}
    except Exception as e:
        return [{"_retrieval_error": str(e)}]

    sim_by_id = {h.source_id: h.similarity for h in hits}
    out: list[dict[str, Any]] = []
    for oid in obs_ids:
        if oid in rows:
            r = rows[oid]
            out.append(
                {
                    "observation": r[1],
                    "observed_at": r[2].isoformat(),
                    "similarity": round(float(sim_by_id[oid]), 3),
                }
            )
    return out
