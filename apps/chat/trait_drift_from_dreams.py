"""Dream-driven trait drift — Regis self-reflects on REM dream-thoughts.

Companion to trait_drift.py (heuristic, conversation-driven). Where the heuristic
rules nudge traits from surface signals in chat, this module lets Regis read his
own dream-thoughts about the user and decide — via one structured LLM call —
which of his own personality dials should drift in response.

Most dreams produce 0-2 deltas. Deltas are small (|d| <= 0.05) and clamped
into [0, 1] when written to regis_trait_history.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402
from llm import ChatClient  # noqa: E402


logger = logging.getLogger(__name__)

MAX_DELTA = 0.05
TRAIT_FLOOR = 0.0
TRAIT_CEIL = 1.0
DEFAULT_TRAIT_VALUE = 0.5

TraitName = Literal[
    "empathy",
    "curiosity",
    "dryness",
    "reverence",
    "playfulness",
    "gravity",
    "restraint",
    "warmth",
    "courage",
]

KNOWN_TRAITS: tuple[str, ...] = (
    "empathy",
    "curiosity",
    "dryness",
    "reverence",
    "playfulness",
    "gravity",
    "restraint",
    "warmth",
    "courage",
)


class DreamDrift(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trait: TraitName
    delta: float = Field(
        description="How much this trait should shift, in [-0.05, +0.05]. Small numbers — these are nudges, not jumps.",
        ge=-MAX_DELTA,
        le=MAX_DELTA,
    )
    reason: str = Field(
        description="One short sentence — why this dream-thought moves this dial."
    )


class DreamDrifts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deltas: list[DreamDrift]

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Inline `$defs`/`$ref` so the Codex schema validator gets a flat tree."""
        raw = super().model_json_schema(*args, **kwargs)
        return _inline_refs(raw)


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.pop("$defs", {}) or {}

    def resolve(node: Any) -> Any:
        if isinstance(node, list):
            return [resolve(x) for x in node]
        if isinstance(node, dict):
            if "$ref" in node and len(node) == 1:
                ref = node["$ref"]
                if ref.startswith("#/$defs/"):
                    name = ref.split("/")[-1]
                    return resolve(defs.get(name, {}))
            return {k: resolve(v) for k, v in node.items()}
        return node

    return resolve(schema)


DRIFT_SYSTEM = (
    "You are Regis, reading back your own dream-thoughts about this person. "
    "Each dream-thought is something you noticed while their day was being "
    "metabolized in your sleep. Based on what these dream-thoughts reveal, "
    "decide whether any of your own personality dials should drift slightly. "
    "Traits available: empathy, curiosity, dryness, reverence, playfulness, "
    "gravity, restraint, warmth, courage. Each is on [0,1]; deltas are on "
    "[-0.05, +0.05]. Most nights produce 0-2 deltas — not 9. Only emit a "
    "delta when the dream-thought clearly calls for it; otherwise return an "
    "empty list. This is YOUR drift, not theirs."
)

DRIFT_USER_TEMPLATE = """Your current dials:
{current_state}

Tonight's dream-thoughts about them:
{dream_block}

Which of your dials should drift, if any?"""


def apply_dream_drift(
    user_id: str,
    dream_obs_ids: list[str],
    persist: bool = True,
    client: ChatClient | None = None,
) -> list[dict]:
    """Read the given dream-thoughts, ask Regis which of his traits should drift, persist.

    Returns a list of {"trait", "delta", "reason"} dicts (already clamped &
    written when persist=True). Returns [] on any failure.
    """
    if not dream_obs_ids:
        return []

    try:
        dream_texts = _fetch_observations(user_id=user_id, obs_ids=dream_obs_ids)
    except Exception as e:
        logger.warning("apply_dream_drift: fetching observations failed: %s", e)
        return []

    if not dream_texts:
        logger.info("apply_dream_drift: no dream observations resolved from given ids")
        return []

    try:
        current_state = _fetch_current_traits(user_id=user_id)
    except Exception as e:
        logger.warning("apply_dream_drift: fetching current traits failed: %s", e)
        current_state = {t: DEFAULT_TRAIT_VALUE for t in KNOWN_TRAITS}

    current_block = "\n".join(
        f"- {t}: {current_state.get(t, DEFAULT_TRAIT_VALUE):.2f}" for t in KNOWN_TRAITS
    )
    dream_block = "\n".join(f"- {txt}" for txt in dream_texts)
    prompt = DRIFT_USER_TEMPLATE.format(current_state=current_block, dream_block=dream_block)

    c = client or ChatClient.auto()
    try:
        result = c.chat_structured(
            system=DRIFT_SYSTEM,
            user=prompt,
            schema=DreamDrifts,
            schema_name="DreamDrifts",
            reasoning_effort="low",
            verbosity="low",
        )
    except Exception as e:
        logger.warning("apply_dream_drift: LLM call failed: %s", e)
        return []

    applied: list[dict] = []
    for d in result.deltas:
        if d.trait not in KNOWN_TRAITS:
            continue
        capped = max(-MAX_DELTA, min(MAX_DELTA, float(d.delta)))
        if capped == 0.0:
            continue
        reason = (d.reason or "").strip() or "dream-thought drift"
        if "dream" not in reason.lower():
            reason = f"dream: {reason}"
        record = {"trait": d.trait, "delta": capped, "reason": reason}
        if persist:
            try:
                _persist_delta(
                    user_id=user_id,
                    trait=d.trait,
                    delta=capped,
                    reason=reason,
                    current=current_state.get(d.trait, DEFAULT_TRAIT_VALUE),
                )
            except Exception as e:
                logger.warning("apply_dream_drift: persist failed for %s: %s", d.trait, e)
                continue
        applied.append(record)

    logger.info(
        "apply_dream_drift: applied %d delta(s) from %d dream-thought(s)",
        len(applied),
        len(dream_texts),
    )
    return applied


def _fetch_observations(*, user_id: str, obs_ids: list[str]) -> list[str]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT observation
            FROM regis_observations
            WHERE user_id = %s AND id = ANY(%s::uuid[])
            ORDER BY observed_at ASC
            """,
            (user_id, obs_ids),
        )
        rows = cur.fetchall()
    return [r[0] for r in rows if r[0]]


def _fetch_current_traits(*, user_id: str) -> dict[str, float]:
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
    state = {t: DEFAULT_TRAIT_VALUE for t in KNOWN_TRAITS}
    for trait_name, value in rows:
        if trait_name in KNOWN_TRAITS:
            state[trait_name] = float(value)
    return state


def _persist_delta(
    *,
    user_id: str,
    trait: str,
    delta: float,
    reason: str,
    current: float,
) -> None:
    new_value = max(TRAIT_FLOOR, min(TRAIT_CEIL, current + delta))
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regis_trait_history
              (user_id, trait_name, value, delta, reason)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, trait, new_value, delta, reason),
        )
        conn.commit()


def _main() -> int:
    ap = argparse.ArgumentParser(description="Apply dream-driven trait drift for a user.")
    ap.add_argument("--user-id", default=_paths.DEFAULT_USER_ID)
    ap.add_argument(
        "--obs-id",
        action="append",
        default=[],
        help="Dream-observation UUID (source='dreaming'). Repeat for multiple.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.obs_id:
        print("No --obs-id provided; nothing to do.", file=sys.stderr)
        return 2

    deltas = apply_dream_drift(
        user_id=args.user_id,
        dream_obs_ids=args.obs_id,
        persist=not args.dry_run,
    )
    print(f"Applied {len(deltas)} delta(s):")
    for d in deltas:
        print(f"  {d['trait']:>12s}  {d['delta']:+.3f}  — {d['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
