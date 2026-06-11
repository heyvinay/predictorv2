"""ESPN public scoreboard client — unofficial JSON API, no auth required.

Primary LIVE score source: ESPN's site API updates in-play scores in near
real time, while Football-Data.org's free tier delivers them with a delay.
The endpoint is the same one every espn.com browser tab polls, so our one
request per minute during match windows is negligible traffic.

Role split (see external_scores.get_score_provider): ESPN paints live
scores only — finished matches are deliberately NOT emitted here, so the
final result always lands via Football-Data's per-fixture resolution pass,
which carries the authoritative FT/ET/penalties split our scoring expects.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from app.models.fixture import MatchStatus


class EspnError(Exception):
    """Catch-all for ESPN HTTP / parsing failures."""


BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# Our competition rows store Football-Data codes ("WC"); map them to ESPN
# league slugs. Unknown codes fall back to the World Cup slug.
LEAGUE_SLUGS = {"WC": "fifa.world"}

# ESPN display names that differ from our canonical (Football-Data-seeded)
# fixture team names. Verified 2026-06-11 by diffing the full tournament
# scoreboard against the prod fixtures table — these were the only two of 48.
TEAM_NAME_ALIASES = {
    "Cape Verde": "Cape Verde Islands",
    "Türkiye": "Turkey",
}

# status.type.name overrides; anything else is decided by status.type.state
# (pre → SCHEDULED, in → LIVE). 'post' states are handled by the caller —
# finished matches are skipped entirely so Football-Data lands the final.
_STATUS_NAME_MAP = {
    "STATUS_HALFTIME": MatchStatus.HALFTIME,
}


def map_event_status(status_type: dict[str, Any]) -> MatchStatus | None:
    """Map ESPN's status.type to our MatchStatus.

    Returns None for 'post' states (final/abandoned/postponed): this provider
    only paints pre/in-play state, never terminal results.
    """
    name = status_type.get("name", "")
    state = status_type.get("state", "")
    if state == "post":
        return None
    if name in _STATUS_NAME_MAP:
        return _STATUS_NAME_MAP[name]
    if state == "in":
        return MatchStatus.LIVE
    return MatchStatus.SCHEDULED


def parse_minute(display_clock: str | None) -> int | None:
    """'45'' → 45, '90'+3'' → 90, garbage/empty → None."""
    if not display_clock:
        return None
    m = re.match(r"(\d+)", display_clock)
    return int(m.group(1)) if m else None


def canonical_team_name(espn_name: str) -> str:
    return TEAM_NAME_ALIASES.get(espn_name, espn_name)


class EspnClient:
    """Thin async wrapper over the scoreboard endpoint with light retries."""

    DEFAULT_TIMEOUT = 10.0
    MAX_RETRIES = 2
    BACKOFF_SECONDS = (1.0,)

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    async def get_scoreboard(self, league_slug: str, dates: str) -> list[dict[str, Any]]:
        """GET /{league}/scoreboard?dates=YYYYMMDD[-YYYYMMDD] → events list."""
        url = f"{BASE_URL}/{league_slug}/scoreboard"
        params = {"dates": dates, "limit": "200"}
        last_exc: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.BACKOFF_SECONDS[attempt])
                    continue
                raise EspnError(f"Network error after {self.MAX_RETRIES} attempts: {exc}") from exc

            if resp.status_code >= 400:
                raise EspnError(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")

            payload = resp.json()
            return list(payload.get("events", []))

        raise EspnError(f"Exhausted retries for {url}; last error: {last_exc}")
