"""DB-free + LLM-free smoke test for cold-start arbitration (#4).

Runs the full PURE path on fixtures (a fake ledger reader) and prints a
human-readable trace of weight + calibration_state for a cold axis vs a
calibrated axis. No Neon, no network. Run: python -m arbitration.smoke_test
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelRecord, LabelSource

from arbitration import blend, default_profile, summarize

NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)


def _rec(source: LabelSource, *, age_days: float = 0.0, confidence: float = 1.0) -> LabelRecord:
    return LabelRecord(
        user_id="smoke",
        axis="arousal",
        value=0.5,
        source=source,
        observed_at=NOW - timedelta(days=age_days),
        confidence=confidence,
    )


def _trace(label: str, rows: list[LabelRecord]) -> None:
    profile = default_profile("arousal")
    evidence = summarize(rows, profile, now=NOW)
    result = blend("arousal", evidence, profile, population_value=0.4, population_variance=0.6, now=NOW)
    print(f"\n[{label}]  n_rows={len(rows)}")
    for tier, te in result.evidence_by_tier.items():
        print(f"   tier={tier:18s} count={te.count:5d} mass={te.effective_mass:.4f}")
    print(f"   e_personal={result.e_personal:.4f}")
    print(f"   w_personal={result.w_personal:.4f}  w_population={result.w_population:.4f}")
    print(f"   calibration_state={result.calibration_state.value}")


def main() -> None:
    print("=== cold-start arbitration smoke (pure path, DB-free) ===")
    _trace("cold axis (no personal evidence)", [])
    _trace(
        "calibrating (a few self-reports)",
        [_rec(LabelSource.SELF_REPORT, age_days=d) for d in (0, 1, 3)],
    )
    _trace(
        "calibrated (many fresh self-reports + outcomes)",
        [_rec(LabelSource.SELF_REPORT) for _ in range(8)]
        + [_rec(LabelSource.OBSERVED_OUTCOME) for _ in range(4)],
    )
    _trace(
        "anti-swamp: 500 sensor (heuristic) labels alone",
        [_rec(LabelSource.HEURISTIC) for _ in range(500)],
    )
    print("\nOK — pure arbitration path ran without a DB.")


if __name__ == "__main__":
    main()
