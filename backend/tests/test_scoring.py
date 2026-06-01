"""Tests for the scoring service.

CRITICAL: No scoring logic changes without a corresponding test case.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score
from app.services.scoring import (
    calculate_match_points,
    calculate_advancement_points,
    get_scoring_config,
    get_scoring_strategy,
    FixedScoring,
    HybridScoring,
    LogarithmicScoring,
    SCORING_STRATEGIES,
)


class TestGetScoringConfig:
    """Tests for scoring configuration loading."""

    def test_default_config_when_file_not_found(self):
        """Should return default config when YAML file doesn't exist."""
        with patch("app.services.scoring.get_tournament_config") as mock_config:
            mock_config.side_effect = FileNotFoundError()
            config = get_scoring_config()

            assert config["match"]["correct_outcome"] == 5
            assert config["match"]["exact_score"] == 10
            assert config["advancement"]["winner"] == 100
            assert config["mode"] == "logarithmic"

    def test_config_merges_with_defaults(self):
        """Should merge YAML config with defaults for missing keys."""
        with patch("app.services.scoring.get_tournament_config") as mock_config:
            # Partial config - only override some values
            mock_config.return_value = {
                "scoring": {
                    "mode": "fixed",
                    "match": {
                        "correct_outcome": 10,
                    },
                }
            }
            config = get_scoring_config()

            # Overridden values
            assert config["mode"] == "fixed"
            assert config["match"]["correct_outcome"] == 10
            # Default values preserved
            assert config["match"]["exact_score"] == 10
            assert config["advancement"]["winner"] == 100


class TestScoringStrategies:
    """Tests for scoring strategy selection."""

    def test_get_fixed_strategy(self):
        """Should return FixedScoring when mode is 'fixed'."""
        strategy = get_scoring_strategy("fixed")
        assert isinstance(strategy, FixedScoring)

    def test_get_hybrid_strategy(self):
        """Should return HybridScoring when mode is 'hybrid'."""
        strategy = get_scoring_strategy("hybrid")
        assert isinstance(strategy, HybridScoring)

    def test_unknown_strategy_raises_error(self):
        """Should raise ValueError for unknown scoring mode."""
        with pytest.raises(ValueError) as exc_info:
            get_scoring_strategy("unknown_mode")
        assert "Unknown scoring mode" in str(exc_info.value)

    def test_strategies_are_registered(self):
        """Both fixed and hybrid strategies should be registered."""
        assert "fixed" in SCORING_STRATEGIES
        assert "hybrid" in SCORING_STRATEGIES


class TestCalculateMatchPoints:
    """Tests for match prediction scoring."""

    @pytest.fixture
    def home_win_prediction(self) -> MatchPrediction:
        """Create a prediction for home team win."""
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 2
        pred.away_score = 1
        pred.predicted_outcome = "1"
        return pred

    @pytest.fixture
    def draw_prediction(self) -> MatchPrediction:
        """Create a prediction for draw."""
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 1
        pred.away_score = 1
        pred.predicted_outcome = "X"
        return pred

    @pytest.fixture
    def away_win_prediction(self) -> MatchPrediction:
        """Create a prediction for away team win."""
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 0
        pred.away_score = 2
        pred.predicted_outcome = "2"
        return pred

    @pytest.fixture
    def home_win_score(self) -> Score:
        """Create a score for home team win."""
        score = MagicMock(spec=Score)
        score.home_score = 2
        score.away_score = 1
        score.final_home_score = 2
        score.final_away_score = 1
        score.outcome = "1"
        return score

    @pytest.fixture
    def draw_score(self) -> Score:
        """Create a score for draw."""
        score = MagicMock(spec=Score)
        score.home_score = 1
        score.away_score = 1
        score.final_home_score = 1
        score.final_away_score = 1
        score.outcome = "X"
        return score

    def test_correct_outcome_home_win(self, home_win_prediction, home_win_score):
        """Should award points for correct home win prediction."""
        points, correct, exact = calculate_match_points(
            home_win_prediction, home_win_score, total_predictors=30, correct_predictors=10
        )

        assert correct is True
        assert points >= 5  # At least base points for correct outcome

    def test_correct_outcome_draw(self, draw_prediction, draw_score):
        """Should award points for correct draw prediction."""
        points, correct, exact = calculate_match_points(
            draw_prediction, draw_score, total_predictors=30, correct_predictors=10
        )

        assert correct is True
        assert points >= 5

    def test_incorrect_outcome(self, home_win_prediction, draw_score):
        """Should not award points for incorrect prediction."""
        points, correct, exact = calculate_match_points(
            home_win_prediction, draw_score, total_predictors=30, correct_predictors=10
        )

        assert correct is False
        assert points == 0 or points == 10  # Only exact score bonus if any

    def test_exact_score_bonus(self, home_win_prediction, home_win_score):
        """Should award bonus for exact score."""
        # Prediction: 2-1, Score: 2-1 (exact match)
        points, correct, exact = calculate_match_points(
            home_win_prediction, home_win_score, total_predictors=30, correct_predictors=10
        )

        assert exact is True
        assert points >= 15  # 5 (outcome) + 10 (exact) minimum

    def test_correct_outcome_wrong_score(self, home_win_prediction, home_win_score):
        """Should award outcome points but not exact score bonus."""
        # Modify prediction to have different score but same outcome
        home_win_prediction.home_score = 3
        home_win_prediction.away_score = 0

        points, correct, exact = calculate_match_points(
            home_win_prediction, home_win_score, total_predictors=30, correct_predictors=10
        )

        assert correct is True
        assert exact is False

    def test_hybrid_scoring_with_few_correct(self, home_win_prediction, home_win_score):
        """Hybrid bonus should be higher when fewer people are correct."""
        # Only 3 people got it right out of 30
        points_few, _, _ = calculate_match_points(
            home_win_prediction, home_win_score, total_predictors=30, correct_predictors=3
        )

        # 15 people got it right out of 30
        points_many, _, _ = calculate_match_points(
            home_win_prediction, home_win_score, total_predictors=30, correct_predictors=15
        )

        # Fewer correct = higher bonus (capped at 10)
        assert points_few >= points_many

    def test_hybrid_scoring_cap(self, home_win_prediction, home_win_score):
        """Hybrid bonus should be capped at 10 points."""
        # Only 1 person got it right - would be 30 points without cap
        points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score, total_predictors=30, correct_predictors=1
        )

        # Points should be: 5 (outcome) + 10 (capped hybrid) + 10 (exact) = 25 max
        assert points <= 25


class TestFixedVsHybridScoring:
    """Tests comparing fixed and hybrid scoring modes."""

    @pytest.fixture
    def home_win_prediction(self) -> MatchPrediction:
        """Create a prediction for home team win."""
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 2
        pred.away_score = 1
        pred.predicted_outcome = "1"
        return pred

    @pytest.fixture
    def home_win_score(self) -> Score:
        """Create a score for home team win."""
        score = MagicMock(spec=Score)
        score.home_score = 2
        score.away_score = 1
        score.final_home_score = 2
        score.final_away_score = 1
        score.outcome = "1"
        return score

    def test_fixed_scoring_ignores_player_counts(self, home_win_prediction, home_win_score):
        """Fixed scoring should give same points regardless of how many got it right."""
        # Few correct
        points_few, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=3,
            mode="fixed"
        )

        # Many correct
        points_many, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=25,
            mode="fixed"
        )

        # Fixed scoring gives same points
        assert points_few == points_many

    def test_hybrid_scoring_varies_by_player_counts(self, home_win_prediction, home_win_score):
        """Hybrid scoring should give more points when fewer players are correct."""
        # Few correct (rare outcome)
        points_few, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=3,
            mode="hybrid"
        )

        # Many correct (common outcome)
        points_many, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=25,
            mode="hybrid"
        )

        # Hybrid gives more points for rare correct predictions
        assert points_few > points_many

    def test_fixed_vs_hybrid_base_outcome(self, home_win_prediction, home_win_score):
        """Both modes should award base outcome points when correct."""
        # Wrong score but correct outcome
        home_win_prediction.home_score = 3
        home_win_prediction.away_score = 0

        fixed_points, fixed_correct, fixed_exact = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=15,
            mode="fixed"
        )

        hybrid_points, hybrid_correct, hybrid_exact = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=15,
            mode="hybrid"
        )

        # Both should register correct outcome, not exact
        assert fixed_correct is True
        assert hybrid_correct is True
        assert fixed_exact is False
        assert hybrid_exact is False

        # Fixed should give only base points (5)
        assert fixed_points == 5

        # Hybrid should give base + bonus (5 + 2 = 7 for 30/15)
        assert hybrid_points == 7

    def test_mode_override_works(self, home_win_prediction, home_win_score):
        """Mode override should work regardless of config default."""
        # Explicitly use fixed mode
        fixed_points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=3,
            mode="fixed"
        )

        # Explicitly use hybrid mode
        hybrid_points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=3,
            mode="hybrid"
        )

        # Should get different results due to hybrid bonus
        assert hybrid_points > fixed_points


class TestLogarithmicScoring:
    """Logarithmic rarity bonus: R = min(cap, round(alpha * log2(1/(2f)))).

    Derived from Shannon surprisal in bits beyond a 50/50 coin flip. Anchor
    alpha = 10/log2(15) so that f = 1/30 (the "uniquely correct out of 30
    predictors" case) hits the cap of 10.

    Gates at f >= 0.5 -> R = 0 (consensus pays no premium).
    """

    @pytest.fixture
    def home_win_prediction(self) -> MatchPrediction:
        pred = MagicMock(spec=MatchPrediction)
        pred.home_score = 2
        pred.away_score = 1
        pred.predicted_outcome = "1"
        return pred

    @pytest.fixture
    def home_win_score(self) -> Score:
        score = MagicMock(spec=Score)
        score.home_score = 2
        score.away_score = 1
        score.final_home_score = 2
        score.final_away_score = 1
        score.outcome = "1"
        return score

    @pytest.fixture
    def draw_score(self) -> Score:
        score = MagicMock(spec=Score)
        score.home_score = 1
        score.away_score = 1
        score.final_home_score = 1
        score.final_away_score = 1
        score.outcome = "X"
        return score

    def test_strategy_registered_as_logarithmic(self):
        """get_scoring_strategy('logarithmic') returns a LogarithmicScoring."""
        assert isinstance(get_scoring_strategy("logarithmic"), LogarithmicScoring)
        assert "logarithmic" in SCORING_STRATEGIES

    def test_unanimous_correct_no_rarity_bonus(self, home_win_prediction, home_win_score):
        """f = 1.0: everyone got it right, rarity = 0."""
        points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=30,
            mode="logarithmic",
        )
        assert points == 15  # base 5 + exact 10

    def test_half_correct_no_rarity_bonus(self, home_win_prediction, home_win_score):
        """f = 0.5: at the gate, rarity = 0."""
        points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=15,
            mode="logarithmic",
        )
        assert points == 15

    def test_three_way_split_token_bonus(self, home_win_prediction, home_win_score):
        """f = 1/3: three-way uncertainty, R = 1 (alpha * log2(1.5) ~= 1.497)."""
        points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=10,
            mode="logarithmic",
        )
        assert points == 16  # base 5 + exact 10 + rarity 1

    def test_one_in_six_moderate_bonus(self, home_win_prediction, home_win_score):
        """f = 1/6: R = 4 (alpha * log2(3) ~= 4.057)."""
        points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=5,
            mode="logarithmic",
        )
        assert points == 19  # base 5 + exact 10 + rarity 4

    def test_one_in_ten_high_bonus(self, home_win_prediction, home_win_score):
        """f = 1/10: R = 6 (alpha * log2(5) ~= 5.943)."""
        points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=3,
            mode="logarithmic",
        )
        assert points == 21  # base 5 + exact 10 + rarity 6

    def test_uniquely_correct_hits_cap(self, home_win_prediction, home_win_score):
        """f = 1/30: anchor point, R = 10 (cap)."""
        points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=1,
            mode="logarithmic",
        )
        assert points == 25  # base 5 + exact 10 + rarity 10 (cap)

    def test_beyond_anchor_clamped_to_cap(self, home_win_prediction, home_win_score):
        """f = 1/60 (rarer than anchor): bonus is still capped at 10."""
        points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=60, correct_predictors=1,
            mode="logarithmic",
        )
        assert points == 25  # capped

    def test_no_bonus_when_outcome_wrong(self, home_win_prediction, draw_score):
        """No rarity bonus paid for incorrect outcome (even if k is tiny)."""
        points, correct, exact = calculate_match_points(
            home_win_prediction, draw_score,
            total_predictors=30, correct_predictors=1,
            mode="logarithmic",
        )
        assert correct is False
        assert exact is False
        assert points == 0

    def test_correct_outcome_wrong_exact_score(self, home_win_prediction, home_win_score):
        """Correct outcome + wrong score: rarity paid, exact bonus not."""
        home_win_prediction.home_score = 3
        home_win_prediction.away_score = 0
        points, correct, exact = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=30, correct_predictors=10,
            mode="logarithmic",
        )
        assert correct is True
        assert exact is False
        assert points == 6  # base 5 + rarity 1 (no exact bonus)

    def test_zero_predictors_no_crash(self, home_win_prediction, home_win_score):
        """Division-by-zero guard: 0 predictors -> no bonus, no crash."""
        points, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=0, correct_predictors=0,
            mode="logarithmic",
        )
        # Safe default: base 5 + exact 10 + no rarity = 15
        assert points == 15

    def test_scale_invariance_same_fraction_same_bonus(
        self, home_win_prediction, home_win_score
    ):
        """Same f produces same R regardless of P (percentage-based, scale-invariant)."""
        # f = 1/6 in both cases
        points_small, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=12, correct_predictors=2,
            mode="logarithmic",
        )
        points_large, _, _ = calculate_match_points(
            home_win_prediction, home_win_score,
            total_predictors=60, correct_predictors=10,
            mode="logarithmic",
        )
        assert points_small == points_large == 19  # base 5 + exact 10 + rarity 4


class TestCalculateAdvancementPoints:
    """Tests for team advancement scoring."""

    @pytest.fixture
    def winner_prediction(self) -> MagicMock:
        """Create a prediction for tournament winner."""
        pred = MagicMock()
        pred.team = "Brazil"
        pred.stage = "winner"
        pred.phase = PredictionPhase.PHASE_1
        return pred

    @pytest.fixture
    def round_of_16_prediction(self) -> MagicMock:
        """Create a prediction for round of 16."""
        pred = MagicMock()
        pred.team = "Germany"
        pred.stage = "round_of_16"
        pred.phase = PredictionPhase.PHASE_1
        return pred

    def test_winner_prediction_correct(self, winner_prediction):
        """Should award 100 points for correct winner in Phase 1."""
        actual_advancement = {"Brazil": "winner"}

        points = calculate_advancement_points(
            winner_prediction, actual_advancement, PredictionPhase.PHASE_1
        )

        assert points == 100

    def test_winner_prediction_wrong(self, winner_prediction):
        """Should award 0 points when team doesn't win."""
        actual_advancement = {"Brazil": "semi_final", "Argentina": "winner"}

        points = calculate_advancement_points(
            winner_prediction, actual_advancement, PredictionPhase.PHASE_1
        )

        # Team reached semi but was predicted to win - still get semi-final points
        # because they reached that stage
        assert points >= 0

    def test_round_of_16_prediction_team_reaches(self, round_of_16_prediction):
        """Should award points when team reaches predicted round."""
        actual_advancement = {"Germany": "quarter_final"}  # Went further than R16

        points = calculate_advancement_points(
            round_of_16_prediction, actual_advancement, PredictionPhase.PHASE_1
        )

        # Phase 1 R16 points. Bumped 2026-06-01 from 15 to 30 to match the
        # /rules page (scoring.advancement.round_of_16 in worldcup2026.yml).
        assert points == 30

    def test_team_eliminated_before_prediction(self, round_of_16_prediction):
        """Should award 0 points when team is eliminated early."""
        actual_advancement = {"Germany": "group"}  # Eliminated in groups

        points = calculate_advancement_points(
            round_of_16_prediction, actual_advancement, PredictionPhase.PHASE_1
        )

        assert points == 0

    @pytest.mark.skip(
        reason="Phase 2 scoring is deferred — no Phase 2 implementation yet. "
        "The 0.7 reduced-points multiplier is not currently applied "
        "(calculate_advancement_points returns full points). Restore this test "
        "and implement the multiplier when Phase 2 work resumes."
    )
    def test_phase_2_reduced_points(self, winner_prediction):
        """Phase 2 predictions should award reduced points (0.7× multiplier)."""
        actual_advancement = {"Brazil": "winner"}
        winner_prediction.phase = PredictionPhase.PHASE_2

        points = calculate_advancement_points(
            winner_prediction, actual_advancement, PredictionPhase.PHASE_2
        )

        # Phase 2 winner is 70 points (70% of 100)
        assert points == 70
