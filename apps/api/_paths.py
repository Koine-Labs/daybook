"""sys.path bootstrap so api.* can import from apps/inference, apps/wisp, apps/chat, apps/recall."""
from __future__ import annotations

import sys
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parent.parent
INFERENCE_DIR = APPS_DIR / "inference"
WISP_DIR = APPS_DIR / "wisp"

for p in (APPS_DIR, INFERENCE_DIR):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

PERSONA_PATH = WISP_DIR / "PERSONA.md"
RECALL_AUDIO_DIR = Path.home() / ".daybook" / "recall_audio"
