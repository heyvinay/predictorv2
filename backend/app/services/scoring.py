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
from app.models.competition import Competition
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
        "round_of_32": 20,
        "round_of_16": 30,
        "quarter_final": 40,
        "semi_final": 50,
        "final": 75,
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
        return compute_match_points(
            mode="fixed",
            predicted_home=prediction.home_score,
            predicted_away=prediction.away_score,
            actual_home=score.final_home_score,
            actual_away=score.final_away_score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
            outcome_points=config.get("correct_outcome", 5),
            exact_points=config.get("exact_score", 10),
            cap=0,  # unused for mode "fixed"
        )


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
        return compute_match_points(
            mode="hybrid",
            predicted_home=prediction.home_score,
            predicted_away=prediction.away_score,
            actual_home=score.final_home_score,
            actual_away=score.final_away_score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
            outcome_points=config.get("correct_outcome", 5),
            exact_points=config.get("exact_score", 10),
            cap=config.get("hybrid_cap", 10),
        )


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


def _outcome(home: int, away: int) -> str:
    """1/X/2 outcome from a scoreline. Convention is irrelevant as long as
    both the predicted and actual lines are classified by the same function."""
    if home > away:
        return "1"
    if home < away:
        return "2"
    return "X"


def compute_match_points(
    *,
    mode: str,
    predicted_home: int,
    predicted_away: int,
    actual_home: int,
    actual_away: int,
    total_predictors: int,
    correct_predictors: int,
    outcome_points: int,
    exact_points: int,
    cap: int,
) -> tuple[int, bool, bool]:
    """Pure match-points calculation shared with the frontend
    (`computeMatchPoints` in `frontend/src/lib/utils/matchBreakdown.ts`).

    Takes only primitives — no model objects, no config-dict key names — so
    the two language implementations validate against the SAME shared golden
    cases (`shared/scoring-parity-cases.json`). The three strategy classes
    below and the frontend Results card both route through this, so the
    tested path is the production path.

    Returns (points, correct_outcome, exact_score). `cap` bounds the rarity
    bonus; it's unused for mode 'fixed'.

    Penalty shootouts are out of scope: actual_home/actual_away are the
    final (incl. extra-time) scores, and in this competition match-score
    predictions only exist for group-stage fixtures, which cannot go to
    penalties.
    """
    correct_outcome = _outcome(predicted_home, predicted_away) == _outcome(
        actual_home, actual_away
    )
    exact_score = predicted_home == actual_home and predicted_away == actual_away

    points = 0
    if correct_outcome:
        points += outcome_points
        if mode == "hybrid":
            if correct_predictors > 0:
                points += min(cap, total_predictors // correct_predictors)
        elif mode == "logarithmic":
            points += _logarithmic_rarity_bonus(
                total_predictors, correct_predictors, cap
            )
        # mode "fixed": no rarity bonus.
    if exact_score:
        points += exact_points

    return points, correct_outcome, exact_score


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
        return compute_match_points(
            mode="logarithmic",
            predicted_home=prediction.home_score,
            predicted_away=prediction.away_score,
            actual_home=score.final_home_score,
            actual_away=score.final_away_score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
            outcome_points=config.get("correct_outcome", 5),
            exact_points=config.get("exact_score", 10),
            cap=config.get("rarity_cap", config.get("hybrid_cap", 10)),
        )


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
        mode = config.get("mode", "logarithmic")

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
    """Determine which teams advanced to each stage — lineup-based timing.

    A team is credited with "reached stage X" the moment it is seeded into
    a stage-X fixture (regardless of whether that match has been played).
    The winner of a FINISHED match is additionally credited with reaching
    the next stage — which means the `winner` credit (champion) only fires
    once the final is FINISHED and scored.

    Lineup-based timing (v2.161.0, user decision 2026-06-10): once FIFA
    publishes a round's lineup and the fixtures sync from Football-Data,
    everyone already knows who reached that round — predictions are
    settled, so the points pay immediately instead of waiting for the
    round's matches to be played.

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

    # Map a finished match's stage to the stage its winner advances to
    advancement_map = {
        "round_of_32": "round_of_16",
        "round_of_16": "quarter_final",
        "quarter_final": "semi_final",
        "semi_final": "final",
        "final": "winner",
    }

    # Track highest stage reached by each team
    team_advancement: dict[str, str] = {}

    # ALL knockout fixtures, played or not — seeding alone earns the
    # "reached this stage" credit.
    result = await session.execute(
        select(Fixture, Score)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(Fixture.stage != "group")
    )
    rows = result.all()

    # Resolve R32 slot placeholders to real team names BEFORE crediting.
    # Football-Data writes `slot:round_of_32:NNN:home/away` placeholders
    # for several hours/days after the group stage ends, until it
    # ingests the FIFA-published lineup. We can derive the real
    # qualifiers from settled group standings immediately — that's what
    # r32_resolver does. Without this step, the admin flips
    # knockout_scoring_enabled and sees ZERO advancement credits until
    # FD catches up, which can lag the actual qualification clarity by
    # 24+ hours. (v2.183.x — surfaced when KO scoring was enabled
    # 2026-06-28 with R32 fixtures still placeholder-seeded.)
    from app.services.r32_resolver import build_r32_resolver, resolve_r32_pair

    r32_resolver = await build_r32_resolver(session)

    for fixture, score in rows:
        stage = fixture.stage
        home_team, away_team = resolve_r32_pair(
            r32_resolver, fixture.home_team, fixture.away_team
        )

        # "Reached this stage": credit any team seeded into the fixture.
        # R32 placeholders are now resolved above. R16+ placeholders stay
        # (they can only be known once R32 matches finish), and harmlessly
        # earn no credit because no user prediction matches them.
        for team in [home_team, away_team]:
            if team:
                current_stage = team_advancement.get(team)
                if not current_stage or stage_ranking.get(stage, 0) > stage_ranking.get(
                    current_stage, 0
                ):
                    team_advancement[team] = stage

        # "Winner advances to next stage": still requires a played match.
        if fixture.status != MatchStatus.FINISHED or not score:
            continue

        winner = None
        if score.outcome == "1":
            winner = home_team
        elif score.outcome == "2":
            winner = away_team

        if winner:
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


def eligible_entry_ids_select():
    """SQL Select of entry IDs eligible to compete — SUBMITTED, not
    disabled, not withdrawn. Same predicate as
    leaderboard._list_eligible_entries; used as a subquery filter so
    rarity denominators only count entries that scoring actually pays
    (product decision, 2026-06-10).
    """
    return (
        select(PredictionEntry.id)
        .join(PredictionEntryPhase, PredictionEntryPhase.entry_id == PredictionEntry.id)
        .where(
            PredictionEntry.is_disabled == False,  # noqa: E712
            PredictionEntry.withdrawn_at.is_(None),
            PredictionEntryPhase.status == EntryStatus.SUBMITTED,
        )
        .distinct()
    )


async def get_all_outcome_counts(
    session: AsyncSession,
) -> dict[uuid.UUID, dict[str, int]]:
    """Outcome counts for EVERY fixture, in a single query.

    Returns {fixture_id: {"1": n, "X": n, "2": n}} — per-fixture counts
    ("the room that showed up"), NOT a global entry count. Only eligible
    entries' predictions are counted, so the rarity denominator matches
    what scoring actually pays.

    The leaderboard rebuild calls this once and passes the result into
    calculate_entry_points instead of issuing one query per fixture per
    entry.
    """
    result = await session.execute(
        select(
            MatchPrediction.fixture_id,
            MatchPrediction.home_score,
            MatchPrediction.away_score,
        ).where(MatchPrediction.entry_id.in_(eligible_entry_ids_select()))
    )
    by_fixture: dict[uuid.UUID, dict[str, int]] = {}
    for fixture_id, home_score, away_score in result.all():
        counts = by_fixture.setdefault(fixture_id, {"1": 0, "X": 0, "2": 0})
        if home_score > away_score:
            outcome = "1"
        elif home_score < away_score:
            outcome = "2"
        else:
            outcome = "X"
        counts[outcome] += 1
    return by_fixture


async def is_knockout_scoring_enabled(session: AsyncSession) -> bool:
    """Whether advancement-point payouts are unlocked for the active
    competition (v2.181.1).

    Returns False when no competition is active OR the active competition
    has not flipped the gate. The leaderboard rebuild fetches this once
    per rebuild and threads it through `calculate_entry_points`; single
    entry callers can omit and we look it up here.
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    return bool(competition and competition.knockout_scoring_enabled)


async def is_win_probability_enabled(session: AsyncSession) -> bool:
    """Whether the win-probability simulator is unlocked for the active
    competition. Fail-closed, same contract as is_knockout_scoring_enabled:
    returns False when no competition is active OR the flag is unset."""
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    return bool(competition and competition.win_probability_enabled)


async def calculate_entry_points(
    session: AsyncSession,
    entry_id: uuid.UUID,
    *,
    outcome_counts_by_fixture: dict[uuid.UUID, dict[str, int]] | None = None,
    actual_advancement: dict[str, str] | None = None,
    knockout_scoring_enabled: bool | None = None,
) -> PointBreakdown:
    """Calculate total points for a single prediction entry.

    Args:
        session: Database session
        entry_id: PredictionEntry to calculate points for
        outcome_counts_by_fixture: Optional precomputed
            get_all_outcome_counts() result. The leaderboard rebuild
            computes it once and passes it to every entry; single-entry
            callers omit it and it is computed here.
        actual_advancement: Optional precomputed get_actual_advancement()
            result, same batching rationale.
        knockout_scoring_enabled: Optional precomputed competition flag.
            When False, ALL advancement-point payouts (group_advance,
            group_position, round_of_32 … winner) are suppressed for
            this entry — they sit at zero until the admin flips the
            switch (v2.181.1). Match-points (group-stage fixtures only)
            are unaffected. When None, looked up from the active
            competition row.

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

    # Rarity bonus uses per-fixture predictor counts: "the room that
    # showed up" (eligible entries only), not all active entries.
    # Computed once here when not supplied by a batched caller.
    if rows and outcome_counts_by_fixture is None:
        outcome_counts_by_fixture = await get_all_outcome_counts(session)

    for prediction, score, fixture in rows:
        if not score:
            continue

        total_predictions += 1

        outcome_counts = (outcome_counts_by_fixture or {}).get(
            fixture.id, {"1": 0, "X": 0, "2": 0}
        )
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

    # Team-advancement predictions. Gated on the competition flag
    # (v2.181.1): when knockout scoring is OFF, every advancement payout
    # — including the group_advance / group_position bracket credits —
    # sits at zero. We skip the queries entirely in that case so the
    # cold-rebuild path doesn't waste a round trip per entry.
    if knockout_scoring_enabled is None:
        knockout_scoring_enabled = await is_knockout_scoring_enabled(session)

    if knockout_scoring_enabled:
        result = await session.execute(
            select(TeamPrediction).where(TeamPrediction.entry_id == entry_id)
        )
        team_predictions = result.scalars().all()

        if actual_advancement is None:
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


