"""Smoke tests for the refactored FootballDataScoreProvider."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.models.fixture import MatchStatus


PROBE_MATCHES = json.loads(
    (Path(__file__).parent.parent / "data" / "probe" / "fd_matches.json").read_text()
)["matches"]


@pytest.mark.asyncio
async def test_fetch_live_scores_maps_match_to_external_score() -> None:
    """When the API returns a real (resolved) match, we get a populated ExternalScore."""
    from app.services.external_scores import FootballDataScoreProvider

    sample = next(m for m in PROBE_MATCHES if m["stage"] == "GROUP_STAGE" and m["homeTeam"]["name"])

    with patch("app.services.external_scores.FootballDataClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.get_matches = AsyncMock(return_value=[sample])
        provider = FootballDataScoreProvider()
        scores = await provider.fetch_live_scores("WC")

    assert len(scores) == 1
    s = scores[0]
    assert s.external_id == str(sample["id"])
    assert s.home_team == sample["homeTeam"]["name"]
    assert s.away_team == sample["awayTeam"]["name"]
    assert s.status == MatchStatus.SCHEDULED  # TIMED → SCHEDULED


@pytest.mark.asyncio
async def test_fetch_live_scores_filters_by_status() -> None:
    """The provider passes the live-status filter through to get_matches."""
    from app.services.external_scores import FootballDataScoreProvider

    with patch("app.services.external_scores.FootballDataClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.get_matches = AsyncMock(return_value=[])
        provider = FootballDataScoreProvider()
        await provider.fetch_live_scores("WC")
        mock_client.get_matches.assert_awaited_once_with("WC", status="LIVE,IN_PLAY,PAUSED")


def test_default_provider_is_espn_first_with_fd_resolver() -> None:
    """Regression pin for the provider chain: ESPN paints live scores,
    Football-Data is the bulk fallback AND the per-fixture resolver that
    lands FINISHED results (the live filter never delivers them)."""
    from app.services.external_scores import (
        EspnScoreProvider,
        FallbackScoreProvider,
        FootballDataScoreProvider,
        get_score_provider,
    )

    provider = get_score_provider()
    assert isinstance(provider, FallbackScoreProvider)
    assert isinstance(provider._live_providers[0], EspnScoreProvider)
    assert isinstance(provider._live_providers[1], FootballDataScoreProvider)
    assert isinstance(provider._resolver, FootballDataScoreProvider)
