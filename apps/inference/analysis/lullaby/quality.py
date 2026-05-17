"""
Data quality assessment for Lullaby sleep sessions.

Reports on sample counts, gaps, coverage, and connectivity reliability
to help identify data collection issues before analysis.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lullaby.loader import SleepSessionData


def assess_quality(session: SleepSessionData) -> dict:
    """Assess data quality for a sleep session.

    Checks:
    - Total duration and sample counts per stream
    - Expected vs actual sample counts (based on known sensor rates)
    - Gap analysis: longest gap per stream, total missing time
    - Sample rate validation
    - Watch connectivity metrics
    - Battery drain
    - HealthKit sleep stage coverage

    Args:
        session: Loaded sleep session data.

    Returns:
        Dictionary with quality metrics organized by category.
    """
    total_seconds = session.duration_hours * 3600
    report: dict = {
        "overview": {},
        "heart_rate": {},
        "hrv": {},
        "accelerometer": {},
        "sonar": {},
        "audio": {},
        "sleep_stages": {},
        "connectivity": {},
        "battery": {},
    }

    # --- Overview ---
    report["overview"] = {
        "session_id": session.session_id,
        "duration_hours": round(session.duration_hours, 2),
        "start_time": str(session.start_time),
        "end_time": str(session.end_time),
    }

    # --- Heart Rate ---
    hr = session.heart_rate
    expected_hr = int(total_seconds / 5)  # ~5 second intervals
    report["heart_rate"] = _stream_quality(
        hr, "timestamp", expected_hr, "Heart Rate",
        expected_interval=5.0,
    )

    # --- HRV ---
    hrv = session.hrv
    expected_hrv = int(total_seconds / 300)  # ~5 minute intervals
    report["hrv"] = _stream_quality(
        hrv, "timestamp", expected_hrv, "HRV",
        expected_interval=300.0,
    )

    # --- Accelerometer ---
    accel = session.accelerometer
    expected_accel = int(total_seconds * 10)  # 10 Hz
    report["accelerometer"] = _stream_quality(
        accel, "timestamp", expected_accel, "Accelerometer",
        expected_interval=0.1,
    )

    # --- Sonar ---
    sonar = session.sonar
    expected_sonar = int(total_seconds / 2)  # ~2 second intervals
    report["sonar"] = _stream_quality(
        sonar, "timestamp", expected_sonar, "Sonar",
        expected_interval=2.0,
    )
    # Additional: check how many sonar samples have valid breathing rate
    if not sonar.empty and "breathing_rate" in sonar.columns:
        valid_br = sonar["breathing_rate"].notna().sum()
        report["sonar"]["valid_breathing_rate_count"] = int(valid_br)
        report["sonar"]["valid_breathing_rate_pct"] = round(100 * valid_br / len(sonar), 1)

    # --- Audio ---
    audio = session.audio
    expected_audio = int(total_seconds / 5)  # ~5 second intervals
    report["audio"] = _stream_quality(
        audio, "timestamp", expected_audio, "Audio",
        expected_interval=5.0,
    )
    # Classification distribution
    if not audio.empty and "classification" in audio.columns:
        dist = audio["classification"].value_counts().to_dict()
        report["audio"]["classification_distribution"] = dist

    # --- Sleep Stages ---
    stages = session.sleep_stages
    if not stages.empty:
        total_stage_time = (stages["end"] - stages["start"]).sum()
        coverage_pct = 100 * total_stage_time / total_seconds if total_seconds > 0 else 0

        stage_dist = {}
        for stage_name in stages["stage"].unique():
            mask = stages["stage"] == stage_name
            stage_dist[stage_name] = round((stages.loc[mask, "end"] - stages.loc[mask, "start"]).sum() / 3600, 2)

        report["sleep_stages"] = {
            "count": len(stages),
            "coverage_pct": round(coverage_pct, 1),
            "total_labeled_hours": round(total_stage_time / 3600, 2),
            "stage_hours": stage_dist,
        }
    else:
        report["sleep_stages"] = {
            "count": 0,
            "coverage_pct": 0,
            "total_labeled_hours": 0,
            "stage_hours": {},
            "warning": "No sleep stages available — sync from HealthKit",
        }

    # --- Connectivity ---
    meta = session.metadata
    report["connectivity"] = {
        "packets_received": meta.get("totalPacketsReceived", 0),
        "packets_expected": meta.get("totalPacketsExpected"),
        "drop_count": meta.get("connectivityDropCount", 0),
    }
    expected = meta.get("totalPacketsExpected")
    received = meta.get("totalPacketsReceived", 0)
    if expected and expected > 0:
        report["connectivity"]["delivery_pct"] = round(100 * received / expected, 1)

    # --- Battery ---
    report["battery"] = {
        "phone_start": meta.get("phoneBatteryAtStart"),
        "phone_end": meta.get("phoneBatteryAtEnd"),
        "watch_start": meta.get("watchBatteryAtStart"),
        "watch_end": meta.get("watchBatteryAtEnd"),
    }
    phone_start = meta.get("phoneBatteryAtStart")
    phone_end = meta.get("phoneBatteryAtEnd")
    if phone_start is not None and phone_end is not None:
        report["battery"]["phone_drain_pct"] = round(100 * (phone_start - phone_end), 1)
    watch_start = meta.get("watchBatteryAtStart")
    watch_end = meta.get("watchBatteryAtEnd")
    if watch_start is not None and watch_end is not None:
        report["battery"]["watch_drain_pct"] = round(100 * (watch_start - watch_end), 1)

    return report


def print_quality_report(session: SleepSessionData) -> None:
    """Pretty-print a data quality report to console.

    Args:
        session: Loaded sleep session data.
    """
    report = assess_quality(session)

    print("=" * 60)
    print("  LULLABY DATA QUALITY REPORT")
    print("=" * 60)

    # Overview
    ov = report["overview"]
    print(f"\n  Session:  {ov['session_id'][:8]}...")
    print(f"  Duration: {ov['duration_hours']} hours")
    print(f"  Start:    {ov['start_time']}")
    print(f"  End:      {ov['end_time']}")

    # Sensor streams
    print(f"\n{'─' * 60}")
    print("  SENSOR STREAMS")
    print(f"{'─' * 60}")

    for stream_key in ["heart_rate", "hrv", "accelerometer", "sonar", "audio"]:
        s = report[stream_key]
        name = s.get("name", stream_key)
        actual = s.get("actual_count", 0)
        expected = s.get("expected_count", 0)
        coverage = s.get("coverage_pct", 0)
        gap = s.get("max_gap_seconds", 0)

        status = "✓" if coverage >= 90 else "⚠" if coverage >= 50 else "✗"
        print(f"\n  {status} {name}")
        print(f"    Samples: {actual:,} / {expected:,} expected ({coverage}%)")
        if gap > 0:
            print(f"    Max gap: {gap:.1f}s | Mean interval: {s.get('mean_interval', 0):.2f}s")
        if "valid_breathing_rate_pct" in s:
            print(f"    Valid breathing rate: {s['valid_breathing_rate_pct']}%")

    # Sleep stages
    print(f"\n{'─' * 60}")
    print("  SLEEP STAGES")
    print(f"{'─' * 60}")
    ss = report["sleep_stages"]
    if ss.get("warning"):
        print(f"\n  ⚠ {ss['warning']}")
    else:
        print(f"\n  Coverage: {ss['coverage_pct']}% of session")
        print(f"  Intervals: {ss['count']}")
        for stage, hours in ss.get("stage_hours", {}).items():
            print(f"    {stage:>12}: {hours:.2f} hours")

    # Connectivity
    print(f"\n{'─' * 60}")
    print("  CONNECTIVITY")
    print(f"{'─' * 60}")
    conn = report["connectivity"]
    print(f"\n  Packets: {conn['packets_received']} received", end="")
    if conn.get("packets_expected"):
        print(f" / {conn['packets_expected']} expected ({conn.get('delivery_pct', '?')}%)")
    else:
        print()
    print(f"  Drops: {conn['drop_count']}")

    # Battery
    print(f"\n{'─' * 60}")
    print("  BATTERY")
    print(f"{'─' * 60}")
    bat = report["battery"]
    if bat.get("phone_drain_pct") is not None:
        print(f"\n  Phone: {_pct(bat['phone_start'])} → {_pct(bat['phone_end'])} "
              f"(drain: {bat['phone_drain_pct']}%)")
    if bat.get("watch_drain_pct") is not None:
        print(f"  Watch: {_pct(bat['watch_start'])} → {_pct(bat['watch_end'])} "
              f"(drain: {bat['watch_drain_pct']}%)")

    print(f"\n{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _stream_quality(
    df: pd.DataFrame,
    timestamp_col: str,
    expected_count: int,
    name: str,
    expected_interval: float,
) -> dict:
    """Compute quality metrics for a single sensor stream."""
    result = {
        "name": name,
        "actual_count": len(df),
        "expected_count": expected_count,
        "coverage_pct": round(100 * len(df) / expected_count, 1) if expected_count > 0 else 0,
    }

    if len(df) >= 2:
        intervals = df[timestamp_col].diff().dropna()
        result["mean_interval"] = round(float(intervals.mean()), 3)
        result["std_interval"] = round(float(intervals.std()), 3)
        result["min_interval"] = round(float(intervals.min()), 3)
        result["max_gap_seconds"] = round(float(intervals.max()), 1)

        # Count gaps > 2x expected interval
        gap_threshold = expected_interval * 2
        gaps = intervals[intervals > gap_threshold]
        result["gap_count"] = int(len(gaps))
        result["total_gap_seconds"] = round(float(gaps.sum()), 1) if len(gaps) > 0 else 0
    else:
        result["mean_interval"] = 0
        result["max_gap_seconds"] = 0
        result["gap_count"] = 0

    return result


def _pct(value: float | None) -> str:
    """Format a 0-1 battery level as percentage string."""
    if value is None:
        return "?"
    return f"{value * 100:.0f}%"
