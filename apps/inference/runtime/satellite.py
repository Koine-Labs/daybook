"""Generic sensor-satellite entrypoint — edge loops over a SatelliteLink.

The other half of runtime/hub.py: builds a MessageBus on NetworkTransport with a
SatelliteLink to the hub, then runs the sensor edge loops chosen by --sensors.
Every loop reuses an existing transport-agnostic L1 sink (EEGBusSink /
AudioBusSink-via-voice.loop / VisionBusSink / WatchBusSink) — this file is the
documented one-line NetworkTransport swap those sinks were built for, done for
real. Packets emitted here ride the link to the hub's L2→L6 arc; directives the
hub publishes ride back onto this bus.

Honesty notes: the eeg/vision/watch loops run the SAME synthetic generators
their edge stubs run today (real ADC / camera / HealthKit readers are the
documented swap point in each stub); the audio loop is the REAL mic loop
(voice.loop.listen_continuous, heavy [voice] extra imported lazily inside it).

Run on a satellite (Pi or any second machine; venv):
  cd apps/inference && DAYBOOK_HUB_URL=ws://<mac-ip>:8787 DAYBOOK_HUB_KEY=<shared-key> \
      python -m runtime.satellite --sensors eeg
  # or: python -m runtime.satellite --hub-url ws://<mac-ip>:8787 --key <k> --sensors eeg,vision
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

INF_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = INF_DIR.parent
for p in (str(INF_DIR), str(APPS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.bus.bus import MessageBus
from core.bus.network import NetworkTransport, SatelliteLink
from core.protocol.enums import MetaContext
from sensors.contract import DEFAULT_USER_ID

ENV_URL = "DAYBOOK_HUB_URL"
ENV_KEY = "DAYBOOK_HUB_KEY"
DEFAULT_HUB_URL = "ws://127.0.0.1:8787"
DEFAULT_SENSORS = "eeg"
DEFAULT_INTERVAL_SECONDS = 2.0

SensorLoop = Callable[..., None]


def build_satellite_bus(*, url: str, key: str) -> tuple[MessageBus, SatelliteLink]:
    """Connect a SatelliteLink to the hub; return its NetworkTransport bus + the link."""
    link = SatelliteLink(uri=url, key=key)
    link.start()
    return MessageBus(NetworkTransport(link)), link


def _eeg_loop(bus: MessageBus, *, user_id: str, stop: threading.Event, interval: float) -> None:
    """EXG Pill lane: semantic band-power windows via the edge stub's loop + sink."""
    from bci.firmware.eeg_edge_stub import _synthetic_reader, run_edge_loop
    from sensors.eeg_adapter import EEGBusSink

    sink = EEGBusSink(bus, user_id=user_id, meta_context=MetaContext.WAKING)
    reader = _synthetic_reader(fs=sink.fs, seconds=2.0, seed=0)
    while not stop.is_set():
        run_edge_loop(sink, read_window=reader, windows=1, fs=sink.fs, user_id=user_id)
        stop.wait(interval)


def _audio_loop(bus: MessageBus, *, user_id: str, stop: threading.Event, interval: float) -> None:
    """Real mic lane: blocks in listen_continuous, which owns its own cadence."""
    from voice.loop import listen_continuous

    listen_continuous(bus=bus, user_id=user_id, meta_context=MetaContext.WAKING)


def _vision_loop(bus: MessageBus, *, user_id: str, stop: threading.Event, interval: float) -> None:
    """Camera lane: deterministic synthetic scenes until the real frame reader lands."""
    from sensors.vision_adapter import VisionBusSink, synthesize_vision_frame

    sink = VisionBusSink(bus, user_id=user_id, meta_context=MetaContext.WAKING)
    index = 0
    while not stop.is_set():
        sink.emit_scene(synthesize_vision_frame(index), timestamp=datetime.now(timezone.utc))
        index += 1
        stop.wait(interval)


def _watch_loop(bus: MessageBus, *, user_id: str, stop: threading.Event, interval: float) -> None:
    """Watch lane: deterministic synthetic epoch windows until the HealthKit stream lands."""
    from sensors.watch_adapter import WatchBusSink, synthesize_biometric_window

    sink = WatchBusSink(bus, user_id=user_id, meta_context=MetaContext.WAKING)
    index = 0
    while not stop.is_set():
        window = synthesize_biometric_window(
            epoch_start_at=datetime.now(timezone.utc), index=index
        )
        sink.emit_window(**window, user_id=user_id)
        index += 1
        stop.wait(interval)


SENSOR_LOOPS: dict[str, SensorLoop] = {
    "eeg": _eeg_loop,
    "audio": _audio_loop,
    "vision": _vision_loop,
    "watch": _watch_loop,
}


def parse_sensors(spec: str) -> list[str]:
    """Comma-separated --sensors spec -> validated, deduped, order-preserving names."""
    names: list[str] = []
    for raw in spec.split(","):
        name = raw.strip()
        if name and name not in names:
            names.append(name)
    unknown = [n for n in names if n not in SENSOR_LOOPS]
    if unknown:
        raise ValueError(f"unknown sensors {unknown}; expected from {sorted(SENSOR_LOOPS)}")
    if not names:
        raise ValueError(f"--sensors selected nothing; expected from {sorted(SENSOR_LOOPS)}")
    return names


def run(
    *,
    url: str,
    key: str,
    sensors: Sequence[str],
    user_id: str = DEFAULT_USER_ID,
    interval: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Connect to the hub, start one thread per sensor loop, block until interrupted."""
    bus, link = build_satellite_bus(url=url, key=key)
    stop = threading.Event()
    threads = [
        threading.Thread(
            target=SENSOR_LOOPS[name], args=(bus,),
            kwargs={"user_id": user_id, "stop": stop, "interval": interval},
            name=f"sensor-{name}", daemon=True,
        )
        for name in sensors
    ]
    for thread in threads:
        thread.start()
    print(f"Satellite up — sensors [{', '.join(sensors)}] -> {url} (Ctrl-C to stop).", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=2.0)
        link.stop()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daybook sensor satellite (Pi / second machine).")
    parser.add_argument("--hub-url", default=os.environ.get(ENV_URL, DEFAULT_HUB_URL))
    parser.add_argument("--key", default=os.environ.get(ENV_KEY))
    parser.add_argument("--sensors", default=DEFAULT_SENSORS,
                        help=f"comma-separated from {sorted(SENSOR_LOOPS)}")
    parser.add_argument("--user-id", default=os.environ.get("DAYBOOK_USER_ID", DEFAULT_USER_ID))
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    if not args.key:
        parser.error(f"hub auth key required — set {ENV_KEY} or pass --key")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    run(url=args.hub_url, key=args.key, sensors=parse_sensors(args.sensors),
        user_id=args.user_id, interval=args.interval)


if __name__ == "__main__":
    main()
