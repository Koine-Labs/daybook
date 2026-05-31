"""Pure adapter: summarize frozen-contract LabelRecords into per-tier evidence mass.

No DB, no LLM. Groups via the frozen labels.group_by_source, applies per-tier
exponential half-life decay + producer confidence + saturating tier-trust so that
high-volume low-trust streams cannot swamp a high-trust source (#17 anti-swamp).
Population-pole rows are excluded — they are the population side, not personal
evidence.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelRecord, LabelSource, group_by_source

from .constants import POPULATION_TIERS, ProfileParams


@dataclass(frozen=True)
class TierEvidence:
    """Per-tier effective personal-evidence mass after decay + confidence + trust."""

    tier: str
    count: int
    effective_mass: float
    last_observed_at: datetime | None


def _decay(delta_s: float, halflife_s: float) -> float:
    """Exponential half-life recency weight in (0, 1]; future/equal timestamps -> 1.0."""
    if delta_s <= 0.0 or halflife_s <= 0.0:
        return 1.0
    return math.pow(0.5, delta_s / halflife_s)


def summarize(
    label_rows: Sequence[LabelRecord],
    profile: ProfileParams,
    *,
    now: datetime,
) -> dict[str, TierEvidence]:
    """Group personal-tier LabelRecords by source and compute saturating evidence mass.

    Population-pole tiers (literature/demographic/llm-bootstrap) are skipped: they
    are the population pole, not personal evidence.
    """
    grouped = group_by_source(label_rows)
    out: dict[str, TierEvidence] = {}
    for source, recs in grouped.items():
        if not isinstance(source, LabelSource):  # defensive: ledger yields enum members
            source = LabelSource(source)
        if source in POPULATION_TIERS:
            continue
        tier = source.value
        halflife = profile.halflife_for(tier)
        raw_mass = 0.0
        last_seen: datetime | None = None
        for rec in recs:
            delta_s = (now - rec.observed_at).total_seconds()
            conf = rec.confidence if rec.confidence is not None else 0.0
            raw_mass += _decay(delta_s, halflife) * float(conf)
            if last_seen is None or rec.observed_at > last_seen:
                last_seen = rec.observed_at
        # Saturate the pre-trust summed mass, THEN apply tier trust. This is the
        # anti-swamp bound: volume saturates before trust scales it.
        saturated = min(raw_mass, profile.saturation_for(tier))
        effective = profile.trust_for(tier) * saturated
        out[tier] = TierEvidence(
            tier=tier,
            count=len(recs),
            effective_mass=effective,
            last_observed_at=last_seen,
        )
    return out
