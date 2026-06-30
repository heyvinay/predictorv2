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


def test_null_fulltime_sets_has_score_false() -> None:
    """Regression for the WC2026 opener: FD served status FINISHED with
    null fullTime. The 0-coerced scores must be flagged as not-a-score."""
    from app.services.external_scores import FootballDataScoreProvider

    match = {
        "id": 537327,
        "status": "FINISHED",
        "homeTeam": {"name": "Mexico"},
        "awayTeam": {"name": "South Africa"},
        "score": {"winner": None, "duration": "REGULAR",
                  "fullTime": {"home": None, "away": None},
                  "halfTime": {"home": None, "away": None}},
    }
    ext = FootballDataScoreProvider._to_external_score(match)
    assert ext.has_score is False
    assert (ext.home_score, ext.away_score) == (0, 0)  # coerced, but flagged

    match["score"]["fullTime"] = {"home": 2, "away": 0}
    ext2 = FootballDataScoreProvider._to_external_score(match)
    assert ext2.has_score is True


def test_et_pens_match_with_clean_shootout_payload() -> None:
    """Clean ET+pens payload (regularTime + extraTime split present, pens
    unequal): regulation lands as 1-1, after-ET cumulative as 1-1,
    shootout passes through. has_score True so the chain stops at FD."""
    from app.services.external_scores import FootballDataScoreProvider

    match = {
        "id": 999999,
        "status": "FINISHED",
        "homeTeam": {"name": "Germany"},
        "awayTeam": {"name": "Paraguay"},
        "score": {
            "winner": "AWAY_TEAM",
            "duration": "PENALTY_SHOOTOUT",
            "fullTime": {"home": 4, "away": 5},      # combined total — DON'T use as 90-min
            "halfTime": {"home": 0, "away": 1},
            "regularTime": {"home": 1, "away": 1},   # 90-min regulation
            "extraTime": {"home": 0, "away": 0},     # ET-period delta only
            "penalties": {"home": 3, "away": 4},     # shootout (clean, unequal)
        },
    }
    ext = FootballDataScoreProvider._to_external_score(match)

    assert (ext.home_score, ext.away_score) == (1, 1)
    assert (ext.home_score_et, ext.away_score_et) == (1, 1)
    assert (ext.home_penalties, ext.away_penalties) == (3, 4)
    assert ext.has_score is True
    assert ext.status == MatchStatus.FINISHED


def test_broken_pen_field_recovers_via_fulltime_derivation_germany() -> None:
    """Regression for the actual FD payload served for Germany vs
    Paraguay R32 (match 537415) on 2026-06-29: duration was
    PENALTY_SHOOTOUT but FD's `penalties` field misreported as 4-4 with
    `winner: None`. The shootout legs can be recovered exactly via the
    identity `fullTime − (regularTime + extraTime)` because FD's
    `fullTime` IS the combined total. Derived legs: home 4-1-0=3, away
    5-1-0=4 → 3-4, matching Wikipedia's record (Paraguay won 4-3)."""
    from app.services.external_scores import FootballDataScoreProvider

    match = {
        "id": 537415,
        "status": "FINISHED",
        "homeTeam": {"name": "Germany"},
        "awayTeam": {"name": "Paraguay"},
        "score": {
            "winner": None,
            "duration": "PENALTY_SHOOTOUT",
            "fullTime": {"home": 4, "away": 5},
            "halfTime": {"home": 0, "away": 1},
            "regularTime": {"home": 1, "away": 1},
            "extraTime": {"home": 0, "away": 0},
            "penalties": {"home": 4, "away": 4},  # FD glitch — derivation overrides
        },
    }
    ext = FootballDataScoreProvider._to_external_score(match)
    assert ext.has_score is True
    assert (ext.home_score, ext.away_score) == (1, 1)
    assert (ext.home_score_et, ext.away_score_et) == (1, 1)
    assert (ext.home_penalties, ext.away_penalties) == (3, 4)  # derived, not FD's 4-4


def test_broken_pen_field_recovers_via_fulltime_derivation_netherlands() -> None:
    """Regression for the actual FD payload served for Netherlands vs
    Morocco R32 (match 537418) on 2026-06-30: same FD glitch class —
    `penalties: 3-3, winner: None` despite a pen-decided match. Derived
    legs: home 3-1-0=2, away 4-1-0=3 → 2-3, matching Wikipedia
    (Morocco won 3-2)."""
    from app.services.external_scores import FootballDataScoreProvider

    match = {
        "id": 537418,
        "status": "FINISHED",
        "homeTeam": {"name": "Netherlands"},
        "awayTeam": {"name": "Morocco"},
        "score": {
            "winner": None,
            "duration": "PENALTY_SHOOTOUT",
            "fullTime": {"home": 3, "away": 4},
            "halfTime": {"home": 0, "away": 0},
            "regularTime": {"home": 1, "away": 1},
            "extraTime": {"home": 0, "away": 0},
            "penalties": {"home": 3, "away": 3},  # FD glitch — derivation overrides
        },
    }
    ext = FootballDataScoreProvider._to_external_score(match)
    assert ext.has_score is True
    assert (ext.home_score, ext.away_score) == (1, 1)
    assert (ext.home_score_et, ext.away_score_et) == (1, 1)
    assert (ext.home_penalties, ext.away_penalties) == (2, 3)


def test_unrecoverable_shootout_demotes_has_score() -> None:
    """If FD gives `duration=PENALTY_SHOOTOUT` but neither derivation
    nor the `penalty` field yields unequal legs (e.g., fullTime missing
    AND penalty field tied), flag has_score=False so the fallback chain
    reaches for the ESPN backup resolver."""
    from app.services.external_scores import FootballDataScoreProvider

    match = {
        "id": 999997,
        "status": "FINISHED",
        "homeTeam": {"name": "Foo"},
        "awayTeam": {"name": "Bar"},
        "score": {
            "winner": None,
            "duration": "PENALTY_SHOOTOUT",
            "fullTime": {"home": None, "away": None},  # FD never published combined
            "regularTime": {"home": 1, "away": 1},
            "extraTime": {"home": 0, "away": 0},
            "penalties": {"home": 4, "away": 4},  # tied — no winner
        },
    }
    ext = FootballDataScoreProvider._to_external_score(match)
    assert ext.has_score is False


def test_et_only_match_maps_cumulative_after_extra_time() -> None:
    """ET-decided match (no pens). FD's `extraTime` is the ET-period delta,
    so the cumulative-after-ET our model wants is regularTime + extraTime."""
    from app.services.external_scores import FootballDataScoreProvider

    match = {
        "id": 999001,
        "status": "FINISHED",
        "homeTeam": {"name": "Brazil"},
        "awayTeam": {"name": "Chile"},
        "score": {
            "winner": "HOME_TEAM",
            "duration": "EXTRA_TIME",
            "fullTime": {"home": 2, "away": 1},
            "regularTime": {"home": 1, "away": 1},
            "extraTime": {"home": 1, "away": 0},
            "penalties": {"home": None, "away": None},
        },
    }
    ext = FootballDataScoreProvider._to_external_score(match)
    assert (ext.home_score, ext.away_score) == (1, 1)
    assert (ext.home_score_et, ext.away_score_et) == (2, 1)
    assert (ext.home_penalties, ext.away_penalties) == (None, None)


def test_regular_90min_match_still_uses_fulltime() -> None:
    """Backward-compat: group-stage matches have NO `regularTime` field,
    so `fullTime` remains the 90-min source there. The pre-fix mapping
    relied on this for every group match; the fix must preserve it."""
    from app.services.external_scores import FootballDataScoreProvider

    match = {
        "id": 999002,
        "status": "FINISHED",
        "homeTeam": {"name": "Argentina"},
        "awayTeam": {"name": "Mexico"},
        "score": {
            "winner": "HOME_TEAM",
            "duration": "REGULAR",
            "fullTime": {"home": 3, "away": 0},
            "halfTime": {"home": 2, "away": 0},
        },
    }
    ext = FootballDataScoreProvider._to_external_score(match)
    assert (ext.home_score, ext.away_score) == (3, 0)
    assert ext.home_score_et is None and ext.away_score_et is None
    assert ext.home_penalties is None and ext.away_penalties is None


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
    assert isinstance(provider._backup_resolver, EspnScoreProvider)
