"""Entry-scoped prediction endpoints.

All routes are mounted under `/api/entries/{entry_id}/predictions`.
The API layer is thin: it parses inputs, calls the service, and
translates typed exceptions to HTTP status codes. All business logic
(lock enforcement, audit writes, prediction transforms) lives in
`services/predictions.py`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, DbSession
from app.models.prediction import PredictionPhase, TeamPrediction, normalize_stage
from app.schemas.prediction import (
    BracketPrediction,
    BracketPredictionUpdate,
    MatchPredictionCreate,
    MatchPredictionRead,
    MatchPredictionUpdate,
)
from app.services import entries as entries_service
from app.services import predictions as predictions_service
from app.services.audit import AuditContext, audit_context
from app.services.bonus import get_questions as get_bonus_questions
from app.services.bracket_exposure import compute_bracket_exposure
from app.services.entries import (
    EntryAccessDeniedError,
    EntryConfigError,
    EntryNotFoundError,
)
from app.services.predictions import (
    PredictionAccessDeniedError,
    PredictionLockedError,
    PredictionValidationError,
)


router = APIRouter()
AuditCtx = Annotated[AuditContext, Depends(audit_context)]


# ---------------------------------------------------------------------------
# Response schemas used only here
# ---------------------------------------------------------------------------
class BonusPredictionResponse(BaseModel):
    question_id: str
    answer: str


class BonusPredictionUpdate(BaseModel):
    question_id: str
    answer: str


class BonusPredictionBatch(BaseModel):
    predictions: list[BonusPredictionUpdate]


class BracketExposureResponse(BaseModel):
    points_available: int
    picks_locked: int
    picks_total: int
    final_winner: str | None
    final_opponent: str | None


class FixtureAgreement(BaseModel):
    fixture_id: uuid.UUID
    agrees_exact: int
    agrees_outcome: int
    total: int


# ---------------------------------------------------------------------------
# Exception → HTTP translation
# ---------------------------------------------------------------------------
def _raise_for(exc: Exception) -> None:
    """Translate typed service exceptions to HTTPException."""
    if isinstance(exc, EntryNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, EntryAccessDeniedError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, PredictionAccessDeniedError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, PredictionLockedError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, PredictionValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    raise exc


async def _get_competition_and_entry(
    session: AsyncSession, entry_id: uuid.UUID, user
):
    """Resolve the active competition + load the entry with ownership check.

    Used by mutating routes (upsert / batch / replace / save). Service-layer
    guards (`_entry_is_active`) reject mutations on disabled entries
    independently — keep this helper on the strict owner check.
    """
    try:
        competition = await entries_service.get_active_competition(session)
    except EntryConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    try:
        entry = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=user
        )
    except Exception as exc:
        _raise_for(exc)
    return competition, entry


async def _get_competition_and_entry_for_view(
    session: AsyncSession, entry_id: uuid.UUID, user
):
    """Resolve the active competition + load the entry through the
    visibility gate.

    Used by GET routes that return entry-prediction data. Routing through
    `get_entry_for_view` ensures the owner cannot read predictions for
    their own disabled entry (ghost mode), while preserving the existing
    blind-pool rule for non-owners.
    """
    try:
        competition = await entries_service.get_active_competition(session)
    except EntryConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    try:
        entry = await entries_service.get_entry_for_view(
            session, entry_id=entry_id, viewer=user
        )
    except Exception as exc:
        _raise_for(exc)
    return competition, entry


# ---------------------------------------------------------------------------
# Match predictions
# ---------------------------------------------------------------------------
def _to_match_read(pred, fixture) -> MatchPredictionRead:
    return MatchPredictionRead(
        id=pred.id,
        fixture_id=pred.fixture_id,
        home_score=pred.home_score,
        away_score=pred.away_score,
        phase=pred.phase,
        locked_at=pred.locked_at,
        created_at=pred.created_at,
        updated_at=pred.updated_at,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        kickoff=fixture.kickoff,
        is_locked=fixture.is_locked(),
    )


@router.get(
    "/{entry_id}/predictions/matches",
    response_model=list[MatchPredictionRead],
)
async def list_match_predictions(
    entry_id: uuid.UUID, session: DbSession, current_user: CurrentUser
) -> list[MatchPredictionRead]:
    _competition, entry = await _get_competition_and_entry_for_view(
        session, entry_id, current_user
    )
    rows = await predictions_service.get_match_predictions(session, entry=entry)
    return [_to_match_read(pred, fixture) for pred, fixture in rows]


@router.put(
    "/{entry_id}/predictions/matches/{fixture_id}",
    response_model=MatchPredictionRead,
)
async def upsert_match_prediction(
    entry_id: uuid.UUID,
    fixture_id: uuid.UUID,
    payload: MatchPredictionUpdate,
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> MatchPredictionRead:
    competition, entry = await _get_competition_and_entry(
        session, entry_id, current_user
    )
    try:
        pred = await predictions_service.upsert_match_prediction(
            session,
            entry=entry,
            user=current_user,
            competition=competition,
            fixture_id=fixture_id,
            home_score=payload.home_score,
            away_score=payload.away_score,
            ctx=ctx,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)

    # Reload the prediction + fixture for the response.
    from sqlmodel import select

    from app.models.fixture import Fixture
    from app.models.prediction import MatchPrediction

    row = (
        await session.execute(
            select(MatchPrediction, Fixture)
            .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
            .where(MatchPrediction.id == pred.id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=500, detail="Prediction vanished after upsert")
    return _to_match_read(row[0], row[1])


@router.post(
    "/{entry_id}/predictions/matches/batch",
    response_model=list[MatchPredictionRead],
)
async def batch_upsert_match_predictions(
    entry_id: uuid.UUID,
    payload: list[MatchPredictionCreate],
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> list[MatchPredictionRead]:
    competition, entry = await _get_competition_and_entry(
        session, entry_id, current_user
    )
    items = [(p.fixture_id, p.home_score, p.away_score) for p in payload]
    try:
        await predictions_service.batch_upsert_match_predictions(
            session,
            entry=entry,
            user=current_user,
            competition=competition,
            items=items,
            ctx=ctx,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)

    # Refetch + return the full current set for the entry.
    rows = await predictions_service.get_match_predictions(session, entry=entry)
    return [_to_match_read(pred, fixture) for pred, fixture in rows]


# ---------------------------------------------------------------------------
# Bracket predictions
# ---------------------------------------------------------------------------
def _organize_bracket(rows: list[TeamPrediction]) -> BracketPrediction:
    """Group flat TeamPrediction rows into the bracket response shape.

    Stored stage values are SINGULAR (matching Fixture.stage + scoring);
    the BracketPrediction response fields keep plural QF/SF names as a
    frontend display convention. normalize_stage() guards against any
    legacy plural rows that survive the v2.161.0 data migration.
    """
    group_winners: dict[str, list[str]] = {}
    stages: dict[str, list[str]] = {
        "round_of_32": [],
        "round_of_16": [],
        "quarter_final": [],
        "semi_final": [],
        "final": [],
    }
    winner = ""

    for pred in rows:
        stage = normalize_stage(pred.stage)
        if stage == "group":
            # Group-position picks aren't exposed via the bracket response
            # for now (the response schema doesn't carry positions).
            pass
        elif stage == "winner":
            winner = pred.team
        elif stage in stages:
            stages[stage].append(pred.team)

    return BracketPrediction(
        group_winners=group_winners,
        round_of_32=stages["round_of_32"],
        round_of_16=stages["round_of_16"],
        quarter_finals=stages["quarter_final"],
        semi_finals=stages["semi_final"],
        final=stages["final"],
        winner=winner,
    )


@router.get(
    "/{entry_id}/predictions/bracket",
    response_model=BracketPrediction | None,
)
async def get_bracket_predictions(
    entry_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
    phase: str | None = Query(default=None),
) -> BracketPrediction | None:
    """Read bracket picks for an entry. Defaults to the current active phase."""
    _competition, entry = await _get_competition_and_entry_for_view(
        session, entry_id, current_user
    )
    target_phase = (
        PredictionPhase(phase)
        if phase
        else await __get_current_phase(session)
    )
    rows = await predictions_service.get_bracket_predictions(
        session, entry=entry, phase=target_phase
    )
    if not rows:
        return None
    return _organize_bracket(rows)


@router.put(
    "/{entry_id}/predictions/bracket",
    response_model=dict,
)
async def replace_bracket_predictions(
    entry_id: uuid.UUID,
    payload: BracketPredictionUpdate,
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> dict:
    competition, entry = await _get_competition_and_entry(
        session, entry_id, current_user
    )
    picks = [
        {
            "team": p.team,
            "stage": p.stage,
            "group_position": p.group_position,
        }
        for p in payload.predictions
    ]
    try:
        await predictions_service.replace_bracket_predictions(
            session,
            entry=entry,
            user=current_user,
            competition=competition,
            picks=picks,
            ctx=ctx,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return {"status": "ok"}


async def __get_current_phase(session: AsyncSession) -> PredictionPhase:
    """Thin shim over locking.get_current_phase to keep imports local."""
    from app.services.locking import get_current_phase

    return await get_current_phase(session)


# ---------------------------------------------------------------------------
# Bonus predictions
# ---------------------------------------------------------------------------
@router.get(
    "/{entry_id}/predictions/bonus",
    response_model=list[BonusPredictionResponse],
)
async def get_bonus_predictions(
    entry_id: uuid.UUID, session: DbSession, current_user: CurrentUser
) -> list[BonusPredictionResponse]:
    _competition, entry = await _get_competition_and_entry_for_view(
        session, entry_id, current_user
    )
    rows = await predictions_service.get_bonus_predictions(session, entry=entry)
    return [
        BonusPredictionResponse(question_id=r.question_id, answer=r.answer)
        for r in rows
    ]


@router.post(
    "/{entry_id}/predictions/bonus",
    response_model=list[BonusPredictionResponse],
)
async def save_bonus_predictions(
    entry_id: uuid.UUID,
    payload: BonusPredictionBatch,
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> list[BonusPredictionResponse]:
    competition, entry = await _get_competition_and_entry(
        session, entry_id, current_user
    )
    valid_ids = {q.id for q in get_bonus_questions()}
    picks = [(p.question_id, p.answer) for p in payload.predictions]
    try:
        rows = await predictions_service.upsert_bonus_predictions(
            session,
            entry=entry,
            user=current_user,
            competition=competition,
            picks=picks,
            valid_question_ids=valid_ids,
            ctx=ctx,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return [
        BonusPredictionResponse(question_id=r.question_id, answer=r.answer)
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Bracket exposure & agreements (read-only per-entry views)
# ---------------------------------------------------------------------------
@router.get(
    "/{entry_id}/predictions/bracket-exposure",
    response_model=BracketExposureResponse,
)
async def get_bracket_exposure(
    entry_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
    phase: str = Query(default="phase_1"),
) -> BracketExposureResponse:
    _competition, entry = await _get_competition_and_entry_for_view(
        session, entry_id, current_user
    )
    phase_enum = (
        PredictionPhase.PHASE_2 if phase == "phase_2" else PredictionPhase.PHASE_1
    )
    result = await compute_bracket_exposure(session, entry.id, phase_enum)
    return BracketExposureResponse(
        points_available=result.points_available,
        picks_locked=result.picks_locked,
        picks_total=result.picks_total,
        final_winner=result.final_winner,
        final_opponent=result.final_opponent,
    )


@router.get(
    "/{entry_id}/predictions/agreements",
    response_model=list[FixtureAgreement],
)
async def get_agreements(
    entry_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
    fixture_ids: list[uuid.UUID] | None = Query(default=None),
) -> list[FixtureAgreement]:
    _competition, entry = await _get_competition_and_entry_for_view(
        session, entry_id, current_user
    )
    rows = await predictions_service.compute_agreements(
        session, entry=entry, fixture_ids=fixture_ids
    )
    return [FixtureAgreement(**r) for r in rows]
