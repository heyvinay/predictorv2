"""Application configuration and settings."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "Predictor v2"
    debug: bool = False
    api_prefix: str = "/api"

    # Database
    database_url: PostgresDsn
    database_echo: bool = False

    # JWT Auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # Magic-link (passwordless) auth
    # Frontend URL used both as the redirect target after verify, AND as the
    # base for the link in the outgoing email (link goes to
    # {frontend_url}/api/auth/verify-magic-link?token=... which the Vite
    # proxy / nginx forwards to the backend).
    frontend_url: str = "http://localhost:5173"
    magic_link_expire_minutes: int = 15

    # Resend (email delivery for magic links).
    # Leave resend_api_key empty in dev — the service will log the link to
    # stdout instead of sending an email.
    resend_api_key: str = ""
    resend_from_email: str = "Atlas World Cup 2026 Pools <noreply@resend.dev>"

    # Cloudflare Turnstile (sign-in CAPTCHA). Leave empty in dev — the
    # verifier short-circuits to success so local sign-in needs no widget.
    turnstile_secret_key: str = ""

    # Football-Data.org
    football_data_token: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"

    # Tournament config
    tournament_config_path: str = "config/worldcup2026.yml"

    # PostHog analytics
    posthog_api_key: str = ""
    posthog_host: str = "https://eu.i.posthog.com"

    # CORS - stored as string, parsed via computed property
    cors_origins_str: str = "http://localhost:5173,http://localhost:3000"

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from string."""
        v = self.cors_origins_str.strip()
        # Handle JSON array format: ["url1", "url2"]
        if v.startswith("["):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                pass
        # Handle comma-separated format: url1,url2
        return [origin.strip() for origin in v.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def load_tournament_config(path: str | None = None) -> dict[str, Any]:
    """Load tournament configuration from YAML file."""
    settings = get_settings()
    config_path = Path(path or settings.tournament_config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Tournament config not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)


@lru_cache
def get_tournament_config() -> dict[str, Any]:
    """Get cached tournament configuration."""
    return load_tournament_config()
