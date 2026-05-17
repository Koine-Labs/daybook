"""Tests for inference server configuration."""

from __future__ import annotations

import pytest


def test_config_loads_defaults():
    from config import Settings
    settings = Settings(jwt_secret="test-secret")
    assert settings.jwt_secret == "test-secret"
    assert settings.model_path == "models"
    assert settings.env == "dev"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "env-secret")
    monkeypatch.setenv("MODEL_PATH", "/custom/models")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CLOUDFLARE_API_URL", "https://example.com")
    from config import Settings
    settings = Settings()
    assert settings.jwt_secret == "env-secret"
    assert settings.model_path == "/custom/models"
    assert settings.env == "production"
    assert settings.cloudflare_api_url == "https://example.com"


def test_config_requires_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    from config import Settings
    with pytest.raises(Exception):
        Settings()
