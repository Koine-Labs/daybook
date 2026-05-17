"""Smoke test for the Pi daemon — runs MockSensorSource → StdoutCueEmitter for 3 minutes.

Requires the Pi-side env to have:
- DATABASE_URL in apps/inference/.env.local (DB writes will be skipped if missing)
- apps/inference/classifier/models/production_binary_rem.json (the trained model)

This is a long-running smoke test, not a unit test. Run manually:
    cd apps/pi
    python -m pytest tests/test_daemon_smoke.py -s
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PI_DIR = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    not (PI_DIR.parent / "inference" / "classifier" / "models" / "production_binary_rem.json").exists(),
    reason="trained model not present",
)
def test_3min_smoke():
    """Run the daemon for 3 minutes with mock sensors + fast-forward, verify clean exit."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PI_DIR)
    result = subprocess.run(
        [
            sys.executable, "-m", "daemon",
            "--sensors", "mock",
            "--cues", "stdout",
            "--duration-minutes", "3",
            "--mock-fast-forward",
            "--log-level", "INFO",
        ],
        cwd=PI_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"daemon exited non-zero\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "Daemon shutdown clean" in result.stderr, "Did not log clean shutdown"
    # Should have at least logged a few predictor ticks
    assert result.stderr.count("tick  P(REM)") >= 3, "Predictor did not tick enough times"
