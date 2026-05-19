"""Daybook — unified always-on companion daemon.

ONE command starts every always-on component in one supervised process:

  - Continuous mic listener with wake-phrase detection (default: "Regis")
  - Scheduled triggers (morning brief @ 7:30am, pre-sleep @ 22:30)
  - Future: continuous audio-context daemon, visual-context daemon, FastAPI bridge

Invocation (from apps/):

  python -m daybook                    # everything (mic + scheduler)
  python -m daybook --mic-only         # just the wake-listener
  python -m daybook --scheduler-only   # just the daily briefs
  python -m daybook --no-speak         # print replies instead of TTS playback

Env-var overrides (passed through to component defaults):

  DAYBOOK_WAKE_PHRASE              default 'regis'
  DAYBOOK_WAKE_MODE                default 'transcription'   ('transcription' | 'wake_word')
  DAYBOOK_WAKE_WORD                default 'hey_jarvis'      (only for wake_word mode)
  DAYBOOK_MORNING_HOUR             default 7
  DAYBOOK_MORNING_MIN              default 30
  DAYBOOK_PRE_SLEEP_HOUR           default 22
  DAYBOOK_PRE_SLEEP_MIN            default 30
  DAYBOOK_OUTCOME_LABELER_HOUR     default 2    (backfill user_outcome on interject_decisions)
  DAYBOOK_OUTCOME_LABELER_MIN      default 0
  DAYBOOK_NREM_HOUR                default 3    (factual day-distillation)
  DAYBOOK_NREM_MIN                 default 0
  DAYBOOK_CLUSTERING_HOUR          default 4    (nightly I-Model clustering)
  DAYBOOK_CLUSTERING_MIN           default 0
  DAYBOOK_TRAIT_DECAY_HOUR         default 4    (nightly trait-decay toward learned baseline)
  DAYBOOK_TRAIT_DECAY_MIN          default 30
  DAYBOOK_DORMANCY_HOUR            default 4    (cluster dormancy sweep)
  DAYBOOK_DORMANCY_MIN             default 45
  DAYBOOK_REM_HOUR                 default 5    (associative dream-recombination)
  DAYBOOK_REM_MIN                  default 0
  DAYBOOK_INNER_PULSE_INTERVAL_MIN default 25   (proactive thought cadence, 24/7 smart-gated)
  DAYBOOK_LEARNED_DECIDER          default off  (set to 1 to route decider through Thompson bandit)

Ctrl-C shuts everything down cleanly.

Eventually this script is the ONE thing the Pi runs at boot via systemd. Today
it runs on the Mac. Same code path; only the host changes.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Path setup so every module is importable from `apps/` root.
APPS_DIR = Path(__file__).resolve().parent
INFERENCE_DIR = APPS_DIR / "inference"
for _p in (APPS_DIR, INFERENCE_DIR):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

logger = logging.getLogger("daybook")

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _make_scheduler(*, user_id: str):
    """Build a BackgroundScheduler with the standard daily triggers registered."""
    from chat.consolidator import consolidate_yesterday
    from chat.dreamer import run_rem_dreaming
    from chat.trait_decay import apply_nightly_decay
    from inference.imodels.cluster_dormancy import sweep_dormancy
    from inference.interject.clustering_trigger import run_nightly_clustering
    from inference.interject.inner_pulse_trigger import fire_inner_pulse
    from inference.interject.morning_brief_trigger import fire_morning_brief
    from inference.interject.outcome_labeler import label_recent_decisions
    from inference.interject.pre_sleep_trigger import fire_pre_sleep
    from inference.interject.scheduler import DaybookScheduler

    morning_h = int(os.environ.get("DAYBOOK_MORNING_HOUR", "7"))
    morning_m = int(os.environ.get("DAYBOOK_MORNING_MIN", "30"))
    pre_sleep_h = int(os.environ.get("DAYBOOK_PRE_SLEEP_HOUR", "22"))
    pre_sleep_m = int(os.environ.get("DAYBOOK_PRE_SLEEP_MIN", "30"))
    nrem_h = int(os.environ.get("DAYBOOK_NREM_HOUR", "3"))
    nrem_m = int(os.environ.get("DAYBOOK_NREM_MIN", "0"))
    rem_h = int(os.environ.get("DAYBOOK_REM_HOUR", "5"))
    rem_m = int(os.environ.get("DAYBOOK_REM_MIN", "0"))
    clustering_h = int(os.environ.get("DAYBOOK_CLUSTERING_HOUR", "4"))
    clustering_m = int(os.environ.get("DAYBOOK_CLUSTERING_MIN", "0"))
    decay_h = int(os.environ.get("DAYBOOK_TRAIT_DECAY_HOUR", "4"))
    decay_m = int(os.environ.get("DAYBOOK_TRAIT_DECAY_MIN", "30"))
    dormancy_h = int(os.environ.get("DAYBOOK_DORMANCY_HOUR", "4"))
    dormancy_m = int(os.environ.get("DAYBOOK_DORMANCY_MIN", "45"))
    labeler_h = int(os.environ.get("DAYBOOK_OUTCOME_LABELER_HOUR", "2"))
    labeler_m = int(os.environ.get("DAYBOOK_OUTCOME_LABELER_MIN", "0"))
    pulse_interval = int(os.environ.get("DAYBOOK_INNER_PULSE_INTERVAL_MIN", "25"))

    sched = DaybookScheduler(blocking=False)
    sched.register_daily(
        hour=morning_h, minute=morning_m,
        func=fire_morning_brief, name="morning_brief",
        user_id=user_id,
    )
    sched.register_daily(
        hour=pre_sleep_h, minute=pre_sleep_m,
        func=fire_pre_sleep, name="pre_sleep",
        user_id=user_id,
    )
    sched.register_daily(
        hour=labeler_h, minute=labeler_m,
        func=label_recent_decisions, name="outcome_labeler",
        user_id=user_id,
    )
    sched.register_daily(
        hour=nrem_h, minute=nrem_m,
        func=consolidate_yesterday, name="nrem_consolidation",
        user_id=user_id,
    )
    sched.register_daily(
        hour=clustering_h, minute=clustering_m,
        func=run_nightly_clustering, name="nightly_clustering",
        user_id=user_id,
    )
    sched.register_daily(
        hour=decay_h, minute=decay_m,
        func=apply_nightly_decay, name="trait_decay",
        user_id=user_id,
    )
    sched.register_daily(
        hour=dormancy_h, minute=dormancy_m,
        func=sweep_dormancy, name="cluster_dormancy_sweep",
        user_id=user_id,
    )
    sched.register_daily(
        hour=rem_h, minute=rem_m,
        func=run_rem_dreaming, name="rem_dreaming",
        user_id=user_id,
    )
    sched.register_interval(
        minutes=pulse_interval,
        func=fire_inner_pulse, name="inner_pulse",
        user_id=user_id,
    )
    return sched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="daybook",
        description="Unified Daybook always-on companion daemon",
    )
    parser.add_argument("--no-mic", action="store_true", help="don't start the mic listener")
    parser.add_argument("--no-scheduler", action="store_true", help="don't start the scheduler")
    parser.add_argument("--mic-only", action="store_true", help="alias for --no-scheduler")
    parser.add_argument("--scheduler-only", action="store_true", help="alias for --no-mic")
    parser.add_argument("--no-speak", action="store_true", help="print replies instead of TTS playback")
    parser.add_argument("--user", default=DEFAULT_USER_ID)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    if args.mic_only:
        args.no_scheduler = True
    if args.scheduler_only:
        args.no_mic = True

    if args.no_mic and args.no_scheduler:
        print("ERROR: both --no-mic and --no-scheduler set — nothing to run", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print("=" * 60)
    print("DAYBOOK — unified always-on companion")
    print("=" * 60)
    components = []
    if not args.no_scheduler:
        components.append("scheduler")
    if not args.no_mic:
        components.append("mic listener")
    print(f"running: {' + '.join(components)}")
    print(f"user: {args.user}")
    print(f"speak: {'on' if not args.no_speak else 'off (print only)'}")
    print("=" * 60)
    print()

    sched = None
    if not args.no_scheduler:
        print("[daybook] starting scheduler...")
        sched = _make_scheduler(user_id=args.user)
        sched.start()  # BackgroundScheduler — does not block
        print("[daybook] scheduler running in background")
        print()

    exit_code = 0
    try:
        if not args.no_mic:
            print("[daybook] starting mic listener (foreground)...")
            print()
            from mic_listener.run import main as mic_main

            mic_argv: list[str] = ["--user", args.user]
            if args.no_speak:
                mic_argv.append("--no-speak")
            exit_code = mic_main(mic_argv) or 0
        else:
            # Scheduler-only mode — block forever until Ctrl-C.
            print("[daybook] scheduler-only mode. Ctrl-C to quit.")
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        if sched is not None:
            print()
            print("[daybook] shutting down scheduler...")
            sched.shutdown(wait=False)
        print("[daybook] goodbye.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
