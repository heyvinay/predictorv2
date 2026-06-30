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
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.models.fixture import MatchStatus

logger = logging.getLogger(__name__)


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


@dataclass
class KnockoutSplit:
    """Per-period score split parsed from an ESPN summary endpoint."""

    home_reg: int
    away_reg: int
    home_et: int | None
    away_et: int | None
    home_pen: int | None
    away_pen: int | None


# status.type.name overrides; anything else is decided by status.type.state
# (pre → SCHEDULED, in → LIVE). 'post' states are handled by the caller —
# finished matches are skipped entirely so Football-Data lands the final.
_STATUS_NAME_MAP = {
    "STATUS_HALFTIME": MatchStatus.HALFTIME,
}

_REGULATION_PERIODS = 2
_PAST_REGULATION_STATUS_MARKERS = ("EXTRA", "OVERTIME", "SHOOTOUT", "PEN", "AET")


def _linescore_int(entry: Any) -> int:
    """Parse one period's score from an ESPN linescore entry (dict or int)."""
    if isinstance(entry, dict):
        dv = entry.get("displayValue")
        if dv is not None:
            return int(str(dv))
        val = entry.get("value")
        if val is not None:
            return int(val)
    raise ValueError(f"unparseable linescore entry: {entry!r}")


def _parse_side(competitor: dict[str, Any]) -> dict[str, Any] | None:
    """Extract reg/ET/pen totals from one competitor's linescores list.

    Returns None if data is absent, malformed, or internally inconsistent.
    The caller must treat None as 'enrichment unavailable'.
    """
    raw = competitor.get("linescores")
    if not isinstance(raw, list) or len(raw) < _REGULATION_PERIODS:
        return None
    try:
        vals = [_linescore_int(e) for e in raw]
    except (ValueError, TypeError):
        return None
    if any(v < 0 for v in vals):
        return None

    shootout = competitor.get("shootoutScore")
    has_pen = shootout is not None
    if has_pen:
        if len(vals) <= _REGULATION_PERIODS:
            return None
        pen = vals[-1]
        play = vals[:-1]
    else:
        pen = None
        play = vals

    if len(play) < _REGULATION_PERIODS:
        return None

    reg = sum(play[:_REGULATION_PERIODS])
    went_past_reg = has_pen or len(play) > _REGULATION_PERIODS
    et = sum(play) if went_past_reg else None

    score_total: int | None = None
    raw_score = competitor.get("score")
    if raw_score is not None:
        try:
            score_total = int(str(raw_score))
        except (ValueError, TypeError):
            return None

    pen_reported: int | None = None
    if has_pen:
        try:
            pen_reported = int(shootout)
        except (ValueError, TypeError):
            return None

    return {
        "reg": reg,
        "et": et,
        "pen": pen,
        "score_total": score_total,
        "pen_reported": pen_reported,
    }


def parse_summary_split(summary: dict[str, Any]) -> KnockoutSplit | None:
    """Parse regulation + ET + penalty splits from an ESPN summary response.

    Returns None when:
    - The summary structure is missing/malformed
    - Linescores are absent or inconsistent with the reported score total
    - Both sides have the same penalty count (unresolvable shootout)
    """
    try:
        comp = summary["header"]["competitions"][0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    except (KeyError, IndexError, TypeError):
        return None

    home_c, away_c = sides.get("home"), sides.get("away")
    if not home_c or not away_c:
        return None

    home, away = _parse_side(home_c), _parse_side(away_c)
    if home is None or away is None:
        return None

    # Both sides must agree on whether pens happened
    if (home["pen"] is None) != (away["pen"] is None):
        return None

    if home["pen"] is not None:
        # Tied shootout is unresolvable — leave for admin
        if home["pen"] == away["pen"]:
            return None
        # Linescore pen count must match the reported shootoutScore
        if home["pen"] != home["pen_reported"] or away["pen"] != away["pen_reported"]:
            return None

    # ET total must match reported score total (sanity check)
    for side in (home, away):
        if (
            side["et"] is not None
            and side["score_total"] is not None
            and side["et"] != side["score_total"]
        ):
            return None

    return KnockoutSplit(
        home_reg=home["reg"],
        away_reg=away["reg"],
        home_et=home["et"],
        away_et=away["et"],
        home_pen=home["pen"],
        away_pen=away["pen"],
    )


def competition_past_regulation(competition: dict[str, Any]) -> bool:
    """Return True if this competition dict indicates the match has gone past 90'."""
    competitors = competition.get("competitors") or []
    if any(c.get("shootoutScore") is not None for c in competitors):
        return True
    status = competition.get("status") or {}
    period = status.get("period")
    if isinstance(period, (int, float)) and period > _REGULATION_PERIODS:
        return True
    name = (status.get("type") or {}).get("name") or ""
    return any(marker in name for marker in _PAST_REGULATION_STATUS_MARKERS)


def map_event_status(status_type: dict[str, Any]) -> MatchStatus | None:
    """Map ESPN's status.type to our MatchStatus.

    For 'post' state: returns FINISHED only when the event is marked
    completed — abandoned/postponed posts are not a result and return None.
    Pre/in-play states are returned as SCHEDULED/LIVE/HALFTIME. None means
    'skip this event'.
    """
    name = status_type.get("name", "")
    state = status_type.get("state", "")
    if state == "post":
        return MatchStatus.FINISHED if status_type.get("completed") else None
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

    async def get_summary(self, league_slug: str, event_id: str) -> dict[str, Any]:
        """GET /{league}/summary?event={id} → full match summary with linescores."""
        url = f"{BASE_URL}/{league_slug}/summary"
        params = {"event": event_id}
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

            return dict(resp.json())

        raise EspnError(f"Exhausted retries for {url}; last error: {last_exc}")
