"""Pi satellite entrypoint — delegates to runtime.satellite with the Pi's defaults.

The Pi is a sensor satellite, not a second brain (apps/AI_PI_CONTRACT.md): it
connects a SatelliteLink to the Mac hub and streams semantic SignalPackets.
runtime.satellite's defaults ARE the Pi defaults — sensors default to the eeg
lane (BioAmp EXG Pill, the contract's first packet path) and the hub URL/key
come from DAYBOOK_HUB_URL / DAYBOOK_HUB_KEY.

Run on the Pi:
  DAYBOOK_HUB_URL=ws://<mac-ip>:8787 DAYBOOK_HUB_KEY=<shared-key> \
      python apps/pi/satellite.py --sensors eeg
"""
from __future__ import annotations

import sys
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent / "inference"
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from runtime.satellite import main  # noqa: E402

if __name__ == "__main__":
    main()
