"""
Remote server client for downloading Lullaby sleep sessions.

Provides a CLI for authenticating with the Lullaby data collection server
and downloading session data to the local filesystem for analysis.

Usage:
    python -m lullaby.remote login --email user@example.com
    python -m lullaby.remote list
    python -m lullaby.remote download --all --output ./data/sessions/
    python -m lullaby.remote download --id <session-id> --output ./data/sessions/
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://lullaby-server.aakashjuly18.workers.dev"
TOKEN_PATH = Path.home() / ".lullaby" / "tokens.json"


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------

@dataclass
class StoredTokens:
    access_token: str
    refresh_token: str
    base_url: str

    def save(self) -> None:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(json.dumps({
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "base_url": self.base_url,
        }))
        TOKEN_PATH.chmod(0o600)

    @classmethod
    def load(cls) -> Optional["StoredTokens"]:
        if not TOKEN_PATH.exists():
            return None
        try:
            data = json.loads(TOKEN_PATH.read_text())
            return cls(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                base_url=data.get("base_url", DEFAULT_BASE_URL),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    @classmethod
    def clear(cls) -> None:
        if TOKEN_PATH.exists():
            TOKEN_PATH.unlink()


# ---------------------------------------------------------------------------
# Remote client
# ---------------------------------------------------------------------------

class RemoteClient:
    """HTTP client for the Lullaby data collection server."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self._tokens: Optional[StoredTokens] = None

        # Try to load cached tokens
        stored = StoredTokens.load()
        if stored and stored.base_url == self.base_url:
            self._tokens = stored
            self.session.headers["Authorization"] = f"Bearer {stored.access_token}"

    @property
    def is_authenticated(self) -> bool:
        return self._tokens is not None

    def login(self, email: str, password: str) -> dict:
        """Authenticate with email + password."""
        resp = self.session.post(
            f"{self.base_url}/auth/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        data = resp.json()

        self._tokens = StoredTokens(
            access_token=data["accessToken"],
            refresh_token=data["refreshToken"],
            base_url=self.base_url,
        )
        self._tokens.save()
        self.session.headers["Authorization"] = f"Bearer {data['accessToken']}"

        return data.get("user", {})

    def register(self, email: str, password: str, display_name: Optional[str] = None) -> dict:
        """Create a new account."""
        payload: dict = {"email": email, "password": password}
        if display_name:
            payload["displayName"] = display_name

        resp = self.session.post(
            f"{self.base_url}/auth/register",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        self._tokens = StoredTokens(
            access_token=data["accessToken"],
            refresh_token=data["refreshToken"],
            base_url=self.base_url,
        )
        self._tokens.save()
        self.session.headers["Authorization"] = f"Bearer {data['accessToken']}"

        return data.get("user", {})

    def refresh(self) -> None:
        """Refresh the access token using the stored refresh token."""
        if not self._tokens:
            raise RuntimeError("Not authenticated — run login first")

        resp = self.session.post(
            f"{self.base_url}/auth/refresh",
            json={"refreshToken": self._tokens.refresh_token},
        )
        resp.raise_for_status()
        data = resp.json()

        self._tokens = StoredTokens(
            access_token=data["accessToken"],
            refresh_token=data["refreshToken"],
            base_url=self.base_url,
        )
        self._tokens.save()
        self.session.headers["Authorization"] = f"Bearer {data['accessToken']}"

    def logout(self) -> None:
        """Revoke refresh token and clear cached tokens."""
        if self._tokens:
            try:
                self.session.post(
                    f"{self.base_url}/auth/logout",
                    json={"refreshToken": self._tokens.refresh_token},
                )
            except requests.RequestException:
                pass
        StoredTokens.clear()
        self._tokens = None
        self.session.headers.pop("Authorization", None)

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make an authenticated request, auto-refreshing on 401."""
        resp = self.session.request(method, f"{self.base_url}{path}", **kwargs)
        if resp.status_code == 401 and self._tokens:
            try:
                self.refresh()
                resp = self.session.request(method, f"{self.base_url}{path}", **kwargs)
            except requests.RequestException:
                raise RuntimeError("Session expired — run login again")
        resp.raise_for_status()
        return resp

    def list_sessions(self) -> list[dict]:
        """List all sessions for the authenticated user."""
        resp = self._request("GET", "/sessions")
        return resp.json().get("sessions", [])

    def download_session(self, session_id: str, output_dir: Path) -> Path:
        """Download a single session JSON to the output directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        resp = self._request("GET", f"/sessions/{session_id}/download", stream=True)

        output_path = output_dir / f"{session_id}.json"
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return output_path

    def download_all(self, output_dir: Path) -> list[Path]:
        """Download all sessions to the output directory."""
        sessions = self.list_sessions()
        paths = []
        for i, session in enumerate(sessions, 1):
            sid = session["id"]
            print(f"  [{i}/{len(sessions)}] Downloading {sid}...")
            path = self.download_session(sid, output_dir)
            size_mb = path.stat().st_size / (1024 * 1024)
            print(f"    → {path.name} ({size_mb:.1f} MB)")
            paths.append(path)
        return paths

    def me(self) -> dict:
        """Get current user profile."""
        resp = self._request("GET", "/users/me")
        return resp.json()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="lullaby.remote",
        description="Lullaby sleep session remote client",
    )
    parser.add_argument(
        "--server",
        default=DEFAULT_BASE_URL,
        help=f"Server base URL (default: {DEFAULT_BASE_URL})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # login
    login_p = sub.add_parser("login", help="Authenticate with email + password")
    login_p.add_argument("--email", required=True)

    # register
    reg_p = sub.add_parser("register", help="Create a new account")
    reg_p.add_argument("--email", required=True)
    reg_p.add_argument("--name", help="Display name")

    # logout
    sub.add_parser("logout", help="Sign out and clear cached tokens")

    # list
    sub.add_parser("list", help="List all sessions")

    # download
    dl_p = sub.add_parser("download", help="Download sessions")
    dl_p.add_argument("--id", help="Session ID to download")
    dl_p.add_argument("--all", action="store_true", help="Download all sessions")
    dl_p.add_argument(
        "--output", "-o",
        default="./data/sessions",
        help="Output directory (default: ./data/sessions)",
    )

    # me
    sub.add_parser("me", help="Show current user profile")

    args = parser.parse_args(argv)
    client = RemoteClient(base_url=args.server)

    if args.command == "login":
        password = getpass.getpass("Password: ")
        user = client.login(args.email, password)
        print(f"Logged in as {user.get('email', args.email)}")

    elif args.command == "register":
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match", file=sys.stderr)
            sys.exit(1)
        user = client.register(args.email, password, args.name)
        print(f"Registered and logged in as {user.get('email', args.email)}")

    elif args.command == "logout":
        client.logout()
        print("Logged out")

    elif args.command == "list":
        if not client.is_authenticated:
            print("Not authenticated — run 'login' first", file=sys.stderr)
            sys.exit(1)
        sessions = client.list_sessions()
        if not sessions:
            print("No sessions found")
            return
        print(f"{'ID':<38} {'Start Date':<22} {'Duration':>10} {'Packets':>8} {'Size':>10}")
        print("-" * 92)
        for s in sessions:
            duration = s.get("duration_seconds")
            dur_str = f"{duration / 3600:.1f}h" if duration else "—"
            size = s.get("size_bytes", 0)
            size_str = f"{size / (1024*1024):.1f} MB" if size else "—"
            print(
                f"{s['id']:<38} {s.get('start_date', '—'):<22} "
                f"{dur_str:>10} {s.get('watch_packet_count', 0):>8} {size_str:>10}"
            )

    elif args.command == "download":
        if not client.is_authenticated:
            print("Not authenticated — run 'login' first", file=sys.stderr)
            sys.exit(1)
        output = Path(args.output)
        if args.all:
            paths = client.download_all(output)
            print(f"\nDownloaded {len(paths)} sessions to {output}/")
        elif args.id:
            path = client.download_session(args.id, output)
            print(f"Downloaded to {path}")
        else:
            print("Specify --all or --id <session-id>", file=sys.stderr)
            sys.exit(1)

    elif args.command == "me":
        if not client.is_authenticated:
            print("Not authenticated — run 'login' first", file=sys.stderr)
            sys.exit(1)
        profile = client.me()
        print(f"User: {profile.get('email', '?')}")
        print(f"Name: {profile.get('displayName', '—')}")
        print(f"Role: {profile.get('role', 'user')}")
        print(f"Provider: {profile.get('authProvider', '—')}")
        print(f"Created: {profile.get('createdAt', '—')}")


if __name__ == "__main__":
    main()
