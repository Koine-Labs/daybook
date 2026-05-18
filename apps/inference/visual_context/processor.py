"""Orchestrator — image → YOLO + scene + OCR → semantic packet."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .ocr import extract_text, is_available as ocr_available
from .scene import classify_scene
from .yolo_runner import DetectedObject, detect_objects

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402

logger = logging.getLogger(__name__)

MOTION_HIGH_RATIO = 0.04


@dataclass
class VisualContextPacket:
    captured_at: datetime
    scene: str
    scene_confidence: float
    objects: list[DetectedObject]
    text_visible: list[str]
    motion: str
    payload: dict = field(default_factory=dict)


def _to_array(image: np.ndarray | Path | str) -> np.ndarray:
    if isinstance(image, np.ndarray):
        return image
    pil = Image.open(str(image)).convert("RGB")
    return np.array(pil)


def _estimate_motion(curr: np.ndarray, prev: np.ndarray) -> str:
    """Cheap mean-abs-diff on downsampled grayscale; 'low'/'high'/'unknown'."""
    try:
        from PIL import Image as PILImage

        def _ds(arr: np.ndarray) -> np.ndarray:
            pil = PILImage.fromarray(arr).convert("L").resize((64, 64))
            return np.asarray(pil, dtype=np.float32) / 255.0

        a = _ds(curr)
        b = _ds(prev)
        diff = float(np.abs(a - b).mean())
        return "high" if diff > MOTION_HIGH_RATIO else "low"
    except Exception as e:
        logger.warning("Motion estimate failed: %s", e)
        return "unknown"


def _summarize_objects(objects: list[DetectedObject]) -> list[str]:
    """Compact 'label x N' strings, deduped."""
    counts: dict[str, int] = {}
    for o in objects:
        counts[o.label] = counts.get(o.label, 0) + 1
    return [f"{label} x{n}" if n > 1 else label for label, n in counts.items()]


def process_frame(
    image: np.ndarray | Path | str,
    *,
    captured_at: datetime | None = None,
    prev_image: np.ndarray | None = None,
) -> VisualContextPacket:
    """YOLO + scene + OCR → VisualContextPacket."""
    if captured_at is None:
        captured_at = datetime.now(timezone.utc)

    arr = _to_array(image)

    objects = detect_objects(arr)
    scene_result = classify_scene(arr)

    text_visible: list[str] = []
    ocr_warning: str | None = None
    if ocr_available():
        items = extract_text(arr)
        text_visible = [it["text"] for it in items if it.get("confidence", 0.0) >= 0.4]
    else:
        ocr_warning = "OCR_NOT_INSTALLED"

    motion = "unknown"
    if prev_image is not None:
        motion = _estimate_motion(arr, prev_image)

    payload: dict[str, Any] = {
        "scene": scene_result["scene"],
        "scene_confidence": round(scene_result["confidence"], 4),
        "scene_alternatives": [
            {"label": label, "p": round(p, 4)} for label, p in scene_result.get("alternatives", [])
        ],
        "objects": [
            {
                "label": o.label,
                "confidence": round(o.confidence, 4),
                "bbox": [round(v, 4) for v in o.bbox],
            }
            for o in objects
        ],
        "object_summary": _summarize_objects(objects),
        "text_visible": text_visible,
        "motion": motion,
        "frame_size": [int(arr.shape[1]), int(arr.shape[0])],
    }
    if ocr_warning:
        payload["warnings"] = [ocr_warning]

    return VisualContextPacket(
        captured_at=captured_at,
        scene=scene_result["scene"],
        scene_confidence=float(scene_result["confidence"]),
        objects=objects,
        text_visible=text_visible,
        motion=motion,
        payload=payload,
    )


def persist_packet(
    packet: VisualContextPacket,
    *,
    user_id: str,
    source: str = "visual_context_v1",
    session_id: str | None = None,
) -> str:
    """Write to sensor_readings as kind='visual_scene'. Returns row id."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sensor_readings
              (user_id, session_id, recorded_at, kind, source, payload)
            VALUES (%s, %s, %s, 'visual_scene', %s, %s::jsonb)
            RETURNING id
            """,
            (
                user_id,
                session_id,
                packet.captured_at,
                source,
                json.dumps(packet.payload),
            ),
        )
        row = cur.fetchone()
        conn.commit()
    return str(row[0])


def packet_to_json(packet: VisualContextPacket) -> str:
    """Pretty JSON dump of a packet."""
    obj = {
        "captured_at": packet.captured_at.isoformat(),
        "scene": packet.scene,
        "scene_confidence": packet.scene_confidence,
        "objects": [asdict(o) for o in packet.objects],
        "text_visible": packet.text_visible,
        "motion": packet.motion,
        "payload": packet.payload,
    }
    return json.dumps(obj, indent=2, default=str)
