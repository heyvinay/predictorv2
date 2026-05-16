"""Tests for community predictions schemas and blind pool logic.

Verifies that CommunityPrediction/CommunityPredictionsResponse schemas
populate correctly, and that the blind pool check (is_locked + status)
correctly gates visibility.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score
from app.schemas.fixture import FixtureScore
from app.schemas.prediction import CommunityPrediction, CommunityPredictionsResponse


class TestCommunityPredictionSchema:
    """Tests for CommunityPrediction Pydantic schema."""

    def test_basic_prediction(self):
        """Should create a prediction with user name and scores."""
        pred = CommunityPrediction(
            user_name="Alice",
            entry_reference="WC26-000001",
            entry_name="Entry 1",
            home_score=2,
            away_score=1,
        )
        assert pred.user_name == "Alice"
        assert pred.entry_reference == "WC26-000001"
        assert pred.entry_name == "Entry 1"
        assert pred.home_score == 2
        assert pred.away_score == 1

    def test_draw_prediction(self):
        """Should handle draw predictions."""
        pred = CommunityPrediction(
            user_name="Bob",
            entry_reference="WC26-000002",
            entry_name="Entry 1",
            home_score=0,
            away_score=0,
        )
        assert pred.home_score == 0
        assert pred.away_score == 0


class TestCommunityPredictionsResponseSchema:
    """Tests for CommunityPredictionsResponse schema."""

    def test_response_with_predictions_and_actual(self):
        """Should bundle predictions and actual result."""
        fixture_id = uuid.uuid4()
        actual = FixtureScore(
            home_score=3,
            away_score=1,
            outcome="1",
        )
        response = CommunityPredictionsResponse(
            fixture_id=fixture_id,
            home_team="Brazil",
            away_team="Serbia",
            predictions=[
                CommunityPrediction(
                    user_name="Alice",
                    entry_reference="WC26-000001",
                    entry_name="Entry 1",
                    home_score=2,
                    away_score=0,
                ),
                CommunityPrediction(
                    user_name="Bob",
                    entry_reference="WC26-000002",
                    entry_name="Entry 1",
                    home_score=3,
                    away_score=1,
                ),
            ],
            actual=actual,
        )
        assert response.fixture_id == fixture_id
        assert response.home_team == "Brazil"
        assert response.away_team == "Serbia"
        assert len(response.predictions) == 2
        assert response.actual is not None
        assert response.actual.outcome == "1"

    def test_response_without_actual(self):
        """Should allow None actual (locked but not finished)."""
        response = CommunityPredictionsResponse(
            fixture_id=uuid.uuid4(),
            home_team="Japan",
            away_team="Germany",
            predictions=[
                CommunityPrediction(
                    user_name="Charlie",
                    entry_reference="WC26-000003",
                    entry_name="Entry 1",
                    home_score=0,
                    away_score=2,
                ),
            ],
            actual=None,
        )
        assert response.actual is None
        assert len(response.predictions) == 1

    def test_response_empty_predictions(self):
        """Should handle fixture with no predictions."""
        response = CommunityPredictionsResponse(
            fixture_id=uuid.uuid4(),
            home_team="Qatar",
            away_team="Ecuador",
            predictions=[],
            actual=None,
        )
        assert len(response.predictions) == 0


class TestBlindPoolLogic:
    """Tests for the blind pool enforcement condition.

    The community endpoint uses:
        if not fixture.is_locked(LOCK_MINUTES) and fixture.status != FINISHED:
            raise 403

    These tests verify the fixture.is_locked + status gate directly
    on the model methods (not via HTTP), matching the unit test style.
    """

    LOCK_MINUTES = 5

    @pytest.fixture
    def scheduled_future_fixture(self) -> Fixture:
        """Fixture far in the future — predictions should be hidden."""
        fixture = MagicMock(spec=Fixture)
        fixture.id = uuid.uuid4()
        fixture.home_team = "France"
        fixture.away_team = "Denmark"
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(hours=24)
        fixture.status = MatchStatus.SCHEDULED
        fixture.is_locked.return_value = False
        return fixture

    @pytest.fixture
    def locked_fixture(self) -> Fixture:
        """Fixture within lock window — predictions should be visible."""
        fixture = MagicMock(spec=Fixture)
        fixture.id = uuid.uuid4()
        fixture.home_team = "Spain"
        fixture.away_team = "Costa Rica"
        fixture.kickoff = datetime.now(timezone.utc) + timedelta(minutes=3)
        fixture.status = MatchStatus.SCHEDULED
        fixture.is_locked.return_value = True
        return fixture

    @pytest.fixture
    def live_fixture(self) -> Fixture:
        """Live fixture — is_locked returns True."""
        fixture = MagicMock(spec=Fixture)
        fixture.id = uuid.uuid4()
        fixture.home_team = "Argentina"
        fixture.away_team = "Saudi Arabia"
        fixture.kickoff = datetime.now(timezone.utc) - timedelta(minutes=45)
        fixture.status = MatchStatus.LIVE
        fixture.is_locked.return_value = True
        return fixture

    @pytest.fixture
    def finished_fixture(self) -> Fixture:
        """Finished fixture — should always be visible."""
        fixture = MagicMock(spec=Fixture)
        fixture.id = uuid.uuid4()
        fixture.home_team = "Germany"
        fixture.away_team = "Japan"
        fixture.kickoff = datetime.now(timezone.utc) - timedelta(hours=3)
        fixture.status = MatchStatus.FINISHED
        fixture.is_locked.return_value = True
        return fixture

    def _should_block(self, fixture) -> bool:
        """Replicate the blind pool check from the community endpoint."""
        return not fixture.is_locked(self.LOCK_MINUTES) and fixture.status != MatchStatus.FINISHED

    def test_future_fixture_is_blocked(self, scheduled_future_fixture):
        """Unlocked future fixture should be blocked (blind pool)."""
        assert self._should_block(scheduled_future_fixture) is True

    def test_locked_fixture_is_visible(self, locked_fixture):
        """Locked fixture (within 5-min window) should be visible."""
        assert self._should_block(locked_fixture) is False

    def test_live_fixture_is_visible(self, live_fixture):
        """Live fixture should be visible (is_locked=True)."""
        assert self._should_block(live_fixture) is False

    def test_finished_fixture_is_always_visible(self, finished_fixture):
        """Finished fixture should be visible regardless of lock state."""
        assert self._should_block(finished_fixture) is False

    def test_finished_but_not_locked_edge_case(self):
        """Finished fixture with is_locked=False should still be visible.

        This is an edge case — in practice finished fixtures are always
        past kickoff so is_locked would be True. But the blind pool logic
        uses OR, so status==FINISHED alone is sufficient.
        """
        fixture = MagicMock(spec=Fixture)
        fixture.status = MatchStatus.FINISHED
        fixture.is_locked.return_value = False
        assert self._should_block(fixture) is False
