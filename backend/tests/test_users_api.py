"""Tests for users API response schemas and blind pool prediction filtering.

Verifies that PublicProfile, UserMatchPredictionView, BracketSummary,
and UserPredictionsResponse schemas populate correctly, and that the
blind pool logic correctly filters predictions by lock/finished state.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction
from app.models.score import Score
from app.api.users import (
    PublicProfile,
    UserMatchPredictionView,
    BracketSummary,
    UserPredictionsResponse,
)
from app.schemas.auth import UserStats


class TestUserMatchPredictionView:
    """Tests for UserMatchPredictionView schema."""

    def test_basic_pending_prediction(self):
        """Prediction for a locked-but-unfinished match has no result data."""
        view = UserMatchPredictionView(
            fixture_id=uuid.uuid4(),
            home_team="Brazil",
            away_team="Germany",
            kickoff=datetime.now(timezone.utc) + timedelta(minutes=2),
            stage="group",
            group="A",
            status=MatchStatus.SCHEDULED,
            predicted_home=2,
            predicted_away=1,
        )
        assert view.actual_home is None
        assert view.actual_away is None
        assert view.actual_outcome is None
        assert view.is_exact is False
        assert view.is_correct_outcome is False

    def test_finished_with_exact_score(self):
        """Prediction that exactly matches the actual score."""
        view = UserMatchPredictionView(
            fixture_id=uuid.uuid4(),
            home_team="France",
            away_team="Australia",
            kickoff=datetime.now(timezone.utc) - timedelta(hours=2),
            stage="group",
            group="D",
            status=MatchStatus.FINISHED,
            predicted_home=4,
            predicted_away=1,
            actual_home=4,
            actual_away=1,
            actual_outcome="1",
            is_exact=True,
            is_correct_outcome=True,
        )
        assert view.is_exact is True
        assert view.is_correct_outcome is True
        assert view.actual_outcome == "1"

    def test_finished_correct_outcome_wrong_score(self):
        """Prediction got the winner right but not the exact score."""
        view = UserMatchPredictionView(
            fixture_id=uuid.uuid4(),
            home_team="England",
            away_team="Iran",
            kickoff=datetime.now(timezone.utc) - timedelta(hours=2),
            stage="group",
            group="B",
            status=MatchStatus.FINISHED,
            predicted_home=3,
            predicted_away=0,
            actual_home=6,
            actual_away=2,
            actual_outcome="1",
            is_exact=False,
            is_correct_outcome=True,
        )
        assert view.is_exact is False
        assert view.is_correct_outcome is True

    def test_finished_wrong_prediction(self):
        """Prediction got both outcome and score wrong."""
        view = UserMatchPredictionView(
            fixture_id=uuid.uuid4(),
            home_team="Argentina",
            away_team="Saudi Arabia",
            kickoff=datetime.now(timezone.utc) - timedelta(hours=2),
            stage="group",
            group="C",
            status=MatchStatus.FINISHED,
            predicted_home=3,
            predicted_away=0,
            actual_home=1,
            actual_away=2,
            actual_outcome="2",
            is_exact=False,
            is_correct_outcome=False,
        )
        assert view.is_exact is False
        assert view.is_correct_outcome is False

    def test_knockout_stage_no_group(self):
        """Knockout match should have group=None."""
        view = UserMatchPredictionView(
            fixture_id=uuid.uuid4(),
            home_team="Netherlands",
            away_team="USA",
            kickoff=datetime.now(timezone.utc) - timedelta(hours=2),
            stage="round_of_16",
            group=None,
            status=MatchStatus.FINISHED,
            predicted_home=2,
            predicted_away=1,
        )
        assert view.group is None
        assert view.stage == "round_of_16"


class TestBracketSummary:
    """Tests for BracketSummary schema."""

    def test_empty_stages(self):
        """Should handle empty bracket predictions."""
        summary = BracketSummary(stages={})
        assert summary.stages == {}

    def test_multiple_stages(self):
        """Should group teams by stage correctly."""
        summary = BracketSummary(stages={
            "round_of_32": ["Brazil", "France", "Germany", "Spain"],
            "round_of_16": ["Brazil", "France"],
            "quarter_final": ["Brazil"],
        })
        assert len(summary.stages["round_of_32"]) == 4
        assert len(summary.stages["round_of_16"]) == 2
        assert len(summary.stages["quarter_final"]) == 1

    def test_winner_stage(self):
        """Should handle the 'winner' stage with a single team."""
        summary = BracketSummary(stages={
            "winner": ["Brazil"],
        })
        assert summary.stages["winner"] == ["Brazil"]


class TestUserPredictionsResponse:
    """Tests for the full UserPredictionsResponse schema."""

    def test_complete_response(self):
        """Should bundle match predictions and bracket summary."""
        user_id = uuid.uuid4()
        response = UserPredictionsResponse(
            user_id=user_id,
            user_name="Alice",
            match_predictions=[
                UserMatchPredictionView(
                    fixture_id=uuid.uuid4(),
                    home_team="Qatar",
                    away_team="Ecuador",
                    kickoff=datetime.now(timezone.utc) - timedelta(hours=3),
                    stage="group",
                    group="A",
                    status=MatchStatus.FINISHED,
                    predicted_home=0,
                    predicted_away=2,
                    actual_home=0,
                    actual_away=2,
                    actual_outcome="2",
                    is_exact=True,
                    is_correct_outcome=True,
                ),
            ],
            bracket_summary=BracketSummary(stages={"round_of_16": ["Brazil"]}),
        )
        assert response.user_id == user_id
        assert response.user_name == "Alice"
        assert len(response.match_predictions) == 1
        assert response.match_predictions[0].is_exact is True
        assert "round_of_16" in response.bracket_summary.stages

    def test_empty_predictions(self):
        """Should handle a user with no visible predictions."""
        response = UserPredictionsResponse(
            user_id=uuid.uuid4(),
            user_name="NewUser",
            match_predictions=[],
            bracket_summary=BracketSummary(stages={}),
        )
        assert len(response.match_predictions) == 0
        assert response.bracket_summary.stages == {}


class TestBlindPoolPredictionFiltering:
    """Tests for blind pool logic that filters which predictions are shown.

    The users endpoint applies:
        if not fixture.is_locked(LOCK_MINUTES) and fixture.status != FINISHED:
            continue  # skip this prediction

    These tests verify the filtering condition directly.
    """

    LOCK_MINUTES = 5

    def _make_fixture(self, *, status: MatchStatus, locked: bool) -> Fixture:
        """Create a mock fixture with given state."""
        fixture = MagicMock(spec=Fixture)
        fixture.id = uuid.uuid4()
        fixture.home_team = "TeamA"
        fixture.away_team = "TeamB"
        fixture.kickoff = datetime.now(timezone.utc)
        fixture.stage = "group"
        fixture.group = "A"
        fixture.match_number = 1
        fixture.status = status
        fixture.is_locked.return_value = locked
        return fixture

    def _make_prediction(self, fixture_id: uuid.UUID) -> MatchPrediction:
        """Create a mock prediction."""
        pred = MagicMock(spec=MatchPrediction)
        pred.fixture_id = fixture_id
        pred.home_score = 1
        pred.away_score = 0
        pred.predicted_outcome = "1"
        return pred

    def _should_include(self, fixture) -> bool:
        """Replicate the blind pool filter from users endpoint."""
        if not fixture.is_locked(self.LOCK_MINUTES) and fixture.status != MatchStatus.FINISHED:
            return False
        return True

    def test_unlocked_scheduled_excluded(self):
        """Future unlocked fixture predictions should be filtered out."""
        fixture = self._make_fixture(status=MatchStatus.SCHEDULED, locked=False)
        assert self._should_include(fixture) is False

    def test_locked_scheduled_included(self):
        """Locked fixture predictions should be included."""
        fixture = self._make_fixture(status=MatchStatus.SCHEDULED, locked=True)
        assert self._should_include(fixture) is True

    def test_live_included(self):
        """Live fixture predictions should be included (is_locked=True)."""
        fixture = self._make_fixture(status=MatchStatus.LIVE, locked=True)
        assert self._should_include(fixture) is True

    def test_finished_included(self):
        """Finished fixture predictions should always be included."""
        fixture = self._make_fixture(status=MatchStatus.FINISHED, locked=True)
        assert self._should_include(fixture) is True

    def test_finished_not_locked_edge_case(self):
        """Finished but technically not-locked should still be included."""
        fixture = self._make_fixture(status=MatchStatus.FINISHED, locked=False)
        assert self._should_include(fixture) is True

    def test_result_flags_for_exact_match(self):
        """Verify is_exact and is_correct_outcome computation logic.

        The endpoint does:
            is_exact = pred.home_score == score.final_home_score and pred.away_score == score.final_away_score
            is_correct_outcome = pred.predicted_outcome == score.outcome
        """
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 2
        pred.away_score = 1
        pred.predicted_outcome = "1"

        score = MagicMock(spec=Score)
        score.final_home_score = 2
        score.final_away_score = 1
        score.outcome = "1"

        is_exact = pred.home_score == score.final_home_score and pred.away_score == score.final_away_score
        is_correct_outcome = pred.predicted_outcome == score.outcome

        assert is_exact is True
        assert is_correct_outcome is True

    def test_result_flags_for_correct_outcome_wrong_score(self):
        """Correct outcome (home win) but wrong exact score."""
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 1
        pred.away_score = 0
        pred.predicted_outcome = "1"

        score = MagicMock(spec=Score)
        score.final_home_score = 3
        score.final_away_score = 1
        score.outcome = "1"

        is_exact = pred.home_score == score.final_home_score and pred.away_score == score.final_away_score
        is_correct_outcome = pred.predicted_outcome == score.outcome

        assert is_exact is False
        assert is_correct_outcome is True

    def test_result_flags_for_wrong_outcome(self):
        """Predicted home win but away team won."""
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 2
        pred.away_score = 0
        pred.predicted_outcome = "1"

        score = MagicMock(spec=Score)
        score.final_home_score = 0
        score.final_away_score = 1
        score.outcome = "2"

        is_exact = pred.home_score == score.final_home_score and pred.away_score == score.final_away_score
        is_correct_outcome = pred.predicted_outcome == score.outcome

        assert is_exact is False
        assert is_correct_outcome is False

    def test_result_flags_for_draw(self):
        """Both predicted and actual draw — correct outcome."""
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 1
        pred.away_score = 1
        pred.predicted_outcome = "X"

        score = MagicMock(spec=Score)
        score.final_home_score = 0
        score.final_away_score = 0
        score.outcome = "X"

        is_exact = pred.home_score == score.final_home_score and pred.away_score == score.final_away_score
        is_correct_outcome = pred.predicted_outcome == score.outcome

        assert is_exact is False
        assert is_correct_outcome is True
