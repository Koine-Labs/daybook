"""YOLOv8 object detection — lazy-loaded nano model, CPU-friendly."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "yolov8n.pt"
DEFAULT_CONF_THRESHOLD = 0.4

_model: Any = None


@dataclass
class DetectedObject:
    label: str
    confidence: float
    bbox: tuple[float, float, float, float]


def get_model() -> Any:
    """Lazy-load YOLOv8n. Cached."""
    global _model
    if _model is None:
        # Silence ultralytics' chatty startup banner.
        os.environ.setdefault("YOLO_VERBOSE", "False")
        from ultralytics import YOLO

        logger.info("Loading YOLO model %s (first call may download ~6MB)", DEFAULT_MODEL_NAME)
        _model = YOLO(DEFAULT_MODEL_NAME)
    return _model


def detect_objects(
    image: np.ndarray | Path | str,
    *,
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
    classes: list[str] | None = None,
) -> list[DetectedObject]:
    """Run YOLO object detection. Returns list of DetectedObject."""
    model = get_model()
    source = str(image) if isinstance(image, (Path, str)) else image

    results = model.predict(
        source=source,
        conf=conf_threshold,
        verbose=False,
    )
    if not results:
        return []

    result = results[0]
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return []

    names = result.names
    h, w = result.orig_shape

    detections: list[DetectedObject] = []
    xyxy = boxes.xyxy.cpu().numpy()
    conf = boxes.conf.cpu().numpy()
    cls = boxes.cls.cpu().numpy().astype(int)

    for i in range(len(boxes)):
        label = str(names.get(int(cls[i]), f"class_{int(cls[i])}"))
        if classes is not None and label not in classes:
            continue
        x1, y1, x2, y2 = xyxy[i]
        detections.append(
            DetectedObject(
                label=label,
                confidence=float(conf[i]),
                bbox=(
                    float(x1) / w,
                    float(y1) / h,
                    float(x2) / w,
                    float(y2) / h,
                ),
            )
        )
    return detections
