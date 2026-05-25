"""Users API routes — public profiles and prediction viewing."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.dependencies import DbSession, OptionalUser
from app.models.entry import PredictionEntry
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score
from app.models.user import User
from app.schemas.auth import UserStats
from app.services.profile import calculate_user_stats
from app.services.scoring import resolve_default_entry_id

router = APIRouter()

LOCK_MINUTES = 5


# Response schemas


class PublicProfile(BaseModel):
    """Public-facing user profile."""

    id: uuid.UUID
    name: str
    created_at: datetime
    stats: UserStats


class UserMatchPredictionView(BaseModel):
    """A user's prediction for a single match, with fixture context and result data."""

    fixture_id: uuid.UUID
    home_team: str
    away_team: str
    kickoff: datetime
    stage: str
    group: str | None
    status: MatchStatus
    # The user's prediction
    predicted_home: int
    predicted_away: int
    # Actual result (only for finished fixtures with scores)
    actual_home: int | None = None
    actual_away: int | None = None
    actual_outcome: str | None = None
    # Result flags
    is_exact: bool = False
    is_correct_outcome: bool = False


class BracketSummary(BaseModel):
    """Summary of bracket predictions grouped by stage, with phase separation."""

    stages: dict[str, list[str]]  # stage -> [team names] (merged, backward compat)
    phase1_stages: dict[str, list[str]] = {}  # Phase 1 bracket
    phase2_stages: dict[str, list[str]] = {}  # Phase 2 bracket


class UserPredictionsResponse(BaseModel):
    """All visible predictions for a user."""

    user_id: uuid.UUID
    user_name: str
    match_predictions: list[UserMatchPredictionView]
    bracket_summary: BracketSummary


# Endpoints


@router.get("/{user_id}/profile", response_model=PublicProfile)
async def get_user_profile(
    user_id: uuid.UUID,
    session: DbSession,
    _user: OptionalUser,
    entry_id: uuid.UUID | None = Query(
        None,
        description="Specific entry to report stats for. If omitted, picks the user's most recently-updated eligible entry.",
    ),
) -> PublicProfile:
    """Get public profile for a user.

    Stats are entry-scoped — the response represents one of the user's
    entries, not a user-level aggregate. Pass `entry_id` to target a
    specific entry; otherwise the most recently-updated eligible one is
    chosen.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    stats = await calculate_user_stats(session, user.id, entry_id=entry_id)

    return PublicProfile(
        id=user.id,
        name=user.name or user.email.split("@")[0],
        created_at=user.created_at,
        stats=stats,
    )


@router.get("/{user_id}/predictions", response_model=UserPredictionsResponse)
async def get_user_predictions(
    user_id: uuid.UUID,
    session: DbSession,
    _user: OptionalUser,
    entry_id: uuid.UUID | None = Query(
        None,
        description="Specific entry to read predictions from. If omitted, picks the user's most recently-updated eligible entry.",
    ),
) -> UserPredictionsResponse:
    """Get visible predictions for one of the user's entries.

    Predictions are entry-scoped — a user with two entries has two
    independent prediction sets. Pass `entry_id` to target a specific
    entry; otherwise the user's most recently-updated eligible entry
    is used.

    Blind pool enforced: only includes predictions for fixtures that are
    locked (5 min before kickoff) or finished.
    """
    # Verify user exists
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if entry_id is None:
        entry_id = await resolve_default_entry_id(session, user.id)

    if entry_id is None:
        # User has no eligible entry — return an empty payload.
        return UserPredictionsResponse(
            user_id=user.id,
            user_name=user.name or user.email.split("@")[0],
            match_predictions=[],
            bracket_summary=BracketSummary(
                stages={}, phase1_stages={}, phase2_stages={}
            ),
        )

    # Verify the entry belongs to this user (don't leak cross-user
    # predictions if a caller mismatches the params).
    owner_check = await session.execute(
        select(PredictionEntry.user_id).where(PredictionEntry.id == entry_id)
    )
    owner = owner_check.scalar_one_or_none()
    if owner != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found"
        )

    # Get match predictions with fixture and score data
    result = await session.execute(
        select(MatchPrediction, Fixture)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .options(selectinload(Fixture.score))
        .where(MatchPrediction.entry_id == entry_id)
        .order_by(Fixture.kickoff)
    )
    rows = result.all()

    match_predictions: list[UserMatchPredictionView] = []
    for pred, fixture in rows:
        # Blind pool: skip if not locked and not finished
        if not fixture.is_locked(LOCK_MINUTES) and fixture.status != MatchStatus.FINISHED:
            continue

        view = UserMatchPredictionView(
            fixture_id=fixture.id,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            kickoff=fixture.kickoff,
            stage=fixture.stage,
            group=fixture.group,
            status=fixture.status,
            predicted_home=pred.home_score,
            predicted_away=pred.away_score,
        )

        # Add actual result data for finished fixtures
        if fixture.status == MatchStatus.FINISHED and fixture.score:
            score = fixture.score
            view.actual_home = score.home_score
            view.actual_away = score.away_score
            view.actual_outcome = score.outcome

            # Check exact score
            view.is_exact = (
                pred.home_score == score.final_home_score
                and pred.away_score == score.final_away_score
            )

            # Check correct outcome
            pred_outcome = pred.predicted_outcome
            view.is_correct_outcome = pred_outcome == score.outcome

        match_predictions.append(view)

    # Bracket summary: group team predictions by stage and phase
    result = await session.execute(
        select(TeamPrediction).where(TeamPrediction.entry_id == entry_id)
    )
    team_preds = result.scalars().all()

    stages: dict[str, list[str]] = {}
    phase1_stages: dict[str, list[str]] = {}
    phase2_stages: dict[str, list[str]] = {}
    for tp in team_preds:
        stages.setdefault(tp.stage, []).append(tp.team)
        if tp.phase == PredictionPhase.PHASE_1:
            phase1_stages.setdefault(tp.stage, []).append(tp.team)
        else:
            phase2_stages.setdefault(tp.stage, []).append(tp.team)

    return UserPredictionsResponse(
        user_id=user.id,
        user_name=user.name or user.email.split("@")[0],
        match_predictions=match_predictions,
        bracket_summary=BracketSummary(
            stages=stages,
            phase1_stages=phase1_stages,
            phase2_stages=phase2_stages,
        ),
    )
