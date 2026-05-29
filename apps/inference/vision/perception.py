"""Scene-semantics extraction — a camera frame -> a visual_scene semantic dict.

Canonical edge math, the vision lane's analog of bci/bandpower.py. The edge
(camera satellite) runs a detector over a frame and DISCARDS the raw pixels; only
the resulting semantic dict ({setting, people_present, salient_objects,
text_present, model}) ever rides the bus (semantic-first, #11). The cloud
multimodal describer (llm/vision.py:describe_image) is the TRIGGERED-ESCALATION
path only — never this continuous loop.

The real detector is the [vision] extra (ultralytics YOLO for person/object
detection, optional OCR for text). That import is LAZY and lives inside
`extract_semantics`, so this module imports clean with no model installed and no
DATABASE_URL (mirroring bci/bandpower.py + bci/firmware/eeg_edge_stub.py). CI
never installs the model — it runs on synthetic semantics
(sensors.vision_adapter.synthesize_vision_frame) only.
"""
from __future__ import annotations

from typing import Any

# Frozen vocabulary for the `setting` field of a visual_scene packet (Stage 2 L2/L3
# map against these). "unknown" is the honest degraded value.
SETTINGS: tuple[str, ...] = ("outdoor", "indoor", "transit", "screen", "unknown")

KIND_VISUAL_SCENE = "visual_scene"          # SignalPacket.kind for this lane
VISION_SOURCE = "camera.visual_scene"       # real Pi sets a satellite-specific source

# How many top object classes ride in salient_objects (low-bandwidth, #11).
TOP_K_OBJECTS = 5

# Detector provenance stamped on a real extraction's `model` field. The default
# ultralytics nano weights; the synthetic generator stamps "synthetic" instead.
DEFAULT_DETECTOR_MODEL = "yolov8n"
VERSION = "perception.v1"


def _zero_scene(model: str = DEFAULT_DETECTOR_MODEL) -> dict[str, Any]:
    """Honest degraded scene: nothing detected, setting unknown, no crash."""
    return {
        "setting": "unknown",
        "people_present": 0,
        "salient_objects": [],
        "text_present": False,
        "model": model,
    }


def extract_semantics(
    image_bytes: bytes,
    *,
    detect_text: bool = False,
    detector_model: str = DEFAULT_DETECTOR_MODEL,
) -> dict[str, Any]:
    """Run the real detector over a frame -> visual_scene semantic dict; DISCARD pixels.

    LAZY-imports the [vision] model (ultralytics YOLO; optional OCR) so this module
    is import-clean with no model installed. Off-CI (needs the model): CI proves the
    schema on synthetic semantics instead. Returns ONLY the semantic dict
    ({setting, people_present, salient_objects, text_present, model}); `image_bytes`
    is consumed and never returned — raw pixels never leave this function (#11).
    """
    if not image_bytes:
        raise ValueError("image_bytes must be non-empty")

    try:
        from ultralytics import YOLO  # noqa: F401 — heavy; LAZY by design (#11, off-CI)
    except ImportError as exc:  # pragma: no cover - exercised only off-CI
        raise RuntimeError(
            "vision detector unavailable: install the [vision] extra "
            "(uv pip install -e \".[vision]\") on the camera/compute node"
        ) from exc

    from PIL import Image  # pragma: no cover - off-CI
    import io  # pragma: no cover - off-CI

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")  # pragma: no cover - off-CI
    model = _load_detector(detector_model)  # pragma: no cover - off-CI
    detections = model(image, verbose=False)  # pragma: no cover - off-CI
    scene = _detections_to_scene(  # pragma: no cover - off-CI
        detections, model_name=detector_model
    )
    if detect_text:  # pragma: no cover - off-CI
        scene["text_present"] = _ocr_has_text(image)
    del image_bytes, image, detections  # pragma: no cover - RAW DISCARDED (#11)
    return scene  # pragma: no cover - off-CI


def _load_detector(detector_model: str):  # pragma: no cover - off-CI, needs model
    """Lazily construct the YOLO detector (off-CI; model weights not in CI)."""
    from ultralytics import YOLO

    return YOLO(f"{detector_model}.pt")


def _detections_to_scene(detections: Any, *, model_name: str) -> dict[str, Any]:  # pragma: no cover - off-CI
    """Collapse raw detector boxes into the semantic visual_scene dict (no pixels)."""
    counts: dict[str, int] = {}
    people = 0
    result = detections[0] if detections else None
    names = getattr(getattr(result, "model", None), "names", None) or getattr(result, "names", {})
    boxes = getattr(result, "boxes", None)
    if boxes is not None:
        for cls_idx in boxes.cls.tolist():
            label = str(names.get(int(cls_idx), int(cls_idx))) if isinstance(names, dict) else str(int(cls_idx))
            counts[label] = counts.get(label, 0) + 1
            if label == "person":
                people += 1
    salient = [label for label, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)][:TOP_K_OBJECTS]
    return {
        "setting": _infer_setting(salient),
        "people_present": people,
        "salient_objects": salient,
        "text_present": False,
        "model": model_name,
    }


def _infer_setting(salient_objects: list[str]) -> str:  # pragma: no cover - off-CI
    """Coarse setting heuristic from detected classes (honest v1; #16 flywheel input)."""
    transit_cues = {"car", "bus", "train", "truck", "bicycle", "motorcycle"}
    indoor_cues = {"chair", "couch", "bed", "tv", "laptop", "keyboard", "dining table"}
    if any(o in transit_cues for o in salient_objects):
        return "transit"
    if any(o in indoor_cues for o in salient_objects):
        return "indoor"
    if salient_objects:
        return "outdoor"
    return "unknown"


def _ocr_has_text(image: Any) -> bool:  # pragma: no cover - off-CI, optional OCR
    """Optional OCR pass: True if any text is found. Lazy + best-effort."""
    try:
        import pytesseract
    except ImportError:
        return False
    return bool(pytesseract.image_to_string(image).strip())
