"""Pluggable cue emitters — what the wisp actually does when CueDecider fires."""
from .base import CueEmitter  # noqa: F401
from .stdout import StdoutCueEmitter  # noqa: F401


def build_cue(spec: str) -> CueEmitter:
    """Parse a cue spec and return a CueEmitter.

    Spec format:
        "stdout"               → StdoutCueEmitter
        (future) "audio", "haptic:/dev/ttyUSB0", ...
    """
    if spec == "stdout":
        return StdoutCueEmitter()
    raise ValueError(f"Unknown cue spec: {spec!r}")
