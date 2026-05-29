"""Off-CI reference: the frame -> scene-semantics -> emit edge loop for the camera.

This is the documented edge contract, ready for a camera satellite (Pi/ESP32-CAM
or a USB webcam on the Mac). It runs TODAY on a laptop only if the [vision] extra
is installed AND a sample image is provided; on the real rig the only swaps are
(1) point `read_frame` at the real camera and (2) bind the sink to a
NetworkTransport-backed bus (camera-as-satellite).

It is NOT collected by CI: vision/ is a collected dir, but this file carries no
test_*.py prefix so nothing is collected here. It imports the real
vision.perception.extract_semantics + sensors.vision_adapter.VisionBusSink so the
edge and the lane share one semantic contract. All heavy imports are LAZY (inside
functions), so `python -c "import vision.perception_edge_stub"` is clean with no
model and no DB.

Run locally (needs the model + a sample frame; no DB; InProcessTransport):
    cd apps/inference && uv pip install -e ".[vision]"
    python -m vision.perception_edge_stub --image path/to/sample.jpg --frames 3

──────────────────────────────────────────────────────────────────────────────
SEMANTIC-FIRST EDGE LOOP (#11) — raw pixels are extracted-then-discarded on-device:

    loop @ frame cadence (e.g. every 1-2s, NOT every camera frame):
        frame = camera.read_frame()                       # webcam / ESP32-CAM -> bytes
        scene = extract_semantics(frame)                  # SEMANTIC extraction at the edge (YOLO/OCR)
        del frame                                         # RAW PIXELS DISCARDED — never leave device
        sink.emit_scene(scene, timestamp=now_utc())       # only the scene dict rides the bus

──────────────────────────────────────────────────────────────────────────────
CAMERA-AS-SATELLITE — the one-line NetworkTransport swap (commitment #9):

    Today (synthetic-or-local, InProcessTransport on the Mac):
        bus  = MessageBus()                               # InProcessTransport
        sink = VisionBusSink(bus, meta_context=MetaContext.WAKING)

    On the rig (camera on a Pi/ESP32 satellite, frames extracted on-device,
    only scene packets cross the wire):
        bus  = MessageBus(transport=NetworkTransport(...)) # the ONLY change
        sink = VisionBusSink(bus, meta_context=MetaContext.WAKING)
        # VisionBusSink is transport-agnostic — identical code, identical contract.

CAMERA-ON-ARRIVAL (why this is "plug-and-play, a using/calibration task"):
  When the camera/satellite is wired: (1) point read_frame at the real device;
  (2) optionally fit fusion.axes.visual_context's category thresholds (Stage 2) on
  a few labeled waking scenes — the entire L1->L2->L3 plumbing, contracts, and
  tests are already in place. No live camera ships in this build (deferred "using").

TRIGGERED-ESCALATION SEAM (#11 — documented, NOT wired into this continuous loop):
  llm/vision.py:describe_image stays the cloud escalation path. When the continuous
  semantic layer flags something salient/novel, a future L4/L5 hook escalates ONE
  frame to the cloud describer. This stub makes NO continuous cloud call.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


# On the real rig this reads the camera; here it replays a single sample frame's bytes.
FrameReader = Callable[[], bytes]


def _sample_reader(image_path: Path) -> FrameReader:
    data = image_path.read_bytes()

    def read() -> bytes:
        return data

    return read


def run_edge_loop(sink, *, read_frame: FrameReader, frames: int) -> int:
    """The semantic-first edge loop: read a frame, extract scene, DISCARD pixels, emit.

    Returns the number of semantic packets emitted. On the real rig, swap
    `read_frame` for the camera reader and the sink's bus for a NetworkTransport bus.
    """
    from vision.perception import extract_semantics  # LAZY: needs the [vision] model

    emitted = 0
    for _ in range(frames):
        frame = read_frame()                                   # camera -> bytes
        scene = extract_semantics(frame)                       # semantic extraction at the edge
        del frame                                              # RAW PIXELS DISCARDED — never leave device
        sink.emit_scene(scene, timestamp=datetime.now(timezone.utc))
        emitted += 1
    return emitted


def main() -> None:
    parser = argparse.ArgumentParser(description="Off-CI vision edge stub (needs [vision] model + a sample image, no DB).")
    parser.add_argument("--image", type=Path, required=True, help="sample frame (jpg/png)")
    parser.add_argument("--frames", type=int, default=3)
    args = parser.parse_args()

    from core.bus.bus import TOPIC_SIGNAL, MessageBus  # LAZY so import stays clean
    from core.protocol.enums import MetaContext
    from sensors.vision_adapter import VisionBusSink

    bus = MessageBus()  # InProcessTransport; real rig binds NetworkTransport (camera satellite).
    seen: list = []
    bus.subscribe(TOPIC_SIGNAL, seen.append)
    sink = VisionBusSink(bus, meta_context=MetaContext.WAKING)

    emitted = run_edge_loop(sink, read_frame=_sample_reader(args.image), frames=args.frames)

    print(f"emitted {emitted} visual_scene packets (raw pixels discarded at the edge)")
    for env in seen:
        p = env.payload.payload
        assert "image_bytes" not in p and "pixels" not in p  # invariant: no raw pixels on the bus
        print(f"  setting={p['setting']:>7}  people={p['people_present']}  objects={p['salient_objects']}")


if __name__ == "__main__":
    main()
