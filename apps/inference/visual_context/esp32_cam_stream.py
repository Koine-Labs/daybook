"""ESP32-CAM frame puller — JPEG snapshots over HTTP."""

from __future__ import annotations

import io
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable

import httpx
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_CAPTURE_PATH = "/capture"


def _normalize_url(cam_url: str) -> str:
    """Append /capture if the URL is just a host root."""
    if cam_url.endswith("/"):
        cam_url = cam_url[:-1]
    if cam_url.endswith(DEFAULT_CAPTURE_PATH) or "/stream" in cam_url:
        return cam_url
    return cam_url + DEFAULT_CAPTURE_PATH


def capture_frame(cam_url: str, *, timeout: float = 5.0) -> np.ndarray:
    """Pull one JPEG frame from ESP32-CAM, return as numpy RGB array."""
    url = _normalize_url(cam_url)
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
    image = Image.open(io.BytesIO(resp.content)).convert("RGB")
    return np.array(image)


def stream_frames(
    cam_url: str,
    *,
    fps: float = 1.0,
    callback: Callable[[np.ndarray, datetime], None],
    stop_event: threading.Event | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    """Continuous puller. Calls callback for each frame."""
    interval = 1.0 / fps if fps > 0 else 1.0
    stop = stop_event or threading.Event()
    while not stop.is_set():
        loop_start = time.monotonic()
        try:
            frame = capture_frame(cam_url)
            ts = datetime.now(timezone.utc)
            callback(frame, ts)
        except Exception as e:
            logger.warning("ESP32-CAM capture failed: %s", e)
            if on_error is not None:
                try:
                    on_error(e)
                except Exception:
                    pass
        elapsed = time.monotonic() - loop_start
        remaining = interval - elapsed
        if remaining > 0:
            stop.wait(remaining)
