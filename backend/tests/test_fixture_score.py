"""Tests for fixture score embedding in API responses.

Verifies that FixtureScore schema populates correctly and that
fixture_to_read includes score data only for finished matches.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score
from app.schemas.fixture import FixtureScore, FixtureRead
from app.api.fixtures import fixture_to_read


class TestFixtureScoreSchema:
    """Tests for FixtureScore Pydantic schema."""

    def test_basic_score(self):
        """Should create FixtureScore with regular time scores."""
        score = FixtureScore(
            home_score=2,
            away_score=1,
            outcome="1",
        )
        assert score.home_score == 2
        assert score.away_score == 1
        assert score.outcome == "1"
        assert score.home_score_et is None
        assert score.away_score_et is None
        assert score.home_penalties is None
        assert score.away_penalties is None

    def test_extra_time_score(self):
        """Should include extra time scores when provided."""
        score = FixtureScore(
            home_score=1,
            away_score=1,
            home_score_et=2,
            away_score_et=1,
            outcome="1",
        )
        assert score.home_score_et == 2
        assert score.away_score_et == 1

    def test_penalty_score(self):
        """Should include penalty scores for knockout matches."""
        score = FixtureScore(
            home_score=1,
            away_score=1,
            home_score_et=1,
            away_score_et=1,
            home_penalties=4,
            away_penalties=3,
            outcome="1",
        )
        assert score.home_penalties == 4
        assert score.away_penalties == 3

    def test_draw_outcome(self):
        """Should handle draw outcome."""
        score = FixtureScore(
            home_score=0,
            away_score=0,
            outcome="X",
        )
        assert score.outcome == "X"


class TestFixtureToRead:
    """Tests for fixture_to_read score embedding."""

    @pytest.fixture
    def finished_fixture_with_score(self) -> Fixture:
        """Create a finished fixture with a score attached."""
        fixture = MagicMock(spec=Fixture)
        fixture.id = uuid.uuid4()
        fixture.home_team = "Brazil"
        fixture.away_team = "Germany"
        fixture.kickoff = datetime.now(timezone.utc) - timedelta(hours=3)
        fixture.stage = "group"
        fixture.group = "A"
        fixture.match_number = 1
        fixture.status = MatchStatus.FINISHED
        fixture.minute = None
        fixture.external_id = None
        fixture.is_locked.return_value = True
        fixture.time_until_lock.return_value = None

        # Attach a score
        score = MagicMock(spec=Score)
        score.home_score = 2
        score.away_score = 0
        score.home_score_et = None
        score.away_score_et = None
        score.home_penalties = None
        score.away_penalties = None
        score.outcome = "1"
        fixture.score = score

        return fixture

    @pytest.fixture
    def scheduled_fixture(self) -> Fixture:
        """Create a scheduled fixture without a score."""
        fixture = MagicMock(spec=Fixture)
        fixture.id = uuid.uuid4()
        fixture.home_team = "France"
        fixture.away_team = "Spain"
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(hours=24)
        fixture.stage = "group"
        fixture.group = "B"
        fixture.match_number = 2
        fixture.status = MatchStatus.SCHEDULED
        fixture.minute = None
        fixture.external_id = None
        fixture.is_locked.return_value = False
        fixture.time_until_lock.return_value = timedelta(hours=23, minutes=55)
        fixture.score = None

        return fixture

    @pytest.fixture
    def live_fixture_with_score(self) -> Fixture:
        """Create a live fixture that has a score (e.g., data feed) but is not finished."""
        fixture = MagicMock(spec=Fixture)
        fixture.id = uuid.uuid4()
        fixture.home_team = "Argentina"
        fixture.away_team = "Mexico"
        fixture.kickoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        fixture.stage = "group"
        fixture.group = "C"
        fixture.match_number = 3
        fixture.status = MatchStatus.LIVE
        fixture.minute = 30
        fixture.external_id = None
        fixture.is_locked.return_value = True
        fixture.time_until_lock.return_value = None

        score = MagicMock(spec=Score)
        score.home_score = 1
        score.away_score = 0
        score.outcome = "1"
        fixture.score = score

        return fixture

    def test_finished_fixture_includes_score(self, finished_fixture_with_score):
        """Finished fixture should have score data embedded in the response."""
        result = fixture_to_read(finished_fixture_with_score)

        assert isinstance(result, FixtureRead)
        assert result.score is not None
        assert result.score.home_score == 2
        assert result.score.away_score == 0
        assert result.score.outcome == "1"
        assert result.status == MatchStatus.FINISHED

    def test_scheduled_fixture_has_no_score(self, scheduled_fixture):
        """Scheduled fixture should not include score data."""
        result = fixture_to_read(scheduled_fixture)

        assert result.score is None
        assert result.status == MatchStatus.SCHEDULED

    def test_live_fixture_includes_score(self, live_fixture_with_score):
        """Live fixture SHOULD include score so the Dashboard can render the
        in-progress scoreline.

        Behaviour changed in feat(live-scores): predictions lock 5 minutes
        before kickoff, so by the time a match is LIVE everyone's pick is
        already locked in — there's no "premature result exposure" risk.
        Exposing the score lets the score_scheduler's Football-Data.org
        writes flow through to the frontend in real time.
        """
        result = fixture_to_read(live_fixture_with_score)

        assert result.score is not None
        assert result.score.home_score == 1
        assert result.score.away_score == 0
        assert result.status == MatchStatus.LIVE

    def test_finished_fixture_without_score_object(self):
        """Finished fixture with no Score record should have score=None."""
        fixture = MagicMock(spec=Fixture)
        fixture.id = uuid.uuid4()
        fixture.home_team = "Japan"
        fixture.away_team = "Korea Republic"
        fixture.kickoff = datetime.now(timezone.utc) - timedelta(hours=2)
        fixture.stage = "group"
        fixture.group = "D"
        fixture.match_number = 4
        fixture.status = MatchStatus.FINISHED
        fixture.minute = None
        fixture.external_id = None
        fixture.is_locked.return_value = True
        fixture.time_until_lock.return_value = None
        fixture.score = None

        result = fixture_to_read(fixture)

        assert result.score is None

    def test_score_includes_extra_time_data(self):
        """Should pass through extra time and penalty data."""
        fixture = MagicMock(spec=Fixture)
        fixture.id = uuid.uuid4()
        fixture.home_team = "England"
        fixture.away_team = "Italy"
        fixture.kickoff = datetime.now(timezone.utc) - timedelta(hours=4)
        fixture.stage = "round_of_16"
        fixture.group = None
        fixture.match_number = 49
        fixture.status = MatchStatus.FINISHED
        fixture.minute = None
        fixture.external_id = None
        fixture.is_locked.return_value = True
        fixture.time_until_lock.return_value = None

        score = MagicMock(spec=Score)
        score.home_score = 1
        score.away_score = 1
        score.home_score_et = 1
        score.away_score_et = 1
        score.home_penalties = 5
        score.away_penalties = 3
        score.outcome = "1"  # Home won on pens
        fixture.score = score

        result = fixture_to_read(fixture)

        assert result.score is not None
        assert result.score.home_score_et == 1
        assert result.score.away_score_et == 1
        assert result.score.home_penalties == 5
        assert result.score.away_penalties == 3
        assert result.score.outcome == "1"
