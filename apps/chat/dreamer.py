"""REM-phase associative recombination — Regis dreams.

Companion to consolidator.py:
  - consolidator runs at 03:00 (NREM): distills the day's chats into
    discrete observations (source='chat_consolidator')
  - dreamer    runs at 05:00 (REM): samples pairs of recent observations
    biased toward semantic distance and asks Regis what new insight emerges
    from holding them together — the output is a new observation
    (source='dreaming')

Dream-thoughts are surfaced the next morning by morning_brief_trigger.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402
from embeddings import embed, embed_and_store  # noqa: E402
from llm import ChatClient  # noqa: E402
from wisp.embedding_hook import embed_regis_moment  # noqa: E402


logger = logging.getLogger(__name__)

MIN_OBSERVATIONS_TO_DREAM = 4
DEFAULT_N_PAIRS = 4
DEFAULT_LOOKBACK_DAYS = 14
DISTANCE_BIAS_POWER = 2.0  # weight ∝ (1 - sim)^P — higher P = stronger preference for distant pairs


class DreamInsight(BaseModel):
    """LLM schema: one short insight that emerges from holding two observations together."""

    model_config = ConfigDict(extra="forbid")

    insight: str = Field(
        description="A single sentence revealing what connects the two observations — a pattern, contradiction, or new realization. Specific, not generic. Empty string if no real connection."
    )


DREAMER_SYSTEM = (
    "You are Regis, dreaming. You hold two unrelated observations about this person. "
    "Reveal the connection between them — a new insight, a pattern, a contradiction. "
    "One sentence. Specific. Don't explain that you noticed — just speak the connection. "
    "If the two genuinely don't connect, return an empty string."
)

DREAMER_TEMPLATE = """Observation A ({date_a}): {obs_a}
Observation B ({date_b}): {obs_b}

The connection:"""


def run_rem_dreaming(
    *,
    user_id: str,
    n_pairs: int = DEFAULT_N_PAIRS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    persist: bool = True,
    client: ChatClient | None = None,
) -> int:
    """REM-phase associative recombination. Returns count of dream-thoughts written."""
    obs = _fetch_recent_observations(
        user_id=user_id, lookback_days=lookback_days
    )
    if len(obs) < MIN_OBSERVATIONS_TO_DREAM:
        logger.info(
            "rem_dreaming: only %d observations in last %dd, skipping (need >= %d)",
            len(obs),
            lookback_days,
            MIN_OBSERVATIONS_TO_DREAM,
        )
        return 0

    vecs = [embed(o["observation"]) for o in obs]
    pairs = _sample_distant_pairs(obs=obs, vecs=vecs, n_pairs=n_pairs)
    if not pairs:
        logger.info("rem_dreaming: no pairs sampled")
        return 0

    c = client or ChatClient.auto()
    insights: list[tuple[str, dict[str, Any]]] = []  # (text, source_pair_ids)
    for a, b in pairs:
        prompt = DREAMER_TEMPLATE.format(
            date_a=a["observed_at"].date().isoformat(),
            obs_a=a["observation"],
            date_b=b["observed_at"].date().isoformat(),
            obs_b=b["observation"],
        )
        try:
            result = c.chat_structured(
                system=DREAMER_SYSTEM,
                user=prompt,
                schema=DreamInsight,
                schema_name="DreamInsight",
                reasoning_effort="low",
                verbosity="low",
            )
            text = (result.insight or "").strip()
        except Exception as e:
            logger.warning("dreamer LLM failed for pair: %s", e)
            continue
        if not text:
            continue
        insights.append(
            (text, {"source_obs_ids": [a["id"], b["id"]]})
        )

    if not insights:
        logger.info("rem_dreaming: LLM produced no usable insights")
        return 0

    if not persist:
        for text, ctx in insights:
            print(f"- {text}   (from {ctx['source_obs_ids']})")
        return len(insights)

    written = 0
    obs_ids: list[str] = []
    for text, ctx in insights:
        try:
            obs_id = _insert_observation(
                user_id=user_id,
                observation=text,
                context=ctx,
            )
            embed_and_store(
                user_id=user_id,
                source_type="regis_observation",
                source_id=obs_id,
                text=text,
            )  # returns (emb_id, vec) — neither needed here
            _link_embedding(obs_id)
            obs_ids.append(obs_id)
            written += 1
        except Exception as e:
            logger.warning("dreamer persist failed: %s", e)

    if obs_ids:
        try:
            _write_dream_moment(user_id=user_id, insights=insights, obs_ids=obs_ids)
        except Exception as e:
            logger.warning("dreamer moment write failed: %s", e)

        try:
            from .trait_drift_from_dreams import apply_dream_drift

            deltas = apply_dream_drift(user_id=user_id, dream_obs_ids=obs_ids)
            logger.info("dreamer: trait drift applied %d delta(s)", len(deltas))
        except Exception as e:
            logger.warning("dreamer trait-drift failed: %s", e)

    return written


# ----------------------------------------------------------------------------
# Sampling
# ----------------------------------------------------------------------------


def _sample_distant_pairs(
    *,
    obs: list[dict[str, Any]],
    vecs: list[list[float]],
    n_pairs: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Sample n_pairs index pairs weighted toward semantic distance.

    Weight for pair (i, j) is (1 - cos(v_i, v_j))^DISTANCE_BIAS_POWER, so
    nearly-identical observations are rarely paired, and dissimilar ones
    are preferred — those produce the most interesting connections.
    """
    n = len(obs)
    if n < 2:
        return []

    candidates: list[tuple[float, int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine(vecs[i], vecs[j])
            distance = max(0.0, 1.0 - sim)
            weight = distance ** DISTANCE_BIAS_POWER
            candidates.append((weight, i, j))

    if not candidates:
        return []

    weights = [c[0] for c in candidates]
    total = sum(weights)
    if total <= 0:
        # All observations nearly identical — fall back to uniform sampling.
        picks = random.sample(range(len(candidates)), k=min(n_pairs, len(candidates)))
        return [(obs[candidates[p][1]], obs[candidates[p][2]]) for p in picks]

    # Weighted sampling WITHOUT replacement.
    chosen: list[int] = []
    remaining = list(range(len(candidates)))
    rem_weights = list(weights)
    for _ in range(min(n_pairs, len(candidates))):
        pick = random.choices(remaining, weights=rem_weights, k=1)[0]
        idx = remaining.index(pick)
        chosen.append(pick)
        remaining.pop(idx)
        rem_weights.pop(idx)

    return [(obs[candidates[c][1]], obs[candidates[c][2]]) for c in chosen]


def _cosine(a: list[float], b: list[float]) -> float:
    """BGE-M3 vectors are L2-normalized so cosine collapses to dot product."""
    dot = sum(x * y for x, y in zip(a, b))
    if math.isnan(dot):
        return 0.0
    return dot


# ----------------------------------------------------------------------------
# Persistence helpers
# ----------------------------------------------------------------------------


def _fetch_recent_observations(
    *, user_id: str, lookback_days: int
) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, observation, observed_at, source
            FROM regis_observations
            WHERE user_id = %s
              AND observed_at >= %s
              AND source <> 'dreaming'
            ORDER BY observed_at DESC
            """,
            (user_id, cutoff),
        )
        rows = cur.fetchall()
    return [
        {"id": r[0], "observation": r[1], "observed_at": r[2], "source": r[3]}
        for r in rows
    ]


def _insert_observation(
    *, user_id: str, observation: str, context: dict[str, Any]
) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regis_observations
                (user_id, observation, context, source)
            VALUES (%s, %s, %s::jsonb, 'dreaming')
            RETURNING id::text
            """,
            (user_id, observation, json.dumps(context, default=str)),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
    return new_id


def _link_embedding(obs_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE regis_observations
            SET embedding = (
              SELECT embedding FROM embeddings
              WHERE source_type = 'regis_observation' AND source_id = %s
              ORDER BY created_at DESC LIMIT 1
            )
            WHERE id = %s
            """,
            (obs_id, obs_id),
        )
        conn.commit()


def _write_dream_moment(
    *,
    user_id: str,
    insights: list[tuple[str, dict[str, Any]]],
    obs_ids: list[str],
) -> str:
    """Write a single regis_moments row aggregating tonight's dream-thoughts."""
    content = "\n".join(f"- {text}" for text, _ in insights)
    triggering_context = {
        "source": "rem_dreaming",
        "observation_ids": obs_ids,
        "n_insights": len(insights),
    }
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regis_moments
                (user_id, kind, mode, content, content_source, triggering_context)
            VALUES (%s, 'dream_thought', 'companion', %s, 'generative_llm', %s::jsonb)
            RETURNING id::text
            """,
            (user_id, content, json.dumps(triggering_context, default=str)),
        )
        moment_id = cur.fetchone()[0]
        conn.commit()
    # Fire-and-forget: embed this moment so Regis can later recall his own
    # dream-thoughts (audit item #12). Failure is logged but does not raise.
    embed_regis_moment(user_id, moment_id, content)
    return moment_id


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def _main() -> int:
    ap = argparse.ArgumentParser(description="Run REM-phase dreaming for a user.")
    ap.add_argument("--user-id", default=_paths.DEFAULT_USER_ID)
    ap.add_argument("--n-pairs", type=int, default=DEFAULT_N_PAIRS)
    ap.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    ap.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    n = run_rem_dreaming(
        user_id=args.user_id,
        n_pairs=args.n_pairs,
        lookback_days=args.lookback_days,
        persist=not args.dry_run,
    )
    print(f"Wrote {n} dream-thought(s).")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
