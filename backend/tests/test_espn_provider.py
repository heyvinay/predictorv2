"""Tests for the ESPN live-score provider and the ESPN→Football-Data chain."""

import pytest

from app.models.fixture import MatchStatus
from app.services.external.espn import canonical_team_name, map_event_status, parse_minute
from app.services.external_scores import (
    EspnScoreProvider,
    ExternalScore,
    FallbackScoreProvider,
)


def _event(
    *,
    state: str = "in",
    name: str = "STATUS_IN_PROGRESS",
    clock: str = "67'",
    home: str = "Mexico",
    away: str = "South Africa",
    home_score: str = "2",
    away_score: str = "1",
    shootout: tuple | None = None,
) -> dict:
    home_c = {
        "homeAway": "home",
        "score": home_score,
        "team": {"displayName": home},
    }
    away_c = {
        "homeAway": "away",
        "score": away_score,
        "team": {"displayName": away},
    }
    if shootout:
        home_c["shootoutScore"], away_c["shootoutScore"] = shootout
    return {
        "competitions": [
            {
                "status": {"displayClock": clock, "type": {"name": name, "state": state}},
                "competitors": [home_c, away_c],
            }
        ]
    }


# ---- mapping helpers -------------------------------------------------------


def test_status_mapping():
    assert map_event_status({"name": "STATUS_SCHEDULED", "state": "pre"}) == MatchStatus.SCHEDULED
    assert map_event_status({"name": "STATUS_IN_PROGRESS", "state": "in"}) == MatchStatus.LIVE
    assert map_event_status({"name": "STATUS_HALFTIME", "state": "in"}) == MatchStatus.HALFTIME
    # All terminal states are None — finals belong to Football-Data.
    assert map_event_status({"name": "STATUS_FULL_TIME", "state": "post"}) is None
    assert map_event_status({"name": "STATUS_POSTPONED", "state": "post"}) is None


def test_parse_minute():
    assert parse_minute("45'") == 45
    assert parse_minute("90'+3'") == 90
    assert parse_minute("0'") == 0
    assert parse_minute("") is None
    assert parse_minute(None) is None
    assert parse_minute("HT") is None


def test_team_name_aliases():
    assert canonical_team_name("Cape Verde") == "Cape Verde Islands"
    assert canonical_team_name("Türkiye") == "Turkey"
    assert canonical_team_name("Mexico") == "Mexico"


# ---- event → ExternalScore -------------------------------------------------


def test_live_event_maps_to_external_score():
    ext = EspnScoreProvider._to_external_score(_event())
    assert ext is not None
    assert ext.external_id == ""  # forces team-name fixture matching
    assert (ext.home_team, ext.away_team) == ("Mexico", "South Africa")
    assert (ext.home_score, ext.away_score) == (2, 1)
    assert ext.status == MatchStatus.LIVE
    assert ext.minute == 67


def test_finished_event_is_skipped():
    ev = _event(state="post", name="STATUS_FULL_TIME")
    assert EspnScoreProvider._to_external_score(ev) is None


def test_alias_applied_to_team_names():
    ev = _event(home="Türkiye", away="Cape Verde")
    ext = EspnScoreProvider._to_external_score(ev)
    assert (ext.home_team, ext.away_team) == ("Turkey", "Cape Verde Islands")


def test_shootout_maps_to_penalties():
    ev = _event(shootout=(4, 3))
    ext = EspnScoreProvider._to_external_score(ev)
    assert (ext.home_penalties, ext.away_penalties) == (4, 3)


def test_malformed_event_returns_none():
    assert EspnScoreProvider._to_external_score({"competitions": []}) is None
    assert EspnScoreProvider._to_external_score({}) is None


@pytest.mark.asyncio
async def test_fetch_live_scores_filters_post_events():
    class FakeClient:
        async def get_scoreboard(self, slug, dates):
            return [
                _event(),
                _event(state="post", name="STATUS_FULL_TIME", home="Canada", away="Qatar"),
            ]

    provider = EspnScoreProvider(client=FakeClient())
    scores = await provider.fetch_live_scores("WC")
    assert len(scores) == 1
    assert scores[0].home_team == "Mexico"


# ---- fallback chain --------------------------------------------------------


class _StubProvider:
    def __init__(self, *, live=None, raises=False, fixture_result=None):
        self.live = live or []
        self.raises = raises
        self.fixture_result = fixture_result
        self.live_calls = 0
        self.fixture_calls = 0

    async def fetch_live_scores(self, competition_id):
        self.live_calls += 1
        if self.raises:
            raise RuntimeError("provider down")
        return self.live

    async def fetch_fixture_score(self, fixture_id):
        self.fixture_calls += 1
        return self.fixture_result


def _score(team: str) -> ExternalScore:
    return ExternalScore(
        external_id="",
        home_team=team,
        away_team="X",
        home_score=1,
        away_score=0,
        status=MatchStatus.LIVE,
    )


@pytest.mark.asyncio
async def test_fallback_uses_primary_when_healthy():
    primary = _StubProvider(live=[_score("Mexico")])
    secondary = _StubProvider(live=[_score("ShouldNotAppear")])
    chain = FallbackScoreProvider([primary, secondary], resolver=secondary)

    scores = await chain.fetch_live_scores("WC")
    assert scores[0].home_team == "Mexico"
    assert secondary.live_calls == 0


@pytest.mark.asyncio
async def test_fallback_moves_to_secondary_on_error():
    primary = _StubProvider(raises=True)
    secondary = _StubProvider(live=[_score("Canada")])
    chain = FallbackScoreProvider([primary, secondary], resolver=secondary)

    scores = await chain.fetch_live_scores("WC")
    assert scores[0].home_team == "Canada"
    assert primary.live_calls == 1 and secondary.live_calls == 1


@pytest.mark.asyncio
async def test_fallback_raises_when_all_fail():
    chain = FallbackScoreProvider(
        [_StubProvider(raises=True), _StubProvider(raises=True)],
        resolver=_StubProvider(),
    )
    with pytest.raises(RuntimeError):
        await chain.fetch_live_scores("WC")


@pytest.mark.asyncio
async def test_fixture_resolution_always_routes_to_resolver():
    primary = _StubProvider()
    resolver = _StubProvider(fixture_result=_score("Mexico"))
    chain = FallbackScoreProvider([primary, resolver], resolver=resolver)

    ext = await chain.fetch_fixture_score("537327")
    assert ext is not None and ext.home_team == "Mexico"
    assert primary.fixture_calls == 0 and resolver.fixture_calls == 1
