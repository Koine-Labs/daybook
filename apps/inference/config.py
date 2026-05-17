"""Inference server configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    jwt_secret: str
    model_path: str = "models"
    cloudflare_api_url: str = ""
    model_url: str = ""
    env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_prefix": "", "case_sensitive": False}
