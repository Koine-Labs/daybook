"""Shared sys.path bootstrap so chat.* can import from apps/inference and apps/wisp."""
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
DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
