"""Canonical axis names — join self-report labels to their inferred counterpart (#5)."""
from __future__ import annotations

# A declared axis maps to its inferred-axis counterpart so a self_report label
# lands under the SAME axis name the inferred pipeline writes — making the
# calibration join real. Conservative on purpose: only the one clear same-concept
# pair. fatigue/focus/valence/stress/mood have no inferred counterpart yet, so
# they keep their own names (honest).
DECLARED_TO_CANONICAL: dict[str, str] = {
    "arousal": "arousal_inferred",
}


def canonical_axis(name: str) -> str:
    """Map a declared axis to its canonical (inferred) name, else return it unchanged."""
    return DECLARED_TO_CANONICAL.get(name, name)
