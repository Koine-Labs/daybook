"""Candidate source-set enumeration (power-set with cap, or greedy forward path).

`dropped` always carries (set, reason) for every set the cap excluded so the run
manifest can report it — A4 (no silent caps).
"""
from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import AblationConfig

SourceSet = tuple[str, ...]  # canonical sorted tuple of source tokens

_CAPPED = "capped_by_max_set_size"


def canonical(sources: list[str]) -> SourceSet:
    """Normalize tokens (lowercase) and return the canonical sorted, deduped tuple."""
    return tuple(sorted({s.strip().lower() for s in sources if s and s.strip()}))


def _all_subsets(tokens: SourceSet) -> list[SourceSet]:
    out: list[SourceSet] = []
    for size in range(1, len(tokens) + 1):
        for combo in combinations(tokens, size):
            out.append(combo)
    return out


def _greedy_path(tokens: SourceSet, max_size: int) -> list[SourceSet]:
    """Deterministic forward-selection chain: all singletons, then grow by adding
    the next token in canonical order, up to max_size. Linear, not exponential."""
    cands: list[SourceSet] = [(t,) for t in tokens]
    grown: SourceSet = (tokens[0],) if tokens else ()
    for t in tokens[1:]:
        if len(grown) >= max_size:
            break
        grown = canonical(list(grown) + [t])
        if grown not in cands:
            cands.append(grown)
    # dedup preserving order
    seen: set[SourceSet] = set()
    uniq: list[SourceSet] = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def enumerate_candidates(
    available_sources: list[str], cfg: "AblationConfig"
) -> tuple[list[SourceSet], list[tuple[SourceSet, str]]]:
    """Return (candidates, dropped). Candidates honor max_set_size; dropped lists
    every excluded set with its reason (A4). Greedy mode returns a forward-
    selection path instead of the full power-set when len(available) is large."""
    tokens = canonical(available_sources)
    if not tokens:
        return [], []

    full = _all_subsets(tokens)
    in_size = [s for s in full if len(s) <= cfg.max_set_size]
    over_size = [s for s in full if len(s) > cfg.max_set_size]
    dropped: list[tuple[SourceSet, str]] = [(s, _CAPPED) for s in over_size]

    if cfg.greedy:
        cands = _greedy_path(tokens, cfg.max_set_size)
        # Anything within the cap that greedy skipped is NOT dropped-by-cap; it is
        # simply not on the greedy path. Report it honestly as a distinct reason.
        skipped = [s for s in in_size if s not in set(cands)]
        dropped.extend((s, "not_on_greedy_path") for s in skipped)
        return cands, dropped

    return in_size, dropped
