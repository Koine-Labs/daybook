"""Pure rule evaluation — the unit-test heart. No DB, no LLM, no network.

`evaluate_rule` returns the predicted claim iff the rule's condition AND its
context_gate (commitment #14) are satisfied by the supplied features/context,
else None. Directional operators (increase/decrease) read a signed delta feature
named `<feature>_delta`; threshold operators read the level feature directly.
"""
from __future__ import annotations

from typing import Mapping

from .models import Context, Rule, RuleClaim


def _context_satisfied(rule: Rule, context: Context | None) -> bool:
    gate = rule.context_gate or {}
    if not gate:
        return True
    if context is None:
        return False
    want_meta = gate.get("meta_context")
    if want_meta is not None and context.meta_context != want_meta:
        return False
    want_sub = gate.get("sub_context")
    if want_sub is not None and context.sub_context != want_sub:
        return False
    return True


def _condition_satisfied(rule: Rule, features: Mapping[str, float]) -> bool:
    op = rule.operator
    if op in {"increase", "decrease"}:
        delta_key = f"{rule.feature}_delta"
        if delta_key not in features:
            return False
        delta = features[delta_key]
        return delta > 0 if op == "increase" else delta < 0
    if rule.feature not in features:
        return False
    val = features[rule.feature]
    if op == "gt":
        return val > rule.threshold  # type: ignore[operator]
    if op == "lt":
        return val < rule.threshold  # type: ignore[operator]
    if op == "ratio_gt":
        return val > rule.threshold  # type: ignore[operator]
    if op == "in_band":
        lo, hi = rule.threshold  # type: ignore[misc]
        return lo <= val <= hi
    return False


def evaluate_rule(
    rule: Rule, features: Mapping[str, float], context: Context | None = None
) -> RuleClaim | None:
    """Pure: predicted claim iff condition AND context_gate hold, else None."""
    if not _context_satisfied(rule, context):
        return None
    if not _condition_satisfied(rule, features):
        return None
    return rule.claim
