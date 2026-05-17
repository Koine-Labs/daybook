"""Tests for JWT authentication."""

from __future__ import annotations

import time

import jwt
import pytest

TEST_SECRET = "test-secret-key"


def make_token(sub: str = "user-1", exp_offset: int = 3600, secret: str = TEST_SECRET) -> str:
    payload = {"sub": sub, "iss": "lullaby", "iat": int(time.time()), "exp": int(time.time()) + exp_offset}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_validate_valid_token():
    from auth import validate_token
    token = make_token(sub="user-42")
    user_id = validate_token(token, TEST_SECRET)
    assert user_id == "user-42"


def test_validate_expired_token():
    from auth import validate_token
    token = make_token(exp_offset=-100)
    with pytest.raises(Exception):
        validate_token(token, TEST_SECRET)


def test_validate_wrong_secret():
    from auth import validate_token
    token = make_token(secret="wrong-secret")
    with pytest.raises(Exception):
        validate_token(token, TEST_SECRET)


def test_validate_malformed_token():
    from auth import validate_token
    with pytest.raises(Exception):
        validate_token("not.a.jwt", TEST_SECRET)


def test_extract_token_from_header():
    from auth import extract_token_from_header
    token = extract_token_from_header("Bearer eyJhbGciOi")
    assert token == "eyJhbGciOi"


def test_extract_token_missing_bearer():
    from auth import extract_token_from_header
    assert extract_token_from_header("Basic abc123") is None
    assert extract_token_from_header("") is None
    assert extract_token_from_header(None) is None
