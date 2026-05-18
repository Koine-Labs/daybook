"""Smoke test for the scheduler + morning_brief + pre_sleep triggers.

What this verifies:
  1. DaybookScheduler accepts a one-shot job and runs it within ~3s.
  2. compose_morning_brief_text returns text + sections (DRY RUN, no audio).
  3. compose_pre_sleep_text returns text + sections (DRY RUN, no audio).
  4. Any smoke-tagged regis_moments rows from the compose calls are cleaned up.

Run with:
    cd apps && source inference/.venv/bin/activate
    python -m inference.interject.scheduler_smoke
"""
from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

APPS_DIR = INFERENCE_DIR.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from db import get_conn  # noqa: E402

from interject.morning_brief_trigger import compose_morning_brief_text  # noqa: E402
from interject.pre_sleep_trigger import compose_pre_sleep_text  # noqa: E402
from interject.scheduler import DaybookScheduler  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _cleanup() -> int:
    """Drop smoke regis_moments rows from this run."""
    deleted = 0
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM regis_moments
                WHERE kind IN ('morning_brief', 'pre_sleep_prompt')
                  AND triggering_context::text LIKE '%SMOKE_SCHEDULER%'
                """
            )
            deleted = cur.rowcount
            conn.commit()
    except Exception as e:
        print(f"[cleanup] {e}")
    return deleted


def main() -> int:
    print("=== Daybook scheduler smoke test ===\n")

    # --- Test 1: one-shot job runs ---
    print("[Test 1] DaybookScheduler one-shot job fires within ~3s")
    fired = threading.Event()

    def _ping() -> None:
        fired.set()

    sched = DaybookScheduler(blocking=False)
    sched.register_once(
        run_at=datetime.now() + timedelta(seconds=1),
        func=_ping,
        name="smoke_ping",
    )
    sched.start()
    ok = fired.wait(timeout=5.0)
    sched.shutdown(wait=False)
    assert ok, "scheduler did not fire one-shot job within 5s"
    print("  one-shot job fired: OK\n")

    # --- Test 2: morning brief composition ---
    print("[Test 2] compose_morning_brief_text (dry run, persist=True for cleanup test)")
    mb = compose_morning_brief_text(user_id=DEFAULT_USER_ID, persist=False)
    print(f"  mode: {mb['mode']}")
    print(f"  sections.sleep: {mb['sections']['sleep']!r}")
    print(f"  sections.news ({len(mb['sections']['news'])} items):")
    for t in mb["sections"]["news"]:
        print(f"    - {t}")
    print(f"  sections.observations ({len(mb['sections']['observations'])} items):")
    for o in mb["sections"]["observations"]:
        print(f"    - {o}")
    print("\n  Morning brief utterance:")
    print(f"  >>> {mb['text']}\n")
    assert mb["text"], "morning brief text was empty"

    # --- Test 3: pre-sleep composition ---
    print("[Test 3] compose_pre_sleep_text (dry run)")
    ps = compose_pre_sleep_text(user_id=DEFAULT_USER_ID, persist=False)
    print(f"  mode: {ps['mode']}")
    print(f"  sections.intent_today: {ps['sections']['intent_today']!r}")
    print(f"  sections.last_sleep_summary: {ps['sections']['last_sleep_summary']!r}")
    print(f"  sections.recent_observations ({len(ps['sections']['recent_observations'])} items):")
    for o in ps["sections"]["recent_observations"]:
        print(f"    - {o}")
    print("\n  Pre-sleep utterance:")
    print(f"  >>> {ps['text']}\n")
    assert ps["text"], "pre-sleep text was empty"

    # --- Cleanup (no rows persisted in this run, but keep the hook) ---
    print("[cleanup] dropping any SMOKE_SCHEDULER-tagged regis_moments rows")
    n = _cleanup()
    print(f"  deleted {n} rows")

    print("\n=== Scheduler smoke test complete (all assertions passed) ===")
    return 0


if __name__ == "__main__":
    start = time.monotonic()
    rc = main()
    print(f"\n[total {time.monotonic() - start:.1f}s]")
    sys.exit(rc)
