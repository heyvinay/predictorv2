"""Profile service — entry-scoped stats.

The profile/me-stats endpoint historically returned a user-level
aggregate. That violated the "scores accumulate at the entry level, not
the user level" invariant: a user with two entries doesn't *have* points,
their entries do. So this service now resolves to a single entry per call.

Callers pass either:
- an explicit `entry_id` (the page lets the user pick which of their
  entries to view), or
- nothing — and we resolve to the user's most-recently-updated eligible
  entry as a sensible default.

If the user has no eligible entries (none submitted, all withdrawn, etc.)
this returns a zero-stats payload rather than 404 — the calling page
should show "no entry yet" UX rather than an error.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.entry import PredictionEntry
from app.models.prediction import MatchPrediction, TeamPrediction
from app.schemas.auth import UserStats
from app.schemas.leaderboard import PointBreakdown
from app.services.leaderboard import calculate_leaderboard
from app.services.scoring import calculate_entry_points, resolve_default_entry_id


async def calculate_user_stats(
    session: AsyncSession,
    user_id: uuid.UUID,
    entry_id: uuid.UUID | None = None,
) -> UserStats:
    """Profile statistics for one of the user's entries.

    Args:
        session: Database session
        user_id: The user whose stats we're reporting (for access control
            in the calling API layer — we still verify entry ownership)
        entry_id: Optional explicit entry. If None, resolves to the user's
            most recently-updated eligible entry.

    Returns:
        UserStats. Zero-valued if the user has no eligible entries.
    """
    if entry_id is None:
        entry_id = await resolve_default_entry_id(session, user_id)

    if entry_id is None:
        # No eligible entry to report on — return zero stats.
        leaderboard = await calculate_leaderboard(session)
        return UserStats(
            total_match_predictions=0,
            total_team_predictions=0,
            total_predictions=0,
            correct_outcomes=0,
            exact_scores=0,
            accuracy_pct=0.0,
            total_points=0,
            leaderboard_position=None,
            total_participants=leaderboard.total_participants,
            breakdown=PointBreakdown(),
        )

    breakdown = await calculate_entry_points(session, entry_id)

    # Leaderboard position for this specific entry (not the user's best
    # entry — that would be a back-door form of user-level aggregation).
    leaderboard = await calculate_leaderboard(session)
    position = next(
        (row.position for row in leaderboard.entries if row.entry_id == entry_id),
        None,
    )

    # Raw prediction counts for this entry only.
    match_count_result = await session.execute(
        select(func.count(MatchPrediction.id)).where(
            MatchPrediction.entry_id == entry_id
        )
    )
    total_match_predictions = match_count_result.scalar_one()

    team_count_result = await session.execute(
        select(func.count(TeamPrediction.id)).where(
            TeamPrediction.entry_id == entry_id
        )
    )
    total_team_predictions = team_count_result.scalar_one()

    total_predictions = total_match_predictions + total_team_predictions

    accuracy_pct = 0.0
    if breakdown.total_predictions > 0:
        accuracy_pct = round(
            (breakdown.correct_outcomes / breakdown.total_predictions) * 100, 1
        )

    return UserStats(
        total_match_predictions=total_match_predictions,
        total_team_predictions=total_team_predictions,
        total_predictions=total_predictions,
        correct_outcomes=breakdown.correct_outcomes,
        exact_scores=breakdown.exact_scores,
        accuracy_pct=accuracy_pct,
        total_points=breakdown.total,
        leaderboard_position=position,
        total_participants=leaderboard.total_participants,
        breakdown=breakdown,
    )
