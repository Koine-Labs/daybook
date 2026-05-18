"""EasyOCR text-in-image extraction."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_reader: Any = None
_load_error: Exception | None = None


def _get_reader() -> Any:
    """Lazy-load EasyOCR reader. English only for v0."""
    global _reader, _load_error
    if _reader is not None:
        return _reader
    if _load_error is not None:
        raise _load_error
    try:
        import easyocr

        logger.info("Loading EasyOCR reader (first call downloads ~200MB)")
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return _reader
    except Exception as e:
        _load_error = e
        raise


def _coerce_image(image: np.ndarray | Path | str) -> Any:
    if isinstance(image, (str, Path)):
        return str(image)
    return image


def extract_text(image: np.ndarray | Path | str) -> list[dict]:
    """Returns list of {text, confidence, bbox}."""
    try:
        reader = _get_reader()
    except Exception as e:
        logger.warning("EasyOCR unavailable: %s", e)
        return []

    source = _coerce_image(image)
    try:
        raw = reader.readtext(source)
    except Exception as e:
        logger.warning("EasyOCR readtext failed: %s", e)
        return []

    out: list[dict] = []
    for entry in raw:
        bbox_pts, text, conf = entry
        xs = [p[0] for p in bbox_pts]
        ys = [p[1] for p in bbox_pts]
        out.append(
            {
                "text": str(text),
                "confidence": float(conf),
                "bbox": (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))),
            }
        )
    return out


def get_visible_text_strings(
    image: np.ndarray | Path | str,
    *,
    min_confidence: float = 0.4,
) -> list[str]:
    """Convenience: just the text strings, filtered by confidence."""
    items = extract_text(image)
    return [item["text"] for item in items if item.get("confidence", 0.0) >= min_confidence]


def is_available() -> bool:
    """True if EasyOCR can be loaded."""
    try:
        _get_reader()
        return True
    except Exception:
        return False
