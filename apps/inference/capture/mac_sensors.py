"""Mac-as-sensor: frontmost app, idle time, keystrokes-per-min.

Writes one sensor_readings row per tick. Cheapest waking-context sensor
available — no new hardware, no permissions beyond AppleScript.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(INF_DIR))

from consent import CONSENT_SCOPES  # noqa: E402
from db import get_conn  # noqa: E402
from features.snapshot import FeatureSnapshot  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _frontmost_app() -> str:
    """Return the frontmost (visible, active) app name."""
    script = 'tell application "System Events" to get name of first process whose frontmost is true'
    try:
        out = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip()
    except Exception as e:
        logger.warning("osascript frontmost failed: %s", e)
        return "unknown"


def _idle_seconds() -> float:
    """Return system idle time in seconds (time since last HID input)."""
    try:
        out = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        for line in out.stdout.splitlines():
            if "HIDIdleTime" in line:
                # line format: ... "HIDIdleTime" = 1234567890  (nanoseconds)
                ns = int(line.split("=")[1].strip())
                return ns / 1e9
    except Exception as e:
        logger.warning("ioreg idle time failed: %s", e)
    return -1.0


def capture_once(user_id: str = DEFAULT_USER_ID) -> FeatureSnapshot:
    """Capture one snapshot. Does NOT write to DB; caller writes."""
    now = datetime.now(timezone.utc)
    return FeatureSnapshot(
        user_id=user_id,
        timestamp=now,
        modality="mac",
        source="mac.app_activity",
        payload={
            "active_app": _frontmost_app(),
            "idle_seconds": _idle_seconds(),
        },
        meta_context_hint="waking",
    )


def write_snapshot(snap: FeatureSnapshot) -> None:
    """Persist a FeatureSnapshot to sensor_readings."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sensor_readings (user_id, kind, recorded_at, source, payload, consent_scope)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                snap.user_id,
                "mac_activity",
                snap.timestamp,
                snap.source,
                json.dumps({
                    **snap.payload,
                    "meta_context_hint": snap.meta_context_hint,
                }),
                CONSENT_SCOPES["mac"],
            ),
        )
        conn.commit()


def run_loop(*, user_id: str = DEFAULT_USER_ID, interval_s: int = 30) -> None:
    """Capture + write every `interval_s` seconds. Ctrl-C to stop."""
    logger.info("mac_sensors loop starting (interval=%ds)", interval_s)
    while True:
        try:
            snap = capture_once(user_id=user_id)
            write_snapshot(snap)
            logger.info(
                "tick app=%s idle=%.1fs",
                snap.payload["active_app"],
                snap.payload["idle_seconds"],
            )
        except Exception as e:
            logger.exception("tick failed: %s", e)
        time.sleep(interval_s)


def _cli() -> int:
    p = argparse.ArgumentParser(prog="capture.mac_sensors")
    p.add_argument("--once", action="store_true", help="Capture one snapshot and exit (don't loop, don't write).")
    p.add_argument("--interval", type=int, default=30)
    p.add_argument("--user-id", default=DEFAULT_USER_ID)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.once:
        snap = capture_once(user_id=args.user_id)
        print(json.dumps(snap.to_dict(), indent=2, default=str))
        return 0

    try:
        run_loop(user_id=args.user_id, interval_s=args.interval)
    except KeyboardInterrupt:
        print("stopped.", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(_cli())
