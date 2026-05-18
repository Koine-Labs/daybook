"""End-to-end smoke test for visual_context."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

THIS_DIR = Path(__file__).resolve().parent
INFERENCE_DIR = THIS_DIR.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402

from visual_context.ocr import extract_text, get_visible_text_strings, is_available as ocr_available  # noqa: E402
from visual_context.processor import packet_to_json, persist_packet, process_frame  # noqa: E402
from visual_context.scene import classify_scene  # noqa: E402
from visual_context.yolo_runner import detect_objects  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
SMOKE_SOURCE = "visual_context_smoke"
LOGO_PATH = Path("/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Logo/Clear-Koine-Wisp.png")


def _banner(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _ensure_image(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Test image not found: {path}")
    return path


def main() -> int:
    _ensure_image(LOGO_PATH)

    pil = Image.open(str(LOGO_PATH)).convert("RGB")
    arr = np.array(pil)
    print(f"[init] loaded {LOGO_PATH.name} shape={arr.shape}")

    _banner("1. YOLO object detection")
    t0 = time.perf_counter()
    objects = detect_objects(arr)
    print(f"  ran in {time.perf_counter() - t0:.2f}s — {len(objects)} object(s)")
    for o in objects:
        print(f"    - {o.label} conf={o.confidence:.3f} bbox={tuple(round(v, 3) for v in o.bbox)}")

    _banner("2. CLIP scene classification")
    t0 = time.perf_counter()
    scene = classify_scene(arr)
    print(f"  ran in {time.perf_counter() - t0:.2f}s")
    print(f"  top: {scene['scene']} ({scene['confidence']:.3f})")
    for label, p in scene["alternatives"]:
        print(f"    alt: {label} ({p:.3f})")

    _banner("3. OCR text extraction")
    if ocr_available():
        t0 = time.perf_counter()
        ocr_items = extract_text(arr)
        print(f"  ran in {time.perf_counter() - t0:.2f}s — {len(ocr_items)} string(s)")
        for item in ocr_items:
            print(f"    - {item['text']!r} conf={item['confidence']:.3f}")
        print(f"  filtered (>=0.4): {get_visible_text_strings(arr)}")
    else:
        print("  OCR not available (easyocr not installed or load failed)")

    _banner("4. Full processor.process_frame")
    t0 = time.perf_counter()
    packet = process_frame(arr)
    print(f"  ran in {time.perf_counter() - t0:.2f}s")
    print(packet_to_json(packet))

    _banner("5. Persist + verify + clean up")
    row_id = persist_packet(packet, user_id=DEFAULT_USER_ID, source=SMOKE_SOURCE)
    print(f"  inserted row id={row_id}")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, kind, source, payload->>'scene' FROM sensor_readings WHERE id = %s",
            (row_id,),
        )
        verified = cur.fetchone()
        print(f"  verified: {verified}")

        cur.execute(
            "DELETE FROM sensor_readings WHERE source = %s",
            (SMOKE_SOURCE,),
        )
        deleted = cur.rowcount
        conn.commit()
        print(f"  cleaned up {deleted} smoke row(s)")

    _banner("smoke test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
