"""Multimodal LLM client — describes an image via Codex `input_image` content.

Reuses the SSE streaming and response parsing from `codex_client.py`. The
Codex `responses` endpoint may or may not have multimodal enabled on the
consumer ChatGPT plan; we try once and raise `VisionNotAvailableError` if it
refuses an image input so callers can fall back gracefully.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from .auth.session import get_valid_access_token
from .codex_client import (
    CODEX_URL,
    CodexError,
    _extract_text,
)

logger = logging.getLogger(__name__)

DEFAULT_VISION_MODEL = "gpt-5.2"
DEFAULT_VISION_PROMPT = "Describe what's in this image in 1-2 sentences. Be concrete."


class VisionNotAvailableError(RuntimeError):
    """Codex multimodal input was rejected. Caller should fall back."""


def describe_image(
    *,
    image_path: Path | str | None = None,
    image_bytes: bytes | None = None,
    prompt: str = DEFAULT_VISION_PROMPT,
    model: str = DEFAULT_VISION_MODEL,
    reasoning_effort: str = "low",
    verbosity: str = "low",
    timeout: float = 60.0,
) -> str:
    """Describe an image via multimodal LLM call.

    Either `image_path` or `image_bytes` must be provided. The image is
    base64-encoded inline as a data URL on the Codex request body.
    """
    if image_bytes is None and image_path is None:
        raise ValueError("Either image_path or image_bytes is required")

    if image_bytes is None:
        path = Path(image_path)  # type: ignore[arg-type]
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        image_bytes = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    else:
        mime = "image/jpeg"

    data_url = _to_data_url(image_bytes, mime=mime)
    body = _build_vision_body(
        prompt=prompt,
        data_url=data_url,
        model=model,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
    )

    try:
        final_response, delta_text = _post_and_stream(body, timeout=timeout)
    except CodexError as e:
        if _looks_like_multimodal_refusal(e):
            logger.warning(
                "Codex multimodal not available — vision features need Gateway+API key"
            )
            raise VisionNotAvailableError(
                f"Codex backend rejected `input_image` content "
                f"(status={e.status}, body snippet={e.body[:200]!r})"
            ) from e
        raise

    text = _extract_text(final_response, delta_text)
    return text.strip()


def _to_data_url(image_bytes: bytes, *, mime: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _build_vision_body(
    *,
    prompt: str,
    data_url: str,
    model: str,
    reasoning_effort: str,
    verbosity: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": (
            "You are a concise visual describer. Given an image, return a brief, "
            "concrete description in plain prose. No preamble."
        ),
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
        "text": {"verbosity": verbosity},
        "reasoning": {"effort": reasoning_effort, "summary": "auto"},
        "include": ["reasoning.encrypted_content"],
        "store": False,
        "stream": True,
    }


def _post_and_stream(body: dict, *, timeout: float) -> tuple[Any, str]:
    """Local copy of codex_client._post_and_stream — vision shares the SSE shape."""
    import json

    token = get_valid_access_token()
    headers = {
        "Authorization": f"Bearer {token.access_token}",
        "chatgpt-account-id": token.identity.account_id,
        "OpenAI-Beta": "responses=experimental",
        "originator": "codex_cli_rs",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    final_response: Any = None
    delta_text = ""

    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", CODEX_URL, headers=headers, json=body) as res:
            if res.status_code != 200:
                full_body = res.read().decode("utf-8", errors="replace")
                raise CodexError(res.status_code, full_body)

            for raw_line in res.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload:
                    continue
                try:
                    evt = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                evt_type = evt.get("type")
                if evt_type in ("response.done", "response.completed"):
                    final_response = evt.get("response", evt)
                elif evt_type == "response.output_text.delta":
                    delta = evt.get("delta")
                    if isinstance(delta, str):
                        delta_text += delta
                elif evt_type == "response.output_text.done":
                    final_text = evt.get("text")
                    if isinstance(final_text, str):
                        delta_text = final_text

    if final_response is None and not delta_text:
        raise RuntimeError("Codex SSE stream ended without response.done or text deltas")

    return final_response, delta_text


def _looks_like_multimodal_refusal(err: CodexError) -> bool:
    """Heuristic: a 4xx whose body mentions image/multimodal/input_image."""
    if err.status not in (400, 415, 422):
        return False
    body_lower = err.body.lower()
    needles = ("image", "input_image", "multimodal", "unsupported content", "image_url")
    return any(n in body_lower for n in needles)
