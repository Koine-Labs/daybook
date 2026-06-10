"""Mac inference-hub entrypoint — the full L2→L6 arc listening for satellites.

The distributed twin of runtime/waking_arc.py: the same production assembly
(assemble_pipeline + register_speaker) but on a MessageBus over NetworkTransport
with a HubLink WebSocket server, so SignalPackets from a Pi/ESP32 satellite flow
into the SAME arc as local packets — NetworkTransport.dispatch delivers inbound
frames to the bus's registered handlers, no satellite-specific routing exists.
Directives the arc publishes (TOPIC_OUTPUT) ride back down the link to the
satellite automatically.

Auth is a shared key (#12's X-API-Key pattern at the bus layer): HubLink fails
closed without one, so the entrypoint requires DAYBOOK_HUB_KEY (or --key).

NOT on the CI path as a process: `python -m runtime.hub` binds a real port and
runs until interrupted. The builder (build_hub) is exercised DB/LLM-free on
loopback by runtime/test_hub_satellite.py via the same leaf-seam injection
core/test_pipeline.py uses.

Run on the Mac (venv):
  cd apps/inference && DAYBOOK_HUB_KEY=<shared-key> python -m runtime.hub
  # or: python -m runtime.hub --host 0.0.0.0 --port 8787 --key <shared-key>
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path
from typing import Sequence

INF_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = INF_DIR.parent
for p in (str(INF_DIR), str(APPS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.bus.bus import MessageBus
from core.bus.network import HubLink, NetworkTransport
from core.pipeline import assemble_pipeline
from decision.policy import Policy
from fusion.participant import AxisCombiner
from output.renderer import Renderer
from output.speaker import Speak, register_speaker

ENV_HOST = "DAYBOOK_HUB_HOST"
ENV_PORT = "DAYBOOK_HUB_PORT"
ENV_KEY = "DAYBOOK_HUB_KEY"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8787


def build_hub(
    *,
    host: str,
    port: int,
    key: str,
    fusion_registry: dict[str, AxisCombiner] | None = None,
    decision_policy: Policy | None = None,
    renderer: Renderer | None = None,
    speak: Speak | None = None,
) -> tuple[MessageBus, HubLink]:
    """Start a HubLink, then assemble the production arc + TTS sink on its bus.

    The injection seams mirror assemble_pipeline / register_speaker exactly: all
    omitted means pure production (real DefaultPolicy, ComposerRenderer, lazy
    real TTS). The loopback test injects deterministic leaves the same way
    core/test_pipeline.py does. Returns (bus, link); the caller owns link.stop().
    """
    link = HubLink(host=host, port=port, key=key)
    link.start()
    bus = MessageBus(NetworkTransport(link))
    assemble_pipeline(
        bus,
        fusion_registry=fusion_registry,
        decision_policy=decision_policy,
        renderer=renderer,
    )
    register_speaker(bus, speak=speak)
    return bus, link


def run(*, host: str, port: int, key: str) -> None:
    """Bring the hub up and block until interrupted; stop the link on the way out."""
    bus, link = build_hub(host=host, port=port, key=key)
    print(f"Hub up on ws://{host}:{port} — L2→L6 arc + TTS live (Ctrl-C to stop).", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        link.stop()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daybook inference hub (Mac).")
    parser.add_argument("--host", default=os.environ.get(ENV_HOST, DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get(ENV_PORT, DEFAULT_PORT)))
    parser.add_argument("--key", default=os.environ.get(ENV_KEY))
    args = parser.parse_args(argv)
    if not args.key:
        parser.error(f"satellite auth key required — set {ENV_KEY} or pass --key")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    run(host=args.host, port=args.port, key=args.key)


if __name__ == "__main__":
    main()
