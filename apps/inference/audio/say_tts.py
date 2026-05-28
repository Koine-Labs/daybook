"""macOS `say` TTS fallback. WAVE/LEI16 output, read back as WAV bytes."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


DEFAULT_VOICE = "Daniel"
DEFAULT_RATE = 180


class SayUnavailable(RuntimeError):
    """Raised when macOS `say` is not available."""


def is_available() -> bool:
    """True only on macOS with `say` on PATH."""
    return shutil.which("say") is not None


def synthesize_say(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: int = DEFAULT_RATE,
) -> bytes:
    """Run `say` to a temp WAV and return its bytes."""
    if not text or not text.strip():
        raise ValueError("synthesize_say: text is empty")
    if not is_available():
        raise SayUnavailable("macOS `say` command not on PATH")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        # WAVE/LEI16@22050 = standard 16-bit PCM WAV at 22050 Hz. Works on every
        # macOS we care about; AIFF and LEF32 are quirky.
        result = subprocess.run(
            [
                "say",
                "-v",
                voice,
                "-r",
                str(rate),
                "-o",
                str(out_path),
                "--file-format=WAVE",
                "--data-format=LEI16@22050",
                text,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise SayUnavailable(
                f"`say` exit {result.returncode}: {result.stderr.strip() or 'no stderr'}"
            )
        return out_path.read_bytes()
    finally:
        out_path.unlink(missing_ok=True)


def list_voices() -> list[str]:
    """Return voice names reported by `say -v '?'`. Empty if `say` missing."""
    if not is_available():
        return []
    res = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5)
    if res.returncode != 0:
        return []
    voices: list[str] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        voices.append(line.split()[0])
    return voices
