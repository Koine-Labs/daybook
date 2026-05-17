"""Parse an Apple Health XML export into Daybook's Postgres schema.

Usage:
    cd apps/inference
    ./.venv/bin/python parse_apple_health.py \\
        --xml "/path/to/apple_health_export/export.xml" \\
        --user-email aakash@example.com \\
        [--clear]

Streams the XML (does not load the full 1+ GB file into memory).

What gets imported into `sensor_readings`:
  - HKQuantityTypeIdentifierHeartRate                       -> kind = heart_rate
  - HKQuantityTypeIdentifierHeartRateVariabilitySDNN        -> kind = hrv
  - HKQuantityTypeIdentifierOxygenSaturation                -> kind = spo2
  - HKQuantityTypeIdentifierRespiratoryRate                 -> kind = respiratory_rate
  - HKQuantityTypeIdentifierAppleSleepingWristTemperature   -> kind = temperature
  - HKQuantityTypeIdentifierBodyTemperature                 -> kind = temperature

What gets imported into `sleep_sessions` + `sleep_stage_classifications`:
  - HKCategoryTypeIdentifierSleepAnalysis records, grouped into sessions
    when consecutive stage records are within 2 hours of each other.

What gets SKIPPED (intentionally, for v0):
  - Workouts and workout routes
  - Activity rings, calories, steps
  - ECG details
  - Mindfulness, audio exposure, environmental data, dietary records
  Skipped types are counted in `records_skipped_unknown_type` for visibility.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import psycopg

from db import get_conn

# ============================================================================
# TYPE MAPPINGS
# ============================================================================

# Apple HealthKit numeric-record types -> our sensor_readings.kind
QUANTITY_TYPE_TO_KIND: dict[str, str] = {
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",
    "HKQuantityTypeIdentifierOxygenSaturation": "spo2",
    "HKQuantityTypeIdentifierRespiratoryRate": "respiratory_rate",
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": "temperature",
    "HKQuantityTypeIdentifierBodyTemperature": "temperature",
}

# Apple HealthKit sleep value -> Daybook SleepStage
# `InBed` is intentionally skipped; not a "real" stage in our taxonomy.
SLEEP_VALUE_TO_STAGE: dict[str, str | None] = {
    "HKCategoryValueSleepAnalysisAsleepREM": "REM",
    "HKCategoryValueSleepAnalysisAsleepCore": "CORE",
    "HKCategoryValueSleepAnalysisAsleepDeep": "DEEP",
    "HKCategoryValueSleepAnalysisAwake": "AWAKE",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "UNKNOWN",
    "HKCategoryValueSleepAnalysisInBed": None,
}

# A gap longer than this between consecutive sleep records starts a new session.
SESSION_GAP = timedelta(hours=2)

# Batch insert size for sensor readings.
BATCH_SIZE = 1000

# Progress log frequency.
PROGRESS_EVERY = 100_000


# ============================================================================
# HELPERS
# ============================================================================


def parse_apple_date(s: str) -> datetime:
    """Apple's HealthKit date format: '2026-05-17 03:30:00 -0400'."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


def source_to_enum(source_name: str) -> str:
    """Map Apple's `sourceName` attribute to Daybook's SensorSource enum."""
    if "Watch" in source_name:
        return "APPLE_WATCH"
    if "iPhone" in source_name:
        return "IPHONE_SONAR"  # Imprecise; iPhone-sourced data lumped here
    return "MANUAL"


def build_payload(value: float, unit: str, kind: str) -> dict:
    """Build the sensor_readings.payload JSON appropriate to `kind`."""
    payload: dict = {"unit": unit}
    if kind == "heart_rate":
        payload["bpm"] = value
    elif kind == "hrv":
        # NOTE: Apple gives HRV as SDNN (in ms). Our type uses `rmssdMs` as
        # the canonical field name; semantically this is SDNN here. We
        # preserve `unit` so downstream consumers can disambiguate.
        payload["rmssdMs"] = value
    elif kind == "spo2":
        # Apple gives fraction (0.0-1.0); store as percent (0-100).
        payload["percent"] = value * 100 if value <= 1.0 else value
    elif kind == "respiratory_rate":
        payload["breathsPerMinute"] = value
    elif kind == "temperature":
        # Apple's sleeping wrist temp is a delta in °C.
        payload["celsiusDelta"] = value
    return payload


# ============================================================================
# DB OPERATIONS
# ============================================================================


def ensure_user(conn: psycopg.Connection, email: str, display_name: str) -> str:
    """Get-or-create the user record. Returns user_id (UUID string)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if row:
            return str(row[0])
        cur.execute(
            "INSERT INTO users (email, display_name) VALUES (%s, %s) RETURNING id",
            (email, display_name),
        )
        return str(cur.fetchone()[0])


def clear_user_data(conn: psycopg.Connection, user_id: str) -> None:
    """Wipe imported sensor + sleep data for a user. Use to re-import idempotently."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sensor_readings WHERE user_id = %s", (user_id,))
        cur.execute(
            "DELETE FROM sleep_stage_classifications "
            "WHERE session_id IN (SELECT id FROM sleep_sessions WHERE user_id = %s)",
            (user_id,),
        )
        cur.execute("DELETE FROM sleep_sessions WHERE user_id = %s", (user_id,))


def flush_sensor_batch(conn: psycopg.Connection, batch: list[tuple]) -> None:
    """Insert a batch of sensor readings."""
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO sensor_readings (user_id, recorded_at, source, kind, payload)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            batch,
        )


def group_sleep_into_sessions(
    records: list[dict],
) -> list[tuple[dict, list[dict]]]:
    """Group consecutive sleep records into sessions (separated by `SESSION_GAP`).

    Returns a list of (session_summary, stage_records) tuples.
    """
    if not records:
        return []

    records.sort(key=lambda r: r["start"])
    sessions: list[tuple[dict, list[dict]]] = []
    current_stages: list[dict] = [records[0]]

    for r in records[1:]:
        prev_end = current_stages[-1]["end"]
        gap = r["start"] - prev_end
        if gap > SESSION_GAP:
            session = {
                "start": current_stages[0]["start"],
                "end": current_stages[-1]["end"],
            }
            sessions.append((session, current_stages))
            current_stages = []
        current_stages.append(r)

    if current_stages:
        session = {
            "start": current_stages[0]["start"],
            "end": current_stages[-1]["end"],
        }
        sessions.append((session, current_stages))

    return sessions


def insert_sleep_sessions(
    conn: psycopg.Connection,
    user_id: str,
    grouped: list[tuple[dict, list[dict]]],
) -> int:
    """Insert sessions + classifications. Returns total stages inserted."""
    total_stages = 0
    with conn.cursor() as cur:
        for session, stages in grouped:
            duration = int((session["end"] - session["start"]).total_seconds())
            cur.execute(
                """
                INSERT INTO sleep_sessions
                    (user_id, started_at, ended_at, duration_seconds, sensor_sources)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, session["start"], session["end"], duration, ["APPLE_WATCH"]),
            )
            session_id = cur.fetchone()[0]
            stage_rows = [
                (session_id, s["start"], s["stage"], "APPLE_HEALTHKIT", 1.0)
                for s in stages
            ]
            cur.executemany(
                """
                INSERT INTO sleep_stage_classifications
                    (session_id, epoch_start_at, stage, source, confidence)
                VALUES (%s, %s, %s, %s, %s)
                """,
                stage_rows,
            )
            total_stages += len(stage_rows)
    return total_stages


# ============================================================================
# MAIN PARSE LOOP
# ============================================================================


def parse(xml_path: Path, user_id: str, *, clear: bool = False) -> dict:
    """Stream-parse the XML, insert into Postgres. Returns summary stats."""
    stats = {
        "records_seen": 0,
        "sensor_readings_inserted": 0,
        "sleep_records_collected": 0,
        "sleep_sessions_created": 0,
        "sleep_stages_inserted": 0,
        "records_skipped_unknown_type": 0,
        "records_skipped_parse_error": 0,
    }

    started_at = time.monotonic()

    with get_conn() as conn:
        if clear:
            print("  [clear] Wiping existing data for user...")
            clear_user_data(conn, user_id)
            conn.commit()
            print("  [clear] Done.")

        sensor_batch: list[tuple] = []
        sleep_records: list[dict] = []

        for _event, elem in ET.iterparse(xml_path, events=("end",)):
            if elem.tag != "Record":
                continue

            attrs = elem.attrib
            record_type = attrs.get("type", "")
            stats["records_seen"] += 1

            if stats["records_seen"] % PROGRESS_EVERY == 0:
                elapsed = time.monotonic() - started_at
                rate = stats["records_seen"] / elapsed if elapsed > 0 else 0
                print(
                    f"  ... seen {stats['records_seen']:>10,} records  "
                    f"({rate:>7,.0f} rec/s, {elapsed:.1f}s elapsed)"
                )

            # --- Sleep records: collect for session grouping ---
            if record_type == "HKCategoryTypeIdentifierSleepAnalysis":
                value = attrs.get("value", "")
                stage = SLEEP_VALUE_TO_STAGE.get(value)
                if stage is None:
                    elem.clear()
                    continue
                try:
                    sleep_records.append({
                        "start": parse_apple_date(attrs["startDate"]),
                        "end": parse_apple_date(attrs["endDate"]),
                        "stage": stage,
                    })
                    stats["sleep_records_collected"] += 1
                except (KeyError, ValueError):
                    stats["records_skipped_parse_error"] += 1
                elem.clear()
                continue

            # --- Numeric quantity records ---
            kind = QUANTITY_TYPE_TO_KIND.get(record_type)
            if kind is None:
                stats["records_skipped_unknown_type"] += 1
                elem.clear()
                continue

            try:
                recorded_at = parse_apple_date(attrs["startDate"])
                value = float(attrs["value"])
            except (KeyError, ValueError):
                stats["records_skipped_parse_error"] += 1
                elem.clear()
                continue

            payload = build_payload(value, attrs.get("unit", ""), kind)
            source = source_to_enum(attrs.get("sourceName", ""))

            sensor_batch.append(
                (user_id, recorded_at, source, kind, json.dumps(payload))
            )

            if len(sensor_batch) >= BATCH_SIZE:
                flush_sensor_batch(conn, sensor_batch)
                stats["sensor_readings_inserted"] += len(sensor_batch)
                sensor_batch.clear()

            elem.clear()

        # Final flush of sensor batch
        if sensor_batch:
            flush_sensor_batch(conn, sensor_batch)
            stats["sensor_readings_inserted"] += len(sensor_batch)

        # Group sleep records into sessions
        print(
            f"\n  Grouping {stats['sleep_records_collected']:,} sleep records "
            f"into sessions (gap threshold: {SESSION_GAP})..."
        )
        grouped = group_sleep_into_sessions(sleep_records)
        stats["sleep_sessions_created"] = len(grouped)
        print(f"  Inserting {len(grouped):,} sleep sessions + classifications...")
        stats["sleep_stages_inserted"] = insert_sleep_sessions(conn, user_id, grouped)

        conn.commit()

    return stats


# ============================================================================
# CLI
# ============================================================================


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--xml", type=Path, required=True, help="Path to Apple Health export.xml")
    p.add_argument("--user-email", type=str, required=True, help="Email for the user record")
    p.add_argument("--user-name", type=str, default="Daybook User", help="Display name")
    p.add_argument("--clear", action="store_true", help="Wipe existing user data before re-import")
    args = p.parse_args()

    if not args.xml.exists():
        print(f"ERROR: XML file not found: {args.xml}", file=sys.stderr)
        return 1

    size_mb = args.xml.stat().st_size / 1024 / 1024
    print(f"Source: {args.xml} ({size_mb:.1f} MB)")
    print(f"User:   {args.user_email}")

    with get_conn() as conn:
        user_id = ensure_user(conn, args.user_email, args.user_name)
        conn.commit()
    print(f"UserID: {user_id}\n")

    started = time.monotonic()
    stats = parse(args.xml, user_id, clear=args.clear)
    duration = time.monotonic() - started

    print("\n=== Import complete ===")
    print(f"  total elapsed: {duration:.1f}s ({duration / 60:.1f} min)")
    for k, v in stats.items():
        print(f"  {k:>32}: {v:>12,}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
