"""External score fetching service.

Two providers with one job each:
  - ESPN (unofficial public JSON) paints LIVE in-play scores — near
    real-time, no auth, but never emits finished matches.
  - Football-Data.org is the authoritative finisher (proper FT/ET/pens
    split via score_sync's per-fixture resolution pass) and the bulk
    fallback if ESPN errors on a tick.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta

from app.models._datetime import utc_now
from app.models.fixture import MatchStatus
from app.services.external.espn import (
    LEAGUE_SLUGS,
    EspnClient,
    canonical_team_name,
    map_event_status,
    parse_minute,
)
from app.services.external.football_data import FootballDataClient, map_status


logger = logging.getLogger(__name__)


@dataclass
class ExternalScore:
    """Score data from external API."""

    external_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    status: MatchStatus
    minute: int | None = None
    home_score_et: int | None = None
    away_score_et: int | None = None
    home_penalties: int | None = None
    away_penalties: int | None = None


class ScoreProviderBase(ABC):
    """Base class for score providers (kept abstract for testability)."""

    @abstractmethod
    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        ...

    @abstractmethod
    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        ...


class FootballDataScoreProvider(ScoreProviderBase):
    """Live-score provider using football-data.org via the shared client."""

    # Live-only on purpose: finished matches are landed by score_sync's
    # resolution pass (per-fixture fetch by external_id), which catches a
    # final whistle that falls between polls. Do NOT rely on this filter
    # to deliver FINISHED — it never does.
    LIVE_STATUS_FILTER = "LIVE,IN_PLAY,PAUSED"

    def __init__(self, client: FootballDataClient | None = None) -> None:
        self._client = client or FootballDataClient()

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        """Fetch live scores for a competition (e.g. competition_id='WC')."""
        matches = await self._client.get_matches(competition_id, status=self.LIVE_STATUS_FILTER)
        return [self._to_external_score(m) for m in matches]

    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        match = await self._client.get_match(fixture_id)
        if match is None:
            return None
        return self._to_external_score(match)

    @staticmethod
    def _to_external_score(match: dict) -> ExternalScore:
        score = match.get("score") or {}
        full_time = score.get("fullTime") or {}
        extra_time = score.get("extratime") or score.get("extraTime") or {}
        penalty = score.get("penalty") or score.get("penalties") or {}
        home_team = match.get("homeTeam") or {}
        away_team = match.get("awayTeam") or {}

        return ExternalScore(
            external_id=str(match.get("id", "")),
            home_team=home_team.get("name") or "",
            away_team=away_team.get("name") or "",
            home_score=full_time.get("home") or 0,
            away_score=full_time.get("away") or 0,
            status=map_status(match.get("status", "")),
            minute=match.get("minute"),
            home_score_et=extra_time.get("home"),
            away_score_et=extra_time.get("away"),
            home_penalties=penalty.get("home"),
            away_penalties=penalty.get("away"),
        )


class EspnScoreProvider(ScoreProviderBase):
    """Live in-play scores from ESPN's public scoreboard JSON.

    Emits only pre/in-play matches: a finished match is deliberately
    dropped, which leaves its fixture untouched on that sync tick so the
    Football-Data resolution pass fetches the authoritative final result.

    ExternalScore.external_id is left blank — ESPN event ids don't match
    the Football-Data ids stored on fixtures, so matching goes through the
    (home_team, away_team) name fallback with ESPN→canonical aliases.
    """

    def __init__(self, client: EspnClient | None = None) -> None:
        self._client = client or EspnClient()

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        slug = LEAGUE_SLUGS.get(competition_id, "fifa.world")
        # ESPN buckets events by US-Eastern calendar day; a ±1-day UTC window
        # always covers anything currently in play (incl. 02:00Z kickoffs).
        now = utc_now()
        dates = (
            f"{(now - timedelta(days=1)).strftime('%Y%m%d')}"
            f"-{(now + timedelta(days=1)).strftime('%Y%m%d')}"
        )
        events = await self._client.get_scoreboard(slug, dates)
        scores: list[ExternalScore] = []
        for event in events:
            ext = self._to_external_score(event)
            if ext is not None:
                scores.append(ext)
        return scores

    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        # Per-fixture lookups are keyed by Football-Data external ids, which
        # ESPN can't resolve — the fallback provider routes these to FD.
        return None

    @staticmethod
    def _to_external_score(event: dict) -> ExternalScore | None:
        try:
            comp = event["competitions"][0]
            status = map_event_status(comp.get("status", {}).get("type", {}))
            if status is None:
                return None  # finished/abandoned — Football-Data's job
            sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            home, away = sides.get("home"), sides.get("away")
            if not home or not away:
                return None
            shootout_home = home.get("shootoutScore")
            shootout_away = away.get("shootoutScore")
            return ExternalScore(
                external_id="",
                home_team=canonical_team_name(home.get("team", {}).get("displayName", "")),
                away_team=canonical_team_name(away.get("team", {}).get("displayName", "")),
                home_score=int(home.get("score") or 0),
                away_score=int(away.get("score") or 0),
                status=status,
                minute=parse_minute(comp.get("status", {}).get("displayClock")),
                home_penalties=int(shootout_home) if shootout_home is not None else None,
                away_penalties=int(shootout_away) if shootout_away is not None else None,
            )
        except (KeyError, IndexError, TypeError, ValueError):
            return None  # one malformed event shouldn't poison the tick


class FallbackScoreProvider(ScoreProviderBase):
    """ESPN-first chain: live scores try each provider in order, falling
    through on exceptions; per-fixture resolution always goes to
    Football-Data (it owns the external ids and the FT/ET/pens split)."""

    def __init__(
        self,
        live_providers: list[ScoreProviderBase],
        resolver: ScoreProviderBase,
    ) -> None:
        self._live_providers = live_providers
        self._resolver = resolver

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        last_exc: Exception | None = None
        for provider in self._live_providers:
            try:
                return await provider.fetch_live_scores(competition_id)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "score provider %s failed, trying next: %s",
                    type(provider).__name__,
                    exc,
                )
        raise last_exc if last_exc else RuntimeError("no live score providers configured")

    async def fetch_fixture_score(self, fixture_id: str) -> ExternalScore | None:
        return await self._resolver.fetch_fixture_score(fixture_id)


def get_score_provider() -> ScoreProviderBase:
    """ESPN paints live scores (Football-Data bulk as same-tick fallback);
    Football-Data resolves finals. No configuration on purpose — nothing
    to wire into prod env, and the fallback engages by itself per tick.
    """
    football_data = FootballDataScoreProvider()
    return FallbackScoreProvider(
        live_providers=[EspnScoreProvider(), football_data],
        resolver=football_data,
    )
