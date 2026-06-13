"""Application configuration and settings."""

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Tournament + engagement-cohort constants (v2.176.0)
# ---------------------------------------------------------------------------
# Tournament kickoff anchor — World Cup 2026. 21:00 Malta CEST = 19:00 UTC.
# Used by the broadcast-cohort engagement signal to identify Pool Ghost
# (users with no engagement since this timestamp) and to bound Lapsing-
# window comparisons.
TOURNAMENT_START: datetime = datetime(2026, 6, 11, 19, 0, 0, tzinfo=timezone.utc)

# Lapsing-cohort window — rolling, in days.
LAPSING_FRESH_DAYS: int = 3   # ≤ this many days since last activity → not lapsing
LAPSING_STALE_DAYS: int = 7   # > this many days → graduates to Pool Ghost

# Throttle for the User.last_seen_at write in get_current_user. The dep
# only fires the UPDATE if the column is older than this. At ~100 users
# with 5-minute throttling the write rate is ~10-100/day — invisible
# against the existing background load.
LAST_SEEN_THROTTLE_S: int = 5 * 60


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

    # The Odds API (Smart Fill — Betting Odds method). Plan §9: shared
    # server-side cache with a 4h TTL at /data/odds_cache.json. Empty key
    # → odds_cache.get_or_refresh_odds() returns {error: 'not_configured'}
    # and the frontend modal disables the Betting Odds radio.
    odds_api_key: str = ""

    # Tournament config
    tournament_config_path: str = "config/worldcup2026.yml"

    # PostHog analytics — write side (existing).
    posthog_api_key: str = ""
    posthog_host: str = "https://eu.i.posthog.com"
    # PostHog analytics — read side (v2.156.0, admin engagement card).
    # Personal API key (phx_*) with "Read project events" scope; project
    # id is the numeric id from the PostHog URL. If either is empty the
    # read service short-circuits to "PostHog disabled" mode and the
    # frontend renders graceful "—" placeholders on the engagement card.
    posthog_personal_api_key: str = ""
    posthog_project_id: str = ""

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
