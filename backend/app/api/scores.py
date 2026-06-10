"""Scores API routes."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from app.dependencies import AdminUser, DbSession, OptionalUser
from app.models._datetime import utc_now
from app.models.audit import ActorRole
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource
from app.schemas.leaderboard import LeaderboardEntry
from app.schemas.score import LiveMatchScore, LiveScoreResponse, ScoreRead, ScoreUpdate
from app.services.audit import record_audit_event
from app.services.leaderboard import calculate_leaderboard, invalidate_cache

router = APIRouter()


class LivePollingResponse(BaseModel):
    """Combined response for live polling (scores + leaderboard)."""

    matches: list[LiveMatchScore]
    leaderboard: list[LeaderboardEntry]
    last_updated: datetime


@router.get("/live", response_model=LiveScoreResponse)
async def get_live_scores(session: DbSession, _user: OptionalUser) -> LiveScoreResponse:
    """Get live and recent scores for polling."""
    matches = await _get_live_matches(session)
    return LiveScoreResponse(matches=matches, last_updated=utc_now())


@router.get("/poll", response_model=LivePollingResponse)
async def poll_live_data(session: DbSession, _user: OptionalUser) -> LivePollingResponse:
    """Combined polling endpoint for live scores and leaderboard.

    Use this endpoint for efficient polling during live matches.
    Returns both current match scores and updated leaderboard in a single request.
    Recommended polling interval: 60 seconds.
    """
    matches = await _get_live_matches(session)
    leaderboard = await calculate_leaderboard(session)

    return LivePollingResponse(
        matches=matches,
        leaderboard=leaderboard.entries,
        last_updated=utc_now(),
    )


async def _get_live_matches(session: DbSession) -> list[LiveMatchScore]:
    """Get live and recent match scores."""
    result = await session.execute(
        select(Fixture, Score)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(Fixture.status.in_([MatchStatus.LIVE, MatchStatus.HALFTIME, MatchStatus.FINISHED]))
        .order_by(Fixture.kickoff.desc())
        .limit(50)
    )
    rows = result.all()

    matches = []
    for fixture, score in rows:
        matches.append(
            LiveMatchScore(
                fixture_id=fixture.id,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                home_score=score.home_score if score else 0,
                away_score=score.away_score if score else 0,
                status=fixture.status.value,
                minute=fixture.minute,
                kickoff=fixture.kickoff,
            )
        )

    return matches


@router.get("/{fixture_id}", response_model=ScoreRead | None)
async def get_score(
    fixture_id: uuid.UUID, session: DbSession, _user: OptionalUser
) -> ScoreRead | None:
    """Get score for a specific fixture."""
    result = await session.execute(select(Score).where(Score.fixture_id == fixture_id))
    score = result.scalar_one_or_none()

    if not score:
        return None

    return ScoreRead.model_validate(score)


@router.put("/{fixture_id}", response_model=ScoreRead)
async def update_score(
    fixture_id: uuid.UUID,
    score_data: ScoreUpdate,
    session: DbSession,
    admin: AdminUser,
) -> ScoreRead:
    """Update or create score for a fixture (admin only)."""
    # Verify fixture exists
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    # Get existing score or create new
    result = await session.execute(select(Score).where(Score.fixture_id == fixture_id))
    score = result.scalar_one_or_none()

    old_values = (
        {
            "home_score": score.home_score,
            "away_score": score.away_score,
            "home_score_et": score.home_score_et,
            "away_score_et": score.away_score_et,
            "home_penalties": score.home_penalties,
            "away_penalties": score.away_penalties,
            "verified": score.verified,
            "source": score.source.value,
        }
        if score
        else None
    )

    if score:
        score.home_score = score_data.home_score
        score.away_score = score_data.away_score
        score.home_score_et = score_data.home_score_et
        score.away_score_et = score_data.away_score_et
        score.home_penalties = score_data.home_penalties
        score.away_penalties = score_data.away_penalties
        score.verified = score_data.verified
        score.source = ScoreSource.MANUAL
        score.updated_at = utc_now()
    else:
        score = Score(
            fixture_id=fixture_id,
            home_score=score_data.home_score,
            away_score=score_data.away_score,
            home_score_et=score_data.home_score_et,
            away_score_et=score_data.away_score_et,
            home_penalties=score_data.home_penalties,
            away_penalties=score_data.away_penalties,
            verified=score_data.verified,
            source=ScoreSource.MANUAL,
        )
        session.add(score)

    # Update fixture status
    fixture.status = MatchStatus.FINISHED
    fixture.updated_at = utc_now()

    record_audit_event(
        session,
        event_type="score.manual_update",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="fixture",
        subject_id=fixture.id,
        metadata={
            "home_team": fixture.home_team,
            "away_team": fixture.away_team,
            "stage": fixture.stage,
            "old": old_values,
            "new": score_data.model_dump(),
        },
    )

    await session.commit()
    await session.refresh(score)

    # Invalidate leaderboard cache since scores changed
    invalidate_cache()

    return ScoreRead.model_validate(score)
