"""Scoring calculation service.

Point calculation for match predictions and advancement predictions.
All scoring rules are configurable via YAML.

Supports multiple scoring modes:
- "fixed": Flat points for correct outcome
- "hybrid": Base points + linear rarity bonus (legacy)
- "logarithmic": Base points + Shannon-surprisal rarity bonus, capped

Scoring modes are extensible via the SCORING_STRATEGIES dict.
"""

import math
import uuid
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_tournament_config
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score
from app.schemas.leaderboard import PhaseBreakdown, PointBreakdown


# Default scoring configuration (used when YAML config is unavailable)
DEFAULT_SCORING_CONFIG: dict[str, Any] = {
    "mode": "logarithmic",
    "match": {
        "correct_outcome": 5,
        "exact_score": 10,
        "rarity_cap": 10,
        "hybrid_cap": 10,  # legacy alias retained for hybrid mode
    },
    "advancement": {
        "group_advance": 10,
        "group_position": 5,
        "round_of_32": 10,
        "round_of_16": 15,
        "quarter_final": 20,
        "semi_final": 40,
        "final": 60,
        "winner": 100,
    },
    "phase_multipliers": {
        "phase_1": 1.0,
        "phase_2": 0.7,
    },
}


def get_scoring_config() -> dict[str, Any]:
    """Get scoring configuration from tournament config.

    Returns merged config with defaults for any missing values.
    """
    try:
        config = get_tournament_config()
        scoring = config.get("scoring", {})
        # Merge with defaults to ensure all required keys exist
        return _merge_config(DEFAULT_SCORING_CONFIG, scoring)
    except FileNotFoundError:
        return DEFAULT_SCORING_CONFIG


def _merge_config(default: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge override config into default config."""
    result = default.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value
    return result


# =============================================================================
# Scoring Strategy Pattern
# =============================================================================


class MatchScoringStrategy(Protocol):
    """Protocol for match scoring strategies."""

    def calculate(
        self,
        prediction: MatchPrediction,
        score: Score,
        config: dict[str, Any],
        total_predictors: int,
        correct_predictors: int,
    ) -> tuple[int, bool, bool]:
        """Calculate match points.

        Args:
            prediction: User's prediction
            score: Actual match result
            config: Match scoring config
            total_predictors: Total players in competition
            correct_predictors: Players who got correct outcome

        Returns:
            Tuple of (points, correct_outcome, exact_score)
        """
        ...


class FixedScoring:
    """Fixed scoring: flat points for correct predictions."""

    def calculate(
        self,
        prediction: MatchPrediction,
        score: Score,
        config: dict[str, Any],
        total_predictors: int,
        correct_predictors: int,
    ) -> tuple[int, bool, bool]:
        outcome_points = config.get("correct_outcome", 5)
        exact_points = config.get("exact_score", 10)

        pred_outcome = prediction.predicted_outcome
        actual_outcome = score.outcome

        correct_outcome = pred_outcome == actual_outcome
        exact_score = (
            prediction.home_score == score.final_home_score
            and prediction.away_score == score.final_away_score
        )

        points = 0
        if correct_outcome:
            points += outcome_points
        if exact_score:
            points += exact_points

        return points, correct_outcome, exact_score


class HybridScoring:
    """Hybrid scoring: base points + rarity bonus.

    Formula: outcome_points + min(cap, total_predictors / correct_predictors)
    The fewer players who got it right, the higher the bonus.
    """

    def calculate(
        self,
        prediction: MatchPrediction,
        score: Score,
        config: dict[str, Any],
        total_predictors: int,
        correct_predictors: int,
    ) -> tuple[int, bool, bool]:
        outcome_points = config.get("correct_outcome", 5)
        exact_points = config.get("exact_score", 10)
        cap = config.get("hybrid_cap", 10)

        pred_outcome = prediction.predicted_outcome
        actual_outcome = score.outcome

        correct_outcome = pred_outcome == actual_outcome
        exact_score = (
            prediction.home_score == score.final_home_score
            and prediction.away_score == score.final_away_score
        )

        points = 0
        if correct_outcome:
            points += outcome_points
            # Hybrid bonus (capped)
            if correct_predictors > 0:
                bonus = min(cap, total_predictors // correct_predictors)
                points += bonus

        if exact_score:
            points += exact_points

        return points, correct_outcome, exact_score


# Anchor: alpha chosen so that f = 1/30 (one of thirty predictors correct)
# hits the cap of 10. log2(15) ~= 3.9069, so alpha ~= 2.5596. Defined as a
# module-level constant so a single number drives the published table.
_LOG_ALPHA = 10.0 / math.log2(15.0)


def _logarithmic_rarity_bonus(
    total_predictors: int, correct_predictors: int, cap: int
) -> int:
    """Shannon-surprisal rarity bonus, capped and integer-rounded.

    R = min(cap, round(alpha * log2(1 / (2f)))) for f < 0.5, else 0.
    Returns 0 defensively when there are no predictors.
    """
    if total_predictors <= 0 or correct_predictors <= 0:
        return 0
    f = correct_predictors / total_predictors
    if f >= 0.5:
        return 0
    raw = _LOG_ALPHA * math.log2(1.0 / (2.0 * f))
    return min(cap, max(0, round(raw)))


class LogarithmicScoring:
    """Logarithmic rarity scoring: base points + Shannon-surprisal bonus.

    The rarity bonus measures bits of information the crowd was wrong by,
    scaled so f = 1/30 hits the cap. Gated at f >= 0.5 (consensus picks
    earn no premium). Each ~1 bit of additional surprisal adds ~2.5 points.

    See docs/scoring-system.md for the published percentage-band table.
    """

    def calculate(
        self,
        prediction: MatchPrediction,
        score: Score,
        config: dict[str, Any],
        total_predictors: int,
        correct_predictors: int,
    ) -> tuple[int, bool, bool]:
        outcome_points = config.get("correct_outcome", 5)
        exact_points = config.get("exact_score", 10)
        cap = config.get("rarity_cap", config.get("hybrid_cap", 10))

        correct_outcome = prediction.predicted_outcome == score.outcome
        exact_score = (
            prediction.home_score == score.final_home_score
            and prediction.away_score == score.final_away_score
        )

        points = 0
        if correct_outcome:
            points += outcome_points
            points += _logarithmic_rarity_bonus(
                total_predictors, correct_predictors, cap
            )
        if exact_score:
            points += exact_points

        return points, correct_outcome, exact_score


# Registry of available scoring strategies
# Add new strategies here to make them available via config
SCORING_STRATEGIES: dict[str, MatchScoringStrategy] = {
    "fixed": FixedScoring(),
    "hybrid": HybridScoring(),
    "logarithmic": LogarithmicScoring(),
}


def get_scoring_strategy(mode: str | None = None) -> MatchScoringStrategy:
    """Get the scoring strategy based on config mode.

    Args:
        mode: Optional override for scoring mode. If None, uses config.

    Returns:
        The scoring strategy implementation.

    Raises:
        ValueError: If the configured mode is not registered.
    """
    if mode is None:
        config = get_scoring_config()
        mode = config.get("mode", "hybrid")

    strategy = SCORING_STRATEGIES.get(mode)
    if strategy is None:
        available = ", ".join(SCORING_STRATEGIES.keys())
        raise ValueError(f"Unknown scoring mode '{mode}'. Available: {available}")

    return strategy


def calculate_match_points(
    prediction: MatchPrediction,
    score: Score,
    total_predictors: int = 30,
    correct_predictors: int = 1,
    mode: str | None = None,
) -> tuple[int, bool, bool]:
    """Calculate points for a single match prediction.

    Uses the configured scoring mode (fixed or hybrid).

    Args:
        prediction: User's prediction
        score: Actual match result
        total_predictors: Total number of players (for hybrid calculation)
        correct_predictors: Number of players with correct outcome (for hybrid)
        mode: Optional override for scoring mode. If None, uses config.

    Returns:
        Tuple of (points, correct_outcome, exact_score)
    """
    config = get_scoring_config()
    match_config = config.get("match", {})
    strategy = get_scoring_strategy(mode)

    return strategy.calculate(
        prediction, score, match_config, total_predictors, correct_predictors
    )


def calculate_advancement_points(
    team_prediction: TeamPrediction,
    actual_advancement: dict[str, str],
    phase: PredictionPhase,
) -> int:
    """Calculate points for team advancement prediction.

    Args:
        team_prediction: User's prediction for team advancement
        actual_advancement: Dict mapping team -> highest stage reached
        phase: Which phase the prediction was made in

    Returns:
        Points earned for this prediction
    """
    config = get_scoring_config()
    adv_config = config.get("advancement", {})

    # Phase 2 is dormant — all entries are PHASE_1; multiplier is always 1.0.
    # The 0.7 Phase 2 multiplier and the `phase_multipliers` config read are
    # preserved in git history for future revival (see lifecycle simplification).
    multiplier = 1.0

    team = team_prediction.team
    predicted_stage = team_prediction.stage
    actual_stage = actual_advancement.get(team)

    if not actual_stage:
        return 0

    # Define stage ordering
    stage_order = [
        "group",
        "round_of_32",
        "round_of_16",
        "quarter_final",
        "semi_final",
        "final",
        "winner",
    ]

    predicted_idx = stage_order.index(predicted_stage) if predicted_stage in stage_order else -1
    actual_idx = stage_order.index(actual_stage) if actual_stage in stage_order else -1

    # Team must have reached at least the predicted stage
    if actual_idx >= predicted_idx:
        base_points = adv_config.get(predicted_stage, 0)
        return int(base_points * multiplier)

    return 0


async def get_actual_advancement(session: AsyncSession) -> dict[str, str]:
    """Determine which teams advanced to each stage based on completed fixtures.

    Queries finished knockout fixtures and determines the highest stage
    reached by each team.

    Args:
        session: Database session

    Returns:
        Dict mapping team name -> highest stage reached
        e.g., {"France": "winner", "Germany": "semi_final", ...}
    """
    # Define stage progression for determining highest stage
    # Higher index = further in tournament
    stage_ranking = {
        "round_of_32": 1,
        "round_of_16": 2,
        "quarter_final": 3,
        "semi_final": 4,
        "final": 5,
    }

    # Track highest stage reached by each team
    team_advancement: dict[str, str] = {}

    # Get all finished knockout fixtures with scores
    result = await session.execute(
        select(Fixture, Score)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(
            Fixture.stage != "group",
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    rows = result.all()

    for fixture, score in rows:
        if not score:
            continue

        stage = fixture.stage
        home_team = fixture.home_team
        away_team = fixture.away_team

        # Both teams at least reached this stage
        for team in [home_team, away_team]:
            if team:
                current_stage = team_advancement.get(team)
                if not current_stage or stage_ranking.get(stage, 0) > stage_ranking.get(
                    current_stage, 0
                ):
                    team_advancement[team] = stage

        # Determine winner and advance them to next stage
        winner = None
        if score.outcome == "1":
            winner = home_team
        elif score.outcome == "2":
            winner = away_team

        if winner:
            # Map current stage to advancement stage
            advancement_map = {
                "round_of_32": "round_of_16",
                "round_of_16": "quarter_final",
                "quarter_final": "semi_final",
                "semi_final": "final",
                "final": "winner",
            }
            next_stage = advancement_map.get(stage)
            if next_stage:
                current_stage = team_advancement.get(winner)
                if not current_stage or stage_ranking.get(
                    next_stage, 6
                ) > stage_ranking.get(current_stage, 0):
                    team_advancement[winner] = next_stage

    return team_advancement


def _add_match_points_to_phase(
    phase_breakdown: PhaseBreakdown,
    base_outcome_points: int,
    exact_score_points: int,
    points: int,
    correct_outcome: bool,
    exact_score: bool,
) -> None:
    """Add match prediction points to a phase breakdown."""
    if correct_outcome:
        phase_breakdown.match_outcome_points += base_outcome_points
        # Hybrid bonus is the difference between total points and base + exact
        hybrid_bonus = points - base_outcome_points - (exact_score_points if exact_score else 0)
        if hybrid_bonus > 0:
            phase_breakdown.hybrid_bonus_points += hybrid_bonus

    if exact_score:
        phase_breakdown.exact_score_points += exact_score_points


def _add_advancement_points_to_phase(
    phase_breakdown: PhaseBreakdown,
    stage: str,
    group_position: int | None,
    points: int,
) -> None:
    """Add advancement prediction points to a phase breakdown."""
    if stage == "group":
        if group_position is not None:
            phase_breakdown.group_position_points += points
        else:
            phase_breakdown.group_advance_points += points
    elif stage == "round_of_32":
        phase_breakdown.round_of_32_points += points
    elif stage == "round_of_16":
        phase_breakdown.round_of_16_points += points
    elif stage == "quarter_final":
        phase_breakdown.quarter_final_points += points
    elif stage == "semi_final":
        phase_breakdown.semi_final_points += points
    elif stage == "final":
        phase_breakdown.final_points += points
    elif stage == "winner":
        phase_breakdown.winner_points += points


async def _count_eligible_entries(session: AsyncSession) -> int:
    """Total competitors for hybrid-scoring rarity — number of entries that
    have ever been submitted or locked (excluding withdrawn / disabled).
    Replaces the old "active users" count now that scoring is entry-scoped.
    """
    result = await session.execute(
        select(PredictionEntry.id)
        .join(PredictionEntryPhase, PredictionEntryPhase.entry_id == PredictionEntry.id)
        .where(
            PredictionEntry.is_disabled == False,  # noqa: E712
            PredictionEntry.withdrawn_at.is_(None),
            PredictionEntryPhase.status == EntryStatus.SUBMITTED,
        )
        .distinct()
    )
    return len(result.all())


async def calculate_entry_points(
    session: AsyncSession, entry_id: uuid.UUID
) -> PointBreakdown:
    """Calculate total points for a single prediction entry.

    Args:
        session: Database session
        entry_id: PredictionEntry to calculate points for

    Returns:
        PointBreakdown with detailed point categories by phase
    """
    config = get_scoring_config()
    match_config = config.get("match", {})
    base_outcome_points = match_config.get("correct_outcome", 5)
    exact_score_points = match_config.get("exact_score", 10)

    phase1 = PhaseBreakdown()
    phase2 = PhaseBreakdown()

    total_predictions = 0
    correct_outcomes = 0
    exact_scores = 0

    # Match predictions joined to their fixture + actual score
    result = await session.execute(
        select(MatchPrediction, Score, Fixture)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(
            MatchPrediction.entry_id == entry_id,
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    rows = result.all()

    for prediction, score, fixture in rows:
        if not score:
            continue

        total_predictions += 1

        # Rarity bonus uses per-fixture predictor counts: "the room that
        # showed up", not all active entries. Sum of outcome buckets gives
        # the total predictors for this fixture.
        outcome_counts = await get_outcome_counts(session, fixture.id)
        total_predictors = sum(outcome_counts.values())
        correct_predictors = outcome_counts.get(score.outcome, 0)

        points, is_correct_outcome, is_exact_score = calculate_match_points(
            prediction,
            score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
        )

        if is_correct_outcome:
            correct_outcomes += 1
        if is_exact_score:
            exact_scores += 1

        phase_breakdown = phase1 if prediction.phase == PredictionPhase.PHASE_1 else phase2
        _add_match_points_to_phase(
            phase_breakdown,
            base_outcome_points,
            exact_score_points,
            points,
            is_correct_outcome,
            is_exact_score,
        )

    # Team-advancement predictions
    result = await session.execute(
        select(TeamPrediction).where(TeamPrediction.entry_id == entry_id)
    )
    team_predictions = result.scalars().all()

    actual_advancement = await get_actual_advancement(session)
    for pred in team_predictions:
        points = calculate_advancement_points(pred, actual_advancement, pred.phase)
        if points == 0:
            continue

        phase_breakdown = phase1 if pred.phase == PredictionPhase.PHASE_1 else phase2
        _add_advancement_points_to_phase(
            phase_breakdown,
            pred.stage,
            pred.group_position,
            points,
        )

    # Bonus-question points (cross-phase). Imported locally so this module
    # can stay decoupled from services.bonus at import time.
    from app.services.bonus import calculate_bonus_points
    bonus_points = await calculate_bonus_points(session, entry_id)

    return PointBreakdown(
        phase1=phase1,
        phase2=phase2,
        correct_outcomes=correct_outcomes,
        exact_scores=exact_scores,
        total_predictions=total_predictions,
        bonus_question_points=bonus_points,
    )


async def resolve_default_entry_id(
    session: AsyncSession, user_id: uuid.UUID
) -> uuid.UUID | None:
    """Return the entry_id of the user's most recently-updated eligible
    entry, or None if they have none.

    Used by API endpoints that historically took a `user_id` but must now
    operate on a single entry (profile stats, /snapshots/me, etc.). The
    caller may also accept an explicit `entry_id` query param — this is
    just the default.
    """
    result = await session.execute(
        select(PredictionEntry)
        .join(PredictionEntryPhase, PredictionEntryPhase.entry_id == PredictionEntry.id)
        .where(
            PredictionEntry.user_id == user_id,
            PredictionEntry.is_disabled == False,  # noqa: E712
            PredictionEntry.withdrawn_at.is_(None),
            PredictionEntryPhase.status == EntryStatus.SUBMITTED,
        )
        .order_by(PredictionEntry.updated_at.desc())
        .limit(1)
    )
    row = result.scalars().first()
    return row.id if row else None


async def get_outcome_counts(session: AsyncSession, fixture_id: uuid.UUID) -> dict[str, int]:
    """Get count of each predicted outcome for a fixture.

    Used for hybrid scoring calculation.

    Returns:
        Dict with keys '1', 'X', '2' and counts
    """
    result = await session.execute(
        select(MatchPrediction).where(MatchPrediction.fixture_id == fixture_id)
    )
    predictions = result.scalars().all()

    counts = {"1": 0, "X": 0, "2": 0}
    for pred in predictions:
        outcome = pred.predicted_outcome
        counts[outcome] = counts.get(outcome, 0) + 1

    return counts
