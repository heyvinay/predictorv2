"""Aggregated / static prediction endpoints.

Predictions are now entry-owned (see Task A schema + Task B service +
Task C entry-scoped endpoints in `entry_predictions.py`). The user-
scoped routes that used to live here (`GET /matches`, `PUT /matches/{id}`,
batch, bracket, bonus, bracket-exposure, agreements) are gone — they
each have a `/api/entries/{entry_id}/predictions/...` replacement.

Two endpoints remain here because they aren't user-state:

- `GET /matches/{fixture_id}/community` — aggregated view across all
  eligible entries for one fixture. Blind-pool gated.
- `GET /bonus/questions` — static YAML config; no user data.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.dependencies import DbSession, OptionalUser
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction
from app.models.user import User
from app.services.locking import is_phase1_locked
from app.schemas.fixture import FixtureScore
from app.schemas.prediction import CommunityPrediction, CommunityPredictionsResponse
from app.services.bonus import (
    get_meta as get_bonus_meta,
    get_questions as get_bonus_questions,
)

router = APIRouter()


class BonusQuestionResponse(BaseModel):
    """A bonus question rendered for the wizard/admin UI."""

    id: str
    category: str  # 'group_stage' | 'top_flop' | 'awards'
    label: str
    # 'team' | 'player' | 'team_outside_top_n' | 'team_in_top_n'
    input_type: str
    points: int


class BonusMetaResponse(BaseModel):
    """FIFA top_n cutoff and the team list it expands to.

    Consumed by the wizard so the dark_horse / flop dropdowns can be
    filtered against the YAML's `fifa_top_teams` list without the frontend
    needing its own copy. Order = FIFA rank (1..N).
    """

    top_n: int
    fifa_top_teams: list[str]


LOCK_MINUTES = 5


@router.get(
    "/matches/{fixture_id}/community", response_model=CommunityPredictionsResponse
)
async def get_community_predictions(
    fixture_id: uuid.UUID,
    session: DbSession,
    _user: OptionalUser,
) -> CommunityPredictionsResponse:
    """All eligible entries' predictions for a fixture (blind-pool gated).

    Visibility: predictions for ALL fixtures become visible the moment the
    global Phase 1 deadline passes (open-pool model — CLAUDE.md). The
    older per-fixture 5-minute pre-kickoff lock is kept as a belt-and-
    braces fallback so a single misconfigured deadline can't blow the
    blind pool open early. Once the deadline is past, every fixture's
    pool list, spread, and rarity split are immediately available — the
    upcoming match-detail page leans on this.
    """
    # Load fixture with score.
    fixture_row = await session.execute(
        select(Fixture).options(selectinload(Fixture.score)).where(Fixture.id == fixture_id)
    )
    fixture = fixture_row.scalar_one_or_none()
    if not fixture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found"
        )

    # Blind-pool gate: global deadline OR per-fixture lock OR finished.
    deadline_passed = await is_phase1_locked(session)
    if (
        not deadline_passed
        and not fixture.is_locked(LOCK_MINUTES)
        and fixture.status != MatchStatus.FINISHED
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Predictions are not yet visible for this match",
        )

    # Join predictions with entry + user, filtered to entries whose phase
    # for this prediction is submitted-or-locked. This is the "eligible
    # entry" rule — drafts and ready entries don't show in the community
    # view because they could still change.
    rows = (
        await session.execute(
            select(
                MatchPrediction,
                PredictionEntry,
                User.name,
                User.email,
            )
            .join(
                PredictionEntry,
                MatchPrediction.entry_id == PredictionEntry.id,
            )
            .join(User, PredictionEntry.user_id == User.id)
            .join(
                PredictionEntryPhase,
                (PredictionEntryPhase.entry_id == PredictionEntry.id)
                & (PredictionEntryPhase.phase == MatchPrediction.phase),
            )
            .where(MatchPrediction.fixture_id == fixture_id)
            .where(PredictionEntry.withdrawn_at.is_(None))
            .where(PredictionEntry.is_disabled.is_(False))
            .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
        )
    ).all()

    # One cached leaderboard fetch → rank lookup table (30s TTL in the
    # service keeps this cheap; entries absent from the ranking get null).
    from app.services.leaderboard import calculate_leaderboard

    leaderboard = await calculate_leaderboard(session, phase=None)
    rank_by_entry = {e.entry_id: e.position for e in leaderboard.entries}

    predictions = [
        CommunityPrediction(
            # Fall back to the email-prefix for magic-link sign-ups that
            # haven't completed /onboarding (user_name may be None).
            user_name=user_name or user_email.split("@")[0],
            entry_reference=entry.reference,
            entry_name=entry.display_name,
            home_score=pred.home_score,
            away_score=pred.away_score,
            rank=rank_by_entry.get(entry.id),
        )
        for pred, entry, user_name, user_email in rows
    ]

    actual = None
    if fixture.status == MatchStatus.FINISHED and fixture.score:
        actual = FixtureScore(
            home_score=fixture.score.home_score,
            away_score=fixture.score.away_score,
            home_score_et=fixture.score.home_score_et,
            away_score_et=fixture.score.away_score_et,
            home_penalties=fixture.score.home_penalties,
            away_penalties=fixture.score.away_penalties,
            outcome=fixture.score.outcome,
        )

    return CommunityPredictionsResponse(
        fixture_id=fixture.id,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        predictions=predictions,
        actual=actual,
    )


@router.get("/bonus/questions", response_model=list[BonusQuestionResponse])
async def get_bonus_questions_route(
    _user: OptionalUser,
) -> list[BonusQuestionResponse]:
    """All bonus questions loaded from worldcup2026.yml.

    Public — the /rules page lists these for prospective joiners.
    Question IDs are stable strings used as upsert keys.
    """
    qs = get_bonus_questions()
    return [
        BonusQuestionResponse(
            id=q.id,
            category=q.category,
            label=q.label,
            input_type=q.input_type,
            points=q.points,
        )
        for q in qs
    ]


@router.get("/bonus/meta", response_model=BonusMetaResponse)
async def get_bonus_meta_route(
    _user: OptionalUser,
) -> BonusMetaResponse:
    """FIFA top_n cutoff and the team list it expands to.

    Used by the wizard to filter the dark_horse / flop dropdowns. Public —
    matches the auth level of /bonus/questions. The list is whatever the
    YAML's `bonus.fifa_top_teams` holds, in YAML order (= FIFA rank).
    """
    meta = get_bonus_meta()
    return BonusMetaResponse(
        top_n=meta.top_n,
        fifa_top_teams=meta.fifa_top_teams,
    )
