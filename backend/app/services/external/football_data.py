"""Shared Football-Data.org HTTP client.

Used by both fixture_sync (for seeding) and external_scores (for live scoring).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import get_settings
from app.models.fixture import MatchStatus


class FootballDataError(Exception):
    """Catch-all for Football-Data.org HTTP / parsing failures."""


class FootballDataAuthError(FootballDataError):
    """401 / 403 from Football-Data — bad or missing token."""


class FootballDataRateLimitError(FootballDataError):
    """429 from Football-Data after retry."""


_STATUS_MAP = {
    "SCHEDULED": MatchStatus.SCHEDULED,
    "TIMED": MatchStatus.SCHEDULED,
    "IN_PLAY": MatchStatus.LIVE,
    "EXTRA_TIME": MatchStatus.LIVE,
    "PENALTY_SHOOTOUT": MatchStatus.LIVE,
    "PAUSED": MatchStatus.HALFTIME,
    "FINISHED": MatchStatus.FINISHED,
    "AWARDED": MatchStatus.FINISHED,
    "POSTPONED": MatchStatus.POSTPONED,
    "SUSPENDED": MatchStatus.POSTPONED,
    "CANCELLED": MatchStatus.CANCELLED,
}


def map_status(api_status: str) -> MatchStatus:
    """Map a Football-Data status enum to our MatchStatus.

    Unknown values fall back to SCHEDULED with no warning — callers can
    log if they need stricter behaviour.
    """
    return _STATUS_MAP.get(api_status, MatchStatus.SCHEDULED)


class FootballDataClient:
    """Async HTTP wrapper for football-data.org/v4.

    Tournament-agnostic: caller provides competition codes (e.g. "WC").
    Reads token + base URL from app.config.Settings.
    """

    DEFAULT_TIMEOUT = 15.0
    MAX_RETRIES = 3
    BACKOFF_SECONDS = (1.0, 4.0, 9.0)

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        settings = get_settings()
        self._token = settings.football_data_token
        self._base = settings.football_data_base_url.rstrip("/")
        self._timeout = timeout
        self._headers = {"X-Auth-Token": self._token}

    async def get_competition(self, code: str) -> dict[str, Any]:
        """GET /v4/competitions/{code} — returns competition metadata."""
        return await self._request("GET", f"/competitions/{code}")

    async def get_matches(
        self,
        code: str,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /v4/competitions/{code}/matches — returns the list of matches.

        If status is provided (e.g. "LIVE,IN_PLAY,PAUSED"), filters server-side.
        """
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        payload = await self._request("GET", f"/competitions/{code}/matches", params=params)
        return list(payload.get("matches", []))

    async def get_match(self, match_id: str | int) -> dict[str, Any] | None:
        """GET /v4/matches/{id} — returns one match, or None on 404."""
        try:
            return await self._request("GET", f"/matches/{match_id}")
        except FootballDataError as exc:
            if "404" in str(exc):
                return None
            raise

    async def get_standings(self, code: str) -> list[dict[str, Any]]:
        """GET /v4/competitions/{code}/standings — group standings (v2.182.0).

        Returns the list of group tables. Each entry has shape:
            {"group": "Group A", "stage": "ALL", "type": "TOTAL",
             "table": [
                 {"position": 1, "team": {"name": "Mexico", ...},
                  "playedGames": 3, "won": 3, "draw": 0, "lost": 0,
                  "points": 9, "goalsFor": 7, "goalsAgainst": 1,
                  "goalDifference": 6},
                 ...
             ]}

        Used by the standings drift verifier as the primary trusted source.
        """
        payload = await self._request("GET", f"/competitions/{code}/standings")
        return list(payload.get("standings", []))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self._token:
            raise FootballDataAuthError("FOOTBALL_DATA_TOKEN is not set")

        url = f"{self._base}{path}"
        last_exc: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.request(method, url, headers=self._headers, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.BACKOFF_SECONDS[attempt])
                    continue
                raise FootballDataError(f"Network error after {self.MAX_RETRIES} attempts: {exc}") from exc

            if resp.status_code in (401, 403):
                raise FootballDataAuthError(f"HTTP {resp.status_code}: bad or missing FOOTBALL_DATA_TOKEN")

            if resp.status_code == 429:
                if attempt < self.MAX_RETRIES - 1:
                    reset = resp.headers.get("X-RequestCounter-Reset", "60")
                    try:
                        wait = float(reset)
                    except ValueError:
                        wait = 60.0
                    await asyncio.sleep(wait)
                    continue
                raise FootballDataRateLimitError("Rate limit exceeded after retry")

            if resp.status_code == 404:
                raise FootballDataError(f"HTTP 404 for {path}")

            if resp.status_code >= 400:
                raise FootballDataError(f"HTTP {resp.status_code} for {path}: {resp.text[:200]}")

            return resp.json()

        raise FootballDataError(f"Exhausted retries for {path}; last error: {last_exc}")
