"""Tombstone: the v0 sleep daemon was removed 2026-06-10 (see git history)."""
from __future__ import annotations

import sys

print("v0 daemon removed — use apps/pi/satellite.py", file=sys.stderr)
sys.exit(1)
