"""OAuth + token storage for Sign-in-with-ChatGPT.

The flow mirrors what Codex CLI / opencode / funda do:
  - PKCE OAuth against auth.openai.com (CLIENT_ID and params from Codex CLI's flow)
  - Local callback server on 127.0.0.1:1455 to capture the redirect
  - Tokens persisted to ~/.daybook/auth.json (0600), refresh on demand
  - id_token decoded for chatgpt_account_id (required as header on Codex calls)

NOT officially documented by OpenAI as supported for arbitrary third-party
apps. Works today (same path as Codex CLI). May break if OpenAI moves.
"""

from .oauth import PkcePair, TokenSet, build_authorize_url, exchange_authorization_code, generate_pkce, generate_state, refresh_access_token
from .jwt import ChatGptIdentity, decode_identity_from_id_token
from .storage import PersistedAuth, read_auth, write_auth, clear_auth
from .session import get_valid_access_token, get_sign_in_status, sign_out

__all__ = [
    "PkcePair",
    "TokenSet",
    "ChatGptIdentity",
    "PersistedAuth",
    "build_authorize_url",
    "exchange_authorization_code",
    "generate_pkce",
    "generate_state",
    "refresh_access_token",
    "decode_identity_from_id_token",
    "read_auth",
    "write_auth",
    "clear_auth",
    "get_valid_access_token",
    "get_sign_in_status",
    "sign_out",
]
