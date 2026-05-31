"""L3 calibration enrichment — attach cold-start arbitration (#4) to an AxisEstimate.

The single seam L3 uses to consume arbitration.get_calibration: it stamps the
honest calibration_state + w_personal onto a fused estimate's value, and blends a
scalar toward the population pole ONLY when that pole is genuinely seeded
(`population_seeded`). cold_start_profiles is empty at v1, and its fallback
population_value is a 0.0 placeholder — blending toward it would corrupt a real
reading, so the numeric blend is gated. Pure; the DB read happens in the caller.
"""
from __future__ import annotations

import copy
from typing import Any

from arbitration.blend import BlendResult
from fusion.belief_state import AxisEstimate

# A v1 scalar axis exposes its number under one of these keys (e.g. arousal_inferred
# -> "arousal"). Categorical axes carry none and are left numerically untouched.
_SCALAR_KEYS = ("arousal", "valence", "value", "score", "load")


def _is_offline(est: AxisEstimate) -> bool:
    return est.confidence is None or est.value.get("category") == "offline"


def _scalar_key(value: dict[str, Any]) -> str | None:
    for k in _SCALAR_KEYS:
        v = value.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return k
    return None


def apply_calibration(est: AxisEstimate, calib: BlendResult) -> AxisEstimate:
    """Return an enriched copy of `est` carrying calibration metadata (+ optional blend).

    OFFLINE sentinels are returned untouched — never fabricate calibration on a
    degraded 'no answer'. The original estimate is never mutated.
    """
    if _is_offline(est):
        return est

    new_value = copy.deepcopy(est.value)
    new_value["calibration_state"] = calib.calibration_state.value
    new_value["w_personal"] = round(calib.w_personal, 3)

    key = _scalar_key(new_value)
    if calib.population_seeded and calib.w_personal < 1.0 and key is not None:
        personal = float(new_value[key])
        blended = calib.w_personal * personal + calib.w_population * calib.population_value
        new_value[key] = round(blended, 3)
        new_value["blended"] = True

    return AxisEstimate(
        axis=est.axis,
        value=new_value,
        timestamp=est.timestamp,
        confidence=est.confidence,
        source=est.source,
        meta_context=est.meta_context,
        i_model_id=est.i_model_id,
        fresh_for_seconds=est.fresh_for_seconds,
    )
