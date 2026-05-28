"""End-to-end smoke test: starts uvicorn on a random port, hits each endpoint.

Run from apps/ with the venv active:
    cd apps && source inference/.venv/bin/activate
    python -m api.smoke_test

The test creates a few rows (conversation, message, dream) and prints what each
endpoint returned. It does NOT clean up created rows — they're useful artifacts
for manual inspection.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _request(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return r.status, _maybe_json(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, _maybe_json(raw)


def _maybe_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _wait_for_health(base: str, deadline_s: float = 90.0) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < deadline_s:
        try:
            code, body = _request("GET", f"{base}/health", timeout=3.0)
            if code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _print_response(label: str, code: int, body: Any) -> None:
    print(f"\n=== {label} ===")
    print(f"HTTP {code}")
    if isinstance(body, (dict, list)):
        print(json.dumps(body, indent=2, default=str)[:1200])
    else:
        print(str(body)[:1200])


def main() -> int:
    api_dir = Path(__file__).resolve().parent
    apps_dir = api_dir.parent
    port = _free_port()
    base = f"http://127.0.0.1:{port}"

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    print(f"Starting uvicorn: {' '.join(cmd)} (cwd={apps_dir})")
    proc = subprocess.Popen(cmd, cwd=str(apps_dir))

    try:
        if not _wait_for_health(base):
            print("FAIL: uvicorn never became healthy.")
            return 1

        code, body = _request("GET", f"{base}/")
        _print_response("GET /", code, body)

        code, body = _request("GET", f"{base}/health")
        _print_response("GET /health", code, body)

        code, conv = _request(
            "POST",
            f"{base}/chat/conversations",
            body={"title": "api smoke test"},
        )
        _print_response("POST /chat/conversations", code, conv)
        conv_id = conv["id"] if isinstance(conv, dict) else None

        code, body = _request("GET", f"{base}/chat/conversations?limit=5")
        _print_response("GET /chat/conversations", code, body)

        if conv_id:
            code, msg = _request(
                "POST",
                f"{base}/chat/conversations/{conv_id}/messages",
                body={"text": "Quick smoke ping — just confirming you're online."},
                timeout=180.0,
            )
            _print_response(f"POST /chat/conversations/{conv_id}/messages", code, msg)

            code, body = _request(
                "GET",
                f"{base}/chat/conversations/{conv_id}/messages?limit=10",
            )
            _print_response(
                f"GET /chat/conversations/{conv_id}/messages", code, body
            )

        code, dream = _request(
            "POST",
            f"{base}/recall",
            body={
                "text": "Smoke test dream: I was floating in a quiet library, the books all hummed.",
                "ack": False,
            },
            timeout=180.0,
        )
        _print_response("POST /recall (text, ack=False)", code, dream)
        dream_id = dream["dream_recall_id"] if isinstance(dream, dict) else None

        code, body = _request("GET", f"{base}/dreams?limit=5")
        _print_response("GET /dreams", code, body)

        code, body = _request(
            "GET", f"{base}/dreams?q=library%20books%20humming&limit=3"
        )
        _print_response("GET /dreams?q=...", code, body)

        if dream_id:
            code, body = _request("GET", f"{base}/dreams/{dream_id}")
            _print_response(f"GET /dreams/{dream_id}", code, body)

        code, body = _request("GET", f"{base}/sessions?limit=3")
        _print_response("GET /sessions", code, body)

        session_id: str | None = None
        if isinstance(body, dict) and body.get("sessions"):
            session_id = body["sessions"][0]["id"]
            code, sbody = _request("GET", f"{base}/sessions/{session_id}")
            _print_response(f"GET /sessions/{session_id}", code, sbody)

        code, body = _request("GET", f"{base}/observations?limit=5")
        _print_response("GET /observations", code, body)

        code, body = _request("GET", f"{base}/persona")
        if isinstance(body, dict) and "content" in body:
            body = {
                **body,
                "content": body["content"][:200] + ("..." if len(body["content"]) > 200 else ""),
            }
        _print_response("GET /persona", code, body)

        code, body = _request(
            "POST",
            f"{base}/compose",
            body={
                "moment_kind": "morning_recall_prompt",
                "explicit_context": "Smoke test — light morning prompt, do not retrieve heavily.",
                "retrieval_top_k": 2,
                "persist": False,
            },
            timeout=180.0,
        )
        _print_response("POST /compose", code, body)

        print("\n=== SMOKE TEST DONE ===")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
