#!/usr/bin/env python3
"""Incremental Apple Health XML export sync into sensor_readings.

Reads an Apple Health export XML (typically ~/Library/Mobile Documents/... or
~/Downloads/export.xml) and inserts only records newer than the last sync
cutoff. Writes sleep stages and HR (extend later for HRV, SpO2, resp).

Usage:
    bin/sync_hk_export.py /path/to/export.xml
    bin/sync_hk_export.py /path/to/export.xml --since 2026-05-20
    bin/sync_hk_export.py /path/to/export.xml --dry-run

State file: ~/.daybook/sync_state.json
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# Path bootstrap so we can `from db import get_conn`.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "inference"))

from db import get_conn  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
STATE_PATH = Path.home() / ".daybook" / "sync_state.json"

# HealthKit type identifiers we care about for Week 1.
# Extend later for HRV (HKQuantityTypeIdentifierHeartRateVariabilitySDNN),
# SpO2, respiratory rate, etc.
TYPE_HR = "HKQuantityTypeIdentifierHeartRate"
TYPE_SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"

# Apple sleep category values → our internal labels.
SLEEP_STAGE_MAP = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAsleep": "asleep_legacy",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
}


def load_state() -> dict[str, str]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict[str, str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def parse_hk_datetime(s: str) -> datetime:
    """Apple Health timestamps look like '2026-05-25 23:14:33 -0700'."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z").astimezone(timezone.utc)


def iter_records(xml_path: Path):
    """Stream-iterate <Record> elements without loading the whole tree."""
    for event, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag == "Record":
            yield elem.attrib
            elem.clear()


def sync(
    *,
    xml_path: Path,
    since: datetime | None = None,
    user_id: str = DEFAULT_USER_ID,
    dry_run: bool = False,
) -> dict[str, int]:
    state = load_state()
    state_key = f"{user_id}:last_synced_at"
    cutoff: datetime | None = since
    if cutoff is None and state_key in state:
        cutoff = datetime.fromisoformat(state[state_key])

    print(f"Sync starting. cutoff={cutoff} dry_run={dry_run}", flush=True)

    new_rows: list[tuple] = []
    counters = {"hr": 0, "sleep": 0, "skipped_before_cutoff": 0, "skipped_other_type": 0}
    latest_ts_seen: datetime | None = None

    for rec in iter_records(xml_path):
        rec_type = rec.get("type")
        start = parse_hk_datetime(rec["startDate"])
        end = parse_hk_datetime(rec["endDate"]) if rec.get("endDate") else start

        if latest_ts_seen is None or end > latest_ts_seen:
            latest_ts_seen = end

        if cutoff and end <= cutoff:
            counters["skipped_before_cutoff"] += 1
            continue

        source_name = rec.get("sourceName", "")
        if rec_type == TYPE_HR:
            new_rows.append(
                (
                    user_id,
                    "apple_health",
                    "apple_health_hr",
                    start,
                    json.dumps({"bpm": float(rec["value"]), "source": source_name}),
                )
            )
            counters["hr"] += 1
        elif rec_type == TYPE_SLEEP:
            stage = SLEEP_STAGE_MAP.get(rec.get("value", ""), "unknown")
            new_rows.append(
                (
                    user_id,
                    "apple_health",
                    "apple_health_sleep_stage",
                    start,
                    json.dumps({
                        "stage": stage,
                        "end": end.isoformat(),
                        "source": source_name,
                        "duration_s": int((end - start).total_seconds()),
                    }),
                )
            )
            counters["sleep"] += 1
        else:
            counters["skipped_other_type"] += 1

    print(f"Parsed {len(new_rows)} new rows. Counters: {counters}", flush=True)

    if dry_run:
        print("Dry run — not inserting.", flush=True)
        return counters

    if not new_rows:
        print("Nothing to insert.", flush=True)
        return counters

    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO sensor_readings (user_id, source, kind, recorded_at, payload)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            new_rows,
        )
        conn.commit()

    if latest_ts_seen is not None:
        state[state_key] = latest_ts_seen.isoformat()
        save_state(state)
        print(f"Cutoff advanced to {latest_ts_seen.isoformat()}", flush=True)

    return counters


def _cli() -> int:
    p = argparse.ArgumentParser(prog="sync_hk_export", description="Incremental Apple Health → sensor_readings sync.")
    p.add_argument("xml_path", type=Path, help="Path to Apple Health export.xml")
    p.add_argument("--since", type=str, default=None, help="ISO timestamp; only records strictly after this are imported.")
    p.add_argument("--user-id", type=str, default=DEFAULT_USER_ID)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not args.xml_path.exists():
        print(f"export.xml not found at {args.xml_path}", file=sys.stderr)
        return 1

    since = datetime.fromisoformat(args.since) if args.since else None
    counters = sync(xml_path=args.xml_path, since=since, user_id=args.user_id, dry_run=args.dry_run)
    print(f"DONE. {counters}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
