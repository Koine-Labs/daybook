"""Post-session day-summary aggregator — belief history -> regis_observations.

The D8 replacement: nothing wrote regis_observations post-rebuild, so Regis
perceived but accumulated no memory. summarize_session folds one session's
per-axis estimates (dominant sub-contexts, notable company, numeric axis ranges)
into 1-3 heuristic observation rows — NO LLM calls. Evidence density maps to the
`weight` column (regis_observations has no confidence column); i_model_id stays
NULL (#1); the discriminator rides in context JSONB (no kind column). Persistence
goes through an injectable conn seam so tests run DB-free with fakes.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

INF_DIR = Path(__file__).resolve().parent.parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from ..belief_state import AxisEstimate

SOURCE = "fusion.observers.day_summary.v1"

# Reads needed for full weight 1.0 — a rough "well-evidenced session" yardstick.
DENSITY_FULL_READS = 20
MIN_WEIGHT = 0.1

_NUMERIC_AXES = {
    "arousal_inferred": "arousal",
    "cognitive_load": "load",
    "affect_prosody": "proxy_arousal",
}

_INSERT_SQL = """
    INSERT INTO regis_observations
        (user_id, observed_at, observation, context, weight, source, i_model_id)
    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
    RETURNING id
"""

_SELECT_SQL = """
    SELECT axis, value, confidence, source, timestamp, meta_context, i_model_id
    FROM user_state_estimate
    WHERE user_id = %s
      AND timestamp >= %s
      AND timestamp <= %s
    ORDER BY timestamp ASC
"""


@dataclass(frozen=True)
class SessionWindow:
    """One session's tz-aware [start, end] bounds."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("SessionWindow bounds must be tz-aware UTC")
        if self.end <= self.start:
            raise ValueError("SessionWindow.end must be after start")


SessionReader = Callable[[str, SessionWindow], list[AxisEstimate]]


def read_session_estimates(
    user_id: str, window: SessionWindow, *, conn: Any | None = None
) -> list[AxisEstimate]:
    """All user_state_estimate rows in the window, oldest first."""
    if conn is None:
        with get_conn() as live:
            return _read(live, user_id, window)
    return _read(conn, user_id, window)


def _read(conn: Any, user_id: str, window: SessionWindow) -> list[AxisEstimate]:
    with conn.cursor() as cur:
        cur.execute(_SELECT_SQL, (user_id, window.start, window.end))
        rows = cur.fetchall()
    out: list[AxisEstimate] = []
    for axis, value, confidence, source, ts, meta_context, i_model_id in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out.append(
            AxisEstimate(
                axis=axis,
                value=value if isinstance(value, dict) else {"value": value},
                timestamp=ts,
                confidence=confidence,
                source=source or "unknown",
                meta_context=meta_context,
                i_model_id=str(i_model_id) if i_model_id is not None else None,
            )
        )
    return out


def summarize_session(
    reader: SessionReader, user_id: str, window: SessionWindow, *, conn: Any | None = None
) -> list[str]:
    """Aggregate one session into 0-3 regis_observations rows; return inserted ids."""
    estimates = [e for e in reader(user_id, window) if _usable(e)]
    rows = build_observations(estimates)
    if not rows:
        return []
    if conn is None:
        with get_conn() as live:
            return _insert(live, user_id, window, rows)
    return _insert(conn, user_id, window, rows)


def build_observations(estimates: list[AxisEstimate]) -> list[dict[str, Any]]:
    """Heuristic v1 aggregation: up to one observation per builder, NO LLM."""
    candidates = (
        _context_observation(estimates),
        _company_observation(estimates),
        _ranges_observation(estimates),
    )
    return [c for c in candidates if c is not None]


def _usable(est: AxisEstimate) -> bool:
    """Drop the L3 OFFLINE sentinels — 'no answer' is not evidence."""
    if est.source.endswith(".offline"):
        return False
    return est.value.get("category") != "offline"


def _weight(reads: int) -> float:
    return round(min(1.0, max(MIN_WEIGHT, reads / DENSITY_FULL_READS)), 2)


def _by_axis(estimates: list[AxisEstimate], axis: str) -> list[AxisEstimate]:
    return [e for e in estimates if e.axis == axis]


def _context_observation(estimates: list[AxisEstimate]) -> dict[str, Any] | None:
    categories = [
        str(e.value["category"])
        for e in _by_axis(estimates, "meta_context")
        if e.value.get("category")
    ]
    if not categories:
        return None
    counts = Counter(categories)
    dominant, dominant_n = counts.most_common(1)[0]
    shifts = sum(1 for a, b in zip(categories, categories[1:]) if a != b)
    share = round(100 * dominant_n / len(categories))
    return {
        "observation": (
            f"Session context: mostly {dominant} "
            f"({share}% of {len(categories)} reads; {shifts} shifts)."
        ),
        "context": {
            "kind": "session_context",
            "dominant": dominant,
            "share_pct": share,
            "reads": len(categories),
            "shifts": shifts,
            "counts": dict(counts),
        },
        "weight": _weight(len(categories)),
    }


def _company_observation(estimates: list[AxisEstimate]) -> dict[str, Any] | None:
    social = _by_axis(estimates, "audio_social_context")
    visual = _by_axis(estimates, "visual_context")
    with_other = sum(1 for e in social if e.value.get("category") == "with_other")
    people_frames = sum(1 for e in visual if e.value.get("people_present"))
    if with_other == 0 and people_frames == 0:
        return None
    settings = Counter(
        str(e.value["setting"])
        for e in visual
        if e.value.get("setting") and e.value.get("setting") != "unknown"
    )
    parts: list[str] = []
    if social:
        parts.append(f"voices of others in {with_other} of {len(social)} audio reads")
    if visual:
        bit = f"people visible in {people_frames} of {len(visual)} frames"
        if settings:
            bit += f", mostly around '{settings.most_common(1)[0][0]}'"
        parts.append(bit)
    context: dict[str, Any] = {
        "kind": "session_company",
        "with_other_reads": with_other,
        "social_reads": len(social),
        "people_frames": people_frames,
        "visual_frames": len(visual),
    }
    if settings:
        context["top_setting"] = settings.most_common(1)[0][0]
    return {
        "observation": "Company: " + "; ".join(parts) + ".",
        "context": context,
        "weight": _weight(len(social) + len(visual)),
    }


def _ranges_observation(estimates: list[AxisEstimate]) -> dict[str, Any] | None:
    ranges: dict[str, dict[str, Any]] = {}
    for axis, key in _NUMERIC_AXES.items():
        values = [
            float(e.value[key])
            for e in _by_axis(estimates, axis)
            if isinstance(e.value.get(key), (int, float))
        ]
        if values:
            ranges[axis] = {"min": min(values), "max": max(values), "reads": len(values)}
    if not ranges:
        return None
    parts = [
        f"{axis} {r['min']:.2f}-{r['max']:.2f} over {r['reads']} reads"
        for axis, r in sorted(ranges.items())
    ]
    return {
        "observation": "Axis ranges: " + "; ".join(parts) + ".",
        "context": {"kind": "session_axis_ranges", "ranges": ranges},
        "weight": _weight(sum(r["reads"] for r in ranges.values())),
    }


def _insert(
    conn: Any, user_id: str, window: SessionWindow, rows: list[dict[str, Any]]
) -> list[str]:
    bounds = {"start": window.start.isoformat(), "end": window.end.isoformat()}
    ids: list[str] = []
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                _INSERT_SQL,
                (
                    user_id,
                    window.end,
                    row["observation"],
                    json.dumps({**row["context"], "window": bounds}),
                    row["weight"],
                    SOURCE,
                    None,
                ),
            )
            ids.append(str(cur.fetchone()[0]))
    conn.commit()
    return ids
