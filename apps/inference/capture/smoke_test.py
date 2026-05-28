"""Smoke test: capture one Mac sensor reading and verify the shape."""
from __future__ import annotations

import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(INF_DIR))

from capture.mac_sensors import capture_once  # noqa: E402


def main() -> int:
    snap = capture_once()
    print(f"FeatureSnapshot: {snap.to_dict()}")
    assert snap.modality == "mac"
    assert "active_app" in snap.payload
    assert "idle_seconds" in snap.payload
    assert snap.timestamp.tzinfo is not None
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
