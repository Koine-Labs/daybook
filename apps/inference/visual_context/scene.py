"""CLIP zero-shot scene classification."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_CLIP_MODEL = "openai/clip-vit-base-patch32"

DEFAULT_SCENE_LABELS = [
    "kitchen",
    "bedroom",
    "office",
    "living room",
    "bathroom",
    "outdoors",
    "park",
    "street",
    "car interior",
    "cafe",
    "restaurant",
    "gym",
    "store",
    "library",
    "classroom",
    "abstract art",
    "illustration",
    "logo or icon",
]

_processor: Any = None
_model: Any = None
_device: str | None = None


def _get_clip() -> tuple[Any, Any, str]:
    """Lazy-load CLIP processor + model. Picks MPS/CUDA/CPU."""
    global _processor, _model, _device
    if _model is None:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        if torch.cuda.is_available():
            _device = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            _device = "mps"
        else:
            _device = "cpu"
        logger.info("Loading CLIP model %s on %s", DEFAULT_CLIP_MODEL, _device)
        _processor = CLIPProcessor.from_pretrained(DEFAULT_CLIP_MODEL)
        loaded = CLIPModel.from_pretrained(DEFAULT_CLIP_MODEL).to(_device)
        loaded.requires_grad_(False)
        # Inference-only mode.
        loaded.train(False)
        _model = loaded
    return _processor, _model, _device  # type: ignore[return-value]


def _to_pil(image: np.ndarray | Path | str) -> Image.Image:
    if isinstance(image, (str, Path)):
        return Image.open(str(image)).convert("RGB")
    if image.ndim == 3 and image.shape[2] == 3:
        return Image.fromarray(image)
    if image.ndim == 3 and image.shape[2] == 4:
        return Image.fromarray(image).convert("RGB")
    return Image.fromarray(image).convert("RGB")


def classify_scene(
    image: np.ndarray | Path | str,
    *,
    candidate_labels: list[str] | None = None,
    top_k: int = 5,
) -> dict:
    """Returns {scene, confidence, alternatives}."""
    import torch

    labels = candidate_labels or DEFAULT_SCENE_LABELS
    processor, model, device = _get_clip()
    pil = _to_pil(image)

    prompts = [f"a photo of a {label}" for label in labels]
    inputs = processor(text=prompts, images=pil, return_tensors="pt", padding=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        logits_per_image = outputs.logits_per_image
        probs = logits_per_image.softmax(dim=-1)[0].cpu().numpy()

    ranked = sorted(zip(labels, probs.tolist()), key=lambda kv: kv[1], reverse=True)
    top = ranked[0]
    alternatives = [(label, float(p)) for label, p in ranked[1:top_k]]
    return {
        "scene": top[0],
        "confidence": float(top[1]),
        "alternatives": alternatives,
    }
