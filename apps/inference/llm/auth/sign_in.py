"""Standalone CLI: run the OAuth flow, write ~/.daybook/auth.json.

Usage:
    cd apps/inference && source .venv/bin/activate
    python -m llm.auth.sign_in

Opens your browser to authorize, runs a local server on :1455 to catch the
callback, exchanges the code for tokens, persists them.
"""
from __future__ import annotations

import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .jwt import decode_identity_from_id_token
from .oauth import build_authorize_url, exchange_authorization_code, generate_pkce, generate_state
from .storage import PersistedAuth, now_epoch, write_auth


CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 1455
CALLBACK_PATH = "/auth/callback"
TIMEOUT_SECONDS = 5 * 60

SUCCESS_HTML = b"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Daybook \xe2\x80\x94 signed in</title>
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
        background: #0a0f15; color: #e5e7eb; display: flex; align-items: center;
        justify-content: center; min-height: 100vh; margin: 0; }
      .card { background: #111827; border: 1px solid #1f2937; border-radius: 12px;
        padding: 32px 40px; max-width: 420px; }
      h1 { font-size: 18px; margin: 0 0 8px; font-weight: 600; color: #f59e0b; }
      p { font-size: 14px; line-height: 1.5; color: #9ca3af; margin: 0 0 4px; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Signed in to Daybook</h1>
      <p>Your ChatGPT subscription is now connected.</p>
      <p>You can close this tab and return to the terminal.</p>
    </div>
  </body>
</html>
"""


@dataclass
class CallbackResult:
    code: str
    state: str


class _Handler(BaseHTTPRequestHandler):
    expected_state: str = ""
    result: CallbackResult | None = None
    error: str | None = None
    callback_event: threading.Event | None = None

    def log_message(self, *args, **_kwargs):  # silence default access log
        pass

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        parsed = urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        params = parse_qs(parsed.query)
        state = (params.get("state") or [None])[0]
        code = (params.get("code") or [None])[0]
        err = (params.get("error") or [None])[0]

        if err:
            _Handler.error = f"OAuth error: {err}"
            self._respond_error(400, f"OAuth error: {err}")
            return
        if not state or state != _Handler.expected_state:
            _Handler.error = "OAuth state mismatch"
            self._respond_error(400, "State mismatch")
            return
        if not code:
            _Handler.error = "Missing authorization code"
            self._respond_error(400, "Missing authorization code")
            return

        _Handler.result = CallbackResult(code=code, state=state)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(SUCCESS_HTML)))
        self.end_headers()
        self.wfile.write(SUCCESS_HTML)

        if _Handler.callback_event:
            _Handler.callback_event.set()

    def _respond_error(self, status: int, message: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))
        if _Handler.callback_event:
            _Handler.callback_event.set()


def run() -> int:
    pkce = generate_pkce()
    state = generate_state()
    authorize_url = build_authorize_url(challenge=pkce.challenge, state=state)

    _Handler.expected_state = state
    _Handler.result = None
    _Handler.error = None
    event = threading.Event()
    _Handler.callback_event = event

    server = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"Opening browser to authorize...\n  {authorize_url}\n")
    try:
        webbrowser.open(authorize_url)
    except Exception:
        print("Could not open browser automatically. Open the URL above manually.")

    print(f"Waiting for callback on {CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH} ...")
    completed = event.wait(timeout=TIMEOUT_SECONDS)
    server.shutdown()
    server.server_close()

    if not completed:
        print("Timed out waiting for OAuth callback.", file=sys.stderr)
        return 1
    if _Handler.error:
        print(f"OAuth error: {_Handler.error}", file=sys.stderr)
        return 1
    if _Handler.result is None:
        print("No callback received.", file=sys.stderr)
        return 1

    result = _Handler.result
    print("Exchanging authorization code for tokens...")
    tokens = exchange_authorization_code(code=result.code, verifier=pkce.verifier)
    if not tokens.id_token:
        print("Token response missing id_token.", file=sys.stderr)
        return 1

    identity = decode_identity_from_id_token(tokens.id_token)
    persisted = PersistedAuth(tokens=tokens, identity=identity, signed_in_at=now_epoch())
    write_auth(persisted)

    print(f"\nSigned in as {identity.email or identity.account_id}")
    print(f"  account_id: {identity.account_id}")
    print(f"  tokens persisted at ~/.daybook/auth.json (mode 0600)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
