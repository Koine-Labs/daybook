"""Pytest collection guards — full-suite collection must work on lean (CI) envs."""
from __future__ import annotations

import importlib.util

# audio/smoke_test.py imports the [voice] extra (sounddevice) at module level and
# actually plays audio — it is a hardware smoke script with zero collectible
# tests. Where the voice stack isn't installed (CI installs only --extra dev),
# importing it breaks full collection, so skip collecting it there. The pinned
# expected_test_count is unaffected: the file contributes 0 tests either way.
collect_ignore: list[str] = []
if importlib.util.find_spec("sounddevice") is None:
    collect_ignore.append("audio/smoke_test.py")
