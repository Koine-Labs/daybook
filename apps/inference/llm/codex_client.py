"""Codex backend client — POSTs to chatgpt.com/backend-api/codex/responses.

Uses the OAuth-with-ChatGPT credentials from ~/.daybook/auth.json. Streams SSE
responses, extracts text or structured output. Mirrors funda's TypeScript
implementation; same headers, same body shape.
"""
from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Type, TypeVar

import httpx
from pydantic import BaseModel

from .auth.session import get_valid_access_token

logger = logging.getLogger(__name__)

CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
DEBUG_DUMP_PATH = Path(tempfile.gettempdir()) / "daybook-codex-last-response.json"

# Keys to strip from JSON schemas (Codex doesn't like JSON Schema meta-keys)
STRIP_SCHEMA_KEYS = {"$schema", "$id", "$ref", "title", "definitions", "$defs"}

T = TypeVar("T", bound=BaseModel)


class CodexError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Codex API error {status}: {body[:500]}")
        self.status = status
        self.body = body


@dataclass
class CodexTextResult:
    text: str
    model: str
    raw_usage: dict[str, Any] | None = None


@dataclass
class CodexStructuredResult:
    data: BaseModel
    model: str
    raw_usage: dict[str, Any] | None = None


def call_codex_text(
    *,
    system: str,
    user: str,
    model: str,
    reasoning_effort: str = "medium",
    verbosity: str = "medium",
    timeout: float = 120.0,
) -> CodexTextResult:
    """Free-form text response. No JSON schema constraint."""
    body = _build_body(
        system=system,
        user=user,
        model=model,
        schema_block=None,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
    )
    final_response, delta_text = _post_and_stream(body, timeout=timeout)
    text = _extract_text(final_response, delta_text)
    usage = _extract_usage(final_response)
    return CodexTextResult(text=text, model=model, raw_usage=usage)


def call_codex_structured(
    *,
    system: str,
    user: str,
    model: str,
    schema_model: Type[T],
    schema_name: str | None = None,
    reasoning_effort: str = "medium",
    verbosity: str = "medium",
    timeout: float = 180.0,
) -> CodexStructuredResult:
    """JSON-schema-constrained response, parsed back into the Pydantic model."""
    name = schema_name or schema_model.__name__
    raw_schema = schema_model.model_json_schema()
    cleaned_schema = _strip_schema_meta(raw_schema)
    schema_block = {
        "type": "json_schema",
        "name": name,
        "schema": cleaned_schema,
        "strict": True,
    }
    body = _build_body(
        system=system,
        user=user,
        model=model,
        schema_block=schema_block,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
    )
    final_response, delta_text = _post_and_stream(body, timeout=timeout)
    text = _extract_text(final_response, delta_text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        _dump_for_debug(final_response, delta_text, raw_text=text)
        raise RuntimeError(
            f"Codex returned text but it was not valid JSON: {e}. "
            f"First 300 chars: {text[:300]}. Full response at {DEBUG_DUMP_PATH}."
        ) from e
    validated = schema_model.model_validate(parsed)
    usage = _extract_usage(final_response)
    return CodexStructuredResult(data=validated, model=model, raw_usage=usage)


def _build_body(
    *,
    system: str,
    user: str,
    model: str,
    schema_block: dict | None,
    reasoning_effort: str,
    verbosity: str,
) -> dict:
    text_block: dict[str, Any] = {"verbosity": verbosity}
    if schema_block is not None:
        text_block["format"] = schema_block

    return {
        "model": model,
        "instructions": system,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user,
                    }
                ],
            }
        ],
        "text": text_block,
        "reasoning": {
            "effort": reasoning_effort,
            "summary": "auto",
        },
        "include": ["reasoning.encrypted_content"],
        "store": False,
        "stream": True,
    }


def _post_and_stream(body: dict, *, timeout: float) -> tuple[Any, str]:
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


def _extract_text(response: Any, delta_text: str) -> str:
    if delta_text:
        return delta_text

    if not isinstance(response, dict):
        raise RuntimeError("Codex response was not an object")

    err = response.get("error")
    if isinstance(err, dict) and err.get("message"):
        raise RuntimeError(f"Codex returned error: {err['message']}")

    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text
    if isinstance(output_text, list) and output_text:
        return "".join(s for s in output_text if isinstance(s, str))

    messages = [
        item
        for item in (response.get("output") or [])
        if isinstance(item, dict) and (item.get("type") == "message" or item.get("role") == "assistant")
    ]
    for msg in messages:
        for content in msg.get("content") or []:
            if not isinstance(content, dict):
                continue
            refusal = content.get("refusal")
            if isinstance(refusal, str) and refusal:
                raise RuntimeError(f"Codex refused: {refusal}")
            text = content.get("text")
            if isinstance(text, str) and text:
                return text
            ot = content.get("output_text")
            if isinstance(ot, str) and ot:
                return ot

    raise RuntimeError("Codex response did not include any text output")


def _extract_usage(response: Any) -> dict[str, Any] | None:
    if isinstance(response, dict):
        usage = response.get("usage")
        if isinstance(usage, dict):
            return usage
    return None


def _strip_schema_meta(node: Any) -> Any:
    if isinstance(node, list):
        return [_strip_schema_meta(item) for item in node]
    if isinstance(node, dict):
        return {k: _strip_schema_meta(v) for k, v in node.items() if k not in STRIP_SCHEMA_KEYS}
    return node


def _dump_for_debug(response: Any, delta_text: str, *, raw_text: str | None = None) -> None:
    try:
        DEBUG_DUMP_PATH.write_text(
            json.dumps(
                {"response": response, "delta_text": delta_text, "raw_text": raw_text},
                indent=2,
                default=str,
            )
        )
    except Exception as e:
        logger.warning("Failed to write debug dump: %s", e)
