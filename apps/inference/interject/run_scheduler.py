"""CLI entry point: starts the Daybook scheduler daemon.

Usage:
    cd apps && source inference/.venv/bin/activate
    python -m inference.interject.run_scheduler

Times are configurable via env vars:
    DAYBOOK_MORNING_HOUR     (default 7)
    DAYBOOK_MORNING_MIN      (default 30)
    DAYBOOK_PRE_SLEEP_HOUR   (default 22)
    DAYBOOK_PRE_SLEEP_MIN    (default 30)
    DAYBOOK_USER_ID          (default Aakash)
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

APPS_DIR = INFERENCE_DIR.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from interject.morning_brief_trigger import fire_morning_brief  # noqa: E402
from interject.pre_sleep_trigger import fire_pre_sleep  # noqa: E402
from interject.scheduler import DaybookScheduler  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    user_id = os.environ.get("DAYBOOK_USER_ID", DEFAULT_USER_ID)
    morning_hour = int(os.environ.get("DAYBOOK_MORNING_HOUR", "7"))
    morning_min = int(os.environ.get("DAYBOOK_MORNING_MIN", "30"))
    pre_sleep_hour = int(os.environ.get("DAYBOOK_PRE_SLEEP_HOUR", "22"))
    pre_sleep_min = int(os.environ.get("DAYBOOK_PRE_SLEEP_MIN", "30"))

    sched = DaybookScheduler(blocking=True)
    sched.register_daily(
        hour=morning_hour,
        minute=morning_min,
        func=fire_morning_brief,
        name="morning_brief",
        user_id=user_id,
    )
    sched.register_daily(
        hour=pre_sleep_hour,
        minute=pre_sleep_min,
        func=fire_pre_sleep,
        name="pre_sleep",
        user_id=user_id,
    )

    print("Daybook scheduler starting. CTRL+C to stop.")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[scheduler] shutdown requested")
        sched.shutdown(wait=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
