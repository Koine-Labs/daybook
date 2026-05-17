"""Daybook Pi daemon — main entry point.

Wires sensor sources → DB + RealtimeClassifier → CueDecider → cue emitters.

Run: `python -m daemon --sensors mock --cues stdout --duration-minutes 5`
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue

from config import DaemonConfig, ensure_inference_importable
from cues import build_cue
from cues.base import CueEmitter
from sensors import build_sensor
from sensors.base import SensorPacket, SensorSource
from session import close_session, create_session

ensure_inference_importable()
from cue_decision import CueConfig, CueDecider  # noqa: E402
from db import get_conn  # noqa: E402
from realtime import RealtimeClassifier  # noqa: E402

logger = logging.getLogger("daemon")

# v0 utterance slot 4 ("rem_whisper") starter variants pulled from PERSONA.md.
# Once we have the full PERSONA loaded dynamically, swap this for a proper selector.
REM_WHISPER_STARTERS = [
    "You are dreaming.",
    "Notice your hands.",
    "Look around. This is the dream.",
]


# ── DB writer ───────────────────────────────────────────────────────────────

def db_writer_loop(
    queue: Queue[SensorPacket],
    user_id: str,
    session_id: str,
    stop_event: threading.Event,
) -> None:
    """Drain sensor queue, write each packet to Postgres + add to classifier."""
    while not stop_event.is_set() or not queue.empty():
        try:
            pkt = queue.get(timeout=0.5)
        except Empty:
            continue

        # Feed the in-memory classifier
        try:
            clf = SHARED["clf"]
            clf.add_reading(pkt.recorded_at, pkt.kind, pkt.value)
        except Exception:
            logger.exception("classifier.add_reading failed for %s", pkt)

        # Persist to DB (best-effort — if DB drops we log and continue)
        try:
            payload = _payload_for(pkt.kind, pkt.value)
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sensor_readings
                        (session_id, user_id, recorded_at, source, kind, payload)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (session_id, user_id, pkt.recorded_at, pkt.source, pkt.kind, json.dumps(payload)),
                )
                conn.commit()
        except Exception:
            logger.exception("DB write failed for %s — continuing", pkt)


def _payload_for(kind: str, value: float) -> dict:
    if kind == "heart_rate":
        return {"bpm": value, "unit": "count/min"}
    if kind == "hrv":
        return {"rmssdMs": value, "unit": "ms"}
    if kind == "respiratory_rate":
        return {"breathsPerMinute": value, "unit": "count/min"}
    if kind == "spo2":
        return {"percent": value, "unit": "%"}
    if kind.startswith("eeg_"):
        return {"microvolts": value, "unit": "uV"}
    if kind.startswith("motion_"):
        return {"g": value, "unit": "g"}
    return {"value": value, "unit": "unknown"}


# ── Predictor ───────────────────────────────────────────────────────────────

def predictor_loop(
    config: DaemonConfig,
    decider: CueDecider,
    cue_emitters: list[CueEmitter],
    session_id: str,
    stop_event: threading.Event,
) -> None:
    """Every `predictor_tick_seconds`, predict_at(now) → decide → maybe emit."""
    clf = SHARED["clf"]
    next_tick = time.monotonic()
    while not stop_event.is_set():
        now = datetime.now(timezone.utc)
        pred = clf.predict_at(now)
        decision = decider.update(pred)

        hr_n = pred.n_in_window.get("heart_rate", 0)
        logger.info(
            "tick  P(REM)=%.3f  hr_n=%-2d  decision=%s",
            pred.rem_probability, hr_n, decision.reason,
        )

        if decision.fire:
            utterance = random.choice(REM_WHISPER_STARTERS)
            for emitter in cue_emitters:
                try:
                    emission = emitter.emit(utterance, decision.cue_kind or "rem_whisper")
                    _log_cue_event(
                        session_id=session_id,
                        user_id=config.user_id,
                        delivered_at=now,
                        text=emission.text,
                        cue_kind=decision.cue_kind or "rem_whisper",
                        actual_proba=pred.rem_probability,
                        duration_ms=emission.duration_ms,
                        audio_ref=emission.audio_ref,
                    )
                except Exception:
                    logger.exception("cue emitter %s failed", emitter.name)

        next_tick += config.predictor_tick_seconds
        sleep_for = max(0.0, next_tick - time.monotonic())
        if sleep_for > 0:
            stop_event.wait(timeout=sleep_for)


def _log_cue_event(
    session_id: str,
    user_id: str,
    delivered_at: datetime,
    text: str,
    cue_kind: str,
    actual_proba: float,
    duration_ms: int,
    audio_ref: str | None,
) -> None:
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cue_events
                    (user_id, session_id, delivered_at, cue_content,
                     content_type, target_stage, actual_stage_at_delivery,
                     audio_duration_ms, audio_ref)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, session_id, delivered_at, text,
                    cue_kind, "REM", f"REM(p={actual_proba:.2f})",
                    duration_ms, audio_ref,
                ),
            )
            conn.commit()
    except Exception:
        logger.exception("cue_events insert failed")


# ── Shared mutable state ────────────────────────────────────────────────────

SHARED: dict = {}  # holds the single RealtimeClassifier instance


# ── Main ────────────────────────────────────────────────────────────────────

def parse_args() -> DaemonConfig:
    p = argparse.ArgumentParser(prog="daybook-pi")
    p.add_argument("--sensors", default="mock",
                   help="Comma-separated sensor specs: mock | esp32:/dev/ttyUSB0 | ...")
    p.add_argument("--cues", default="stdout",
                   help="Comma-separated cue emitter specs: stdout | audio | ...")
    p.add_argument("--duration-minutes", type=int, default=None,
                   help="Stop after N minutes (default: run until SIGINT)")
    p.add_argument("--mock-fast-forward", action="store_true",
                   help="If a mock sensor is enabled, run at 60x speed (1 real sec = 1 sim min)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()
    return DaemonConfig(
        sensor_spec=[s.strip() for s in args.sensors.split(",") if s.strip()],
        cue_spec=[s.strip() for s in args.cues.split(",") if s.strip()],
        duration_minutes=args.duration_minutes,
        mock_fast_forward=args.mock_fast_forward,
        log_level=args.log_level,
    )


def main() -> int:
    config = parse_args()
    config.configure_logging()

    logger.info("Daybook Pi daemon starting")
    logger.info("Sensors: %s | Cues: %s", config.sensor_spec, config.cue_spec)

    # Load AI brain
    logger.info("Loading RealtimeClassifier...")
    clf = RealtimeClassifier.load()
    SHARED["clf"] = clf

    started_at = datetime.now(timezone.utc)
    session_id = create_session(config.user_id, started_at)
    clf.start_session(started_at, user_id=config.user_id, session_id=session_id)
    clf.persist_state = True  # write user_state_estimate rows from now on

    expected_seconds = (config.duration_minutes or 480) * 60
    decider = CueDecider(CueConfig(expected_session_seconds=expected_seconds))
    decider.start_session(started_at, expected_seconds=expected_seconds)

    # If --mock-fast-forward, also relax CueDecider gates so we can see cues fire in a 5-min test
    if config.mock_fast_forward and any(s == "mock" for s in config.sensor_spec):
        logger.info("Mock fast-forward enabled — shrinking ramp-up + cooldown for testing")
        decider.config.no_fire_first_seconds = 30
        decider.config.no_fire_last_seconds = 15
        decider.config.cooldown_seconds = 30
        decider.config.consecutive_high_epochs = 1

    # Build sensor + cue plugins
    sensor_queue: Queue[SensorPacket] = Queue(maxsize=10_000)
    sensors: list[SensorSource] = []
    for spec in config.sensor_spec:
        src = build_sensor(spec)
        if isinstance(src, type(build_sensor("mock"))) and config.mock_fast_forward:
            src.fast_forward = True  # type: ignore[attr-defined]
        src.attach(sensor_queue)
        sensors.append(src)
    cue_emitters: list[CueEmitter] = [build_cue(spec) for spec in config.cue_spec]

    stop_event = threading.Event()

    # Wire signal handlers
    def _handle_signal(signum, frame):
        logger.info("Received signal %d — shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Start sensors
    for s in sensors:
        s.start()

    # Start DB writer
    writer = threading.Thread(
        target=db_writer_loop,
        args=(sensor_queue, config.user_id, session_id, stop_event),
        name="db_writer", daemon=True,
    )
    writer.start()

    # Start predictor (runs in main thread)
    deadline = None
    if config.duration_minutes:
        deadline = time.monotonic() + config.duration_minutes * 60

        def _deadline_watcher():
            while not stop_event.is_set():
                if time.monotonic() >= deadline:
                    logger.info("Duration limit reached")
                    stop_event.set()
                    return
                stop_event.wait(timeout=1.0)

        threading.Thread(target=_deadline_watcher, daemon=True).start()

    try:
        predictor_loop(config, decider, cue_emitters, session_id, stop_event)
    finally:
        logger.info("Stopping sensor sources...")
        for s in sensors:
            s.stop()
        logger.info("Stopping DB writer...")
        stop_event.set()
        writer.join(timeout=5.0)
        close_session(session_id, datetime.now(timezone.utc))
        logger.info("Daemon shutdown clean. Session %s closed.", session_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
