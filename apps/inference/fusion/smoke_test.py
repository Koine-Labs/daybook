"""End-to-end Week-1 smoke test.

Sequence:
  1. Capture one Mac sensor reading (writes to sensor_readings).
  2. Run meta_context fusion → produce AxisEstimate.
  3. Run sleep_stage fusion → produce AxisEstimate or None.
  4. Write each estimate to user_state_estimate (per-axis-row).
  5. Read back the recent BeliefState; assert axes present.

Run:
    cd apps/inference && python -m fusion.smoke_test
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from capture.mac_sensors import capture_once, write_snapshot  # noqa: E402
from fusion.axes import audio_social_context as asc_axis  # noqa: E402
from fusion.axes import meta_context as mc_axis  # noqa: E402
from fusion.axes import sleep_stage as ss_axis  # noqa: E402
from fusion.belief_state import BeliefState  # noqa: E402
from fusion.writer import write_axis_estimate  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def main() -> int:
    now = datetime.now(timezone.utc)
    user_id = DEFAULT_USER_ID

    # 1. Capture Mac sensor reading (writes one sensor_readings row).
    snap = capture_once(user_id=user_id)
    write_snapshot(snap)
    print(f"[1/5] mac_activity captured: app={snap.payload['active_app']} idle={snap.payload['idle_seconds']:.1f}s")

    # 2. Fuse meta_context.
    mc_est = mc_axis.fuse_recent(user_id=user_id, now=now)
    assert mc_est is not None, "meta_context fusion returned None — Mac sensor write must have failed"
    print(f"[2/5] meta_context fused: {mc_est.value['category']} (conf={mc_est.confidence})")

    # 3. Fuse sleep_stage (may legitimately be None if not currently in sleep).
    ss_est = ss_axis.fuse_recent(user_id=user_id, now=now)
    if ss_est is None:
        print("[3/5] sleep_stage: OFFLINE (no covering window — expected if awake)")
    else:
        print(f"[3/5] sleep_stage fused: {ss_est.value['label']} (active={ss_est.value['active']})")

    # 3b. Fuse audio_social_context (None unless the continuous mic loop has
    # recently written an audio_social_context packet).
    asc_est = asc_axis.fuse_recent(user_id=user_id, now=now)
    if asc_est is None:
        print("[3/5] audio_social_context: none (no recent mic packet — expected if loop idle)")
    else:
        print(f"[3/5] audio_social_context fused: {asc_est.value['category']}")

    # 4. Write to user_state_estimate.
    mc_id = write_axis_estimate(user_id, mc_est)
    print(f"[4/5] meta_context written to user_state_estimate id={mc_id}")
    if ss_est is not None:
        ss_id = write_axis_estimate(user_id, ss_est)
        print(f"[4/5] sleep_stage written to user_state_estimate id={ss_id}")
    if asc_est is not None:
        asc_id = write_axis_estimate(user_id, asc_est)
        print(f"[4/5] audio_social_context written to user_state_estimate id={asc_id}")

    # 5. Read back as BeliefState and assert axes present + fresh.
    bs = BeliefState(user_id=user_id)
    bs.update(mc_est)
    if ss_est is not None:
        bs.update(ss_est)

    fresh = bs.snapshot(now=now)
    print(f"[5/5] BeliefState snapshot: {fresh}")
    assert "meta_context" in fresh, "meta_context missing from BeliefState"

    # Verify per-axis-row was persisted with correct shape via DB query.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT axis, value, confidence, source, meta_context
            FROM user_state_estimate
            WHERE user_id = %s AND id = %s
            """,
            (user_id, mc_id),
        )
        db_row = cur.fetchone()

    assert db_row is not None, "wrote meta_context row but couldn't read it back"
    axis, value, confidence, source, meta_context_col = db_row
    assert axis == "meta_context"
    assert value["category"].startswith("waking/")
    print(f"[5/5] DB readback: axis={axis} value={value} meta_context={meta_context_col}")

    print("\nOK — Week 1 end-to-end fusion smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
