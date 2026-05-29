"""Guard: the L1–L6 protocol/bus core imports WITHOUT DATABASE_URL (DB-free core).

Regression for the PR-38 finding that `core.protocol.codec` pulled `db` into the
import graph (via `fusion/__init__` → `fusion.writer` → `db`, which raised at
import when DATABASE_URL was absent). Each check runs in a subprocess with dotenv
neutered and DATABASE_URL removed, faithfully reproducing a clean environment
regardless of the developer's local `.env.local`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent

# The foundational core: must import with zero runtime config.
CORE_MODULES = [
    "core.protocol.enums",
    "core.protocol.payloads",
    "core.protocol.codec",
    "core.protocol.decode",
    "core.protocol.envelope",
    "core.bus.transport",
    "core.bus.bus",
    "core.bus.network",
    "core.nodes",
    "core.layer",
]

# The mic-onto-bus producer (L1) + L2 audio extractor must stay import-clean too:
# DB-free AND free of the heavy [voice] stack (torch/sounddevice/silero/etc.). The
# real models live behind voice.continuous's lazy I/O, never at import; this guard
# fails loudly if a future edit pulls a heavy dependency into the import graph.
AUDIO_BUS_MODULES = [
    "sensors.audio_adapter",
    "features.audio_social",
    "features.participant",
    "fusion.axes.audio_social_context",
]
HEAVY_LIBS = ["torch", "sounddevice", "silero_vad", "resemblyzer", "librosa", "tensorflow"]


def _import_in_clean_env(modules: list[str]) -> subprocess.CompletedProcess[str]:
    """Import `modules` in a subprocess with no DATABASE_URL and dotenv disabled."""
    code = (
        "import dotenv\n"
        "dotenv.load_dotenv = lambda *a, **k: False\n"  # don't read .env.local
        "import os\n"
        "os.environ.pop('DATABASE_URL', None)\n"
        + "".join(f"import {m}\n" for m in modules)
        + "print('IMPORT_OK')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(INF_DIR),
        capture_output=True,
        text=True,
        env=env,
    )


def test_core_imports_without_database_url():
    result = _import_in_clean_env(CORE_MODULES)
    assert result.returncode == 0, (
        "core import required DATABASE_URL (DB leaked into the import graph):\n"
        f"{result.stderr}"
    )
    assert "IMPORT_OK" in result.stdout


def test_db_module_imports_without_database_url():
    # Importing db must be safe; the requirement is enforced lazily at pool use.
    result = _import_in_clean_env(["db"])
    assert result.returncode == 0, f"importing db required DATABASE_URL:\n{result.stderr}"
    assert "IMPORT_OK" in result.stdout


def test_audio_bus_modules_import_without_database_url():
    result = _import_in_clean_env(AUDIO_BUS_MODULES)
    assert result.returncode == 0, (
        "mic-onto-bus producer/L2 required DATABASE_URL (DB leaked into the import graph):\n"
        f"{result.stderr}"
    )
    assert "IMPORT_OK" in result.stdout


def test_audio_bus_modules_pull_no_heavy_libs():
    """Semantic-first (#11): the L1 producer + L2 extractor must not drag the heavy
    [voice] stack (torch/sounddevice/silero/...) into the import graph. The models
    live behind lazy I/O in voice.continuous, invoked only when a real mic runs."""
    code = (
        "import dotenv\n"
        "dotenv.load_dotenv = lambda *a, **k: False\n"
        "import os, sys\n"
        "os.environ.pop('DATABASE_URL', None)\n"
        + "".join(f"import {m}\n" for m in AUDIO_BUS_MODULES)
        + f"leaked = [m for m in {HEAVY_LIBS!r} if m in sys.modules]\n"
        "print('LEAKED:' + ','.join(leaked))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(INF_DIR), capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    leaked = next(
        (ln[len("LEAKED:"):] for ln in result.stdout.splitlines() if ln.startswith("LEAKED:")),
        None,
    )
    assert leaked == "", f"heavy libs leaked into the L1/L2 import graph: {leaked!r}"
