"""External score fetching service.

Fetches live scores from Football-Data.org via the shared FootballDataClient.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.fixture import MatchStatus
from app.services.external.football_data import FootballDataClient, map_status


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

    # FINISHED must stay in this filter: a match that ends between polls
    # drops out of a live-only response, so the LIVE → FINISHED transition
    # would never reach score_sync and the fixture would stay LIVE forever
    # (scoring pays only on FINISHED). Already-applied finished matches are
    # no-op'd by score_sync's change detection.
    LIVE_STATUS_FILTER = "LIVE,IN_PLAY,PAUSED,FINISHED"

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


def get_score_provider() -> ScoreProviderBase:
    """Return the configured score provider.

    Single-provider since we standardised on Football-Data.org. Kept as a
    function (rather than inlined at the call site) for ease of swapping
    providers in the future.
    """
    return FootballDataScoreProvider()
