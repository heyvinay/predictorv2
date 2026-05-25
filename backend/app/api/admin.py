"""Admin API routes for dashboard and management."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from app.dependencies import AdminUser, DbSession
from app.models._datetime import utc_now
from app.models.bonus import BonusAnswer
from app.models.competition import Competition
from app.models.entry import PredictionEntry
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.services.bonus import (
    compute_bonus_answers_for_competition,
    get_questions as get_bonus_questions,
)
from app.services.external_scores import get_score_provider, ExternalScore
from app.services.leaderboard import invalidate_cache
from app.services.score_sync import sync_scores_once


router = APIRouter()


class AdminStats(BaseModel):
    """Admin dashboard statistics."""

    total_users: int
    active_users: int
    total_fixtures: int
    completed_fixtures: int
    live_fixtures: int
    total_predictions: int
    total_scores: int


class UserAdminView(BaseModel):
    """User data for admin view."""

    id: uuid.UUID
    email: str
    # Nullable because magic-link sign-ups before /onboarding completion
    # have name=None. Admin UI shows the email as a fallback.
    name: str | None
    auth_provider: str
    is_admin: bool
    is_active: bool
    paid: bool
    created_at: datetime
    prediction_count: int

    class Config:
        """Pydantic config."""

        from_attributes = True


class CompetitionAdminView(BaseModel):
    """Competition data for admin view."""

    id: uuid.UUID
    name: str
    entry_fee: float
    phase1_deadline: datetime | None
    is_phase2_active: bool
    phase2_activated_at: datetime | None
    phase2_bracket_deadline: datetime | None
    phase2_deadline: datetime | None
    is_active: bool
    fixture_count: int
    user_count: int

    class Config:
        """Pydantic config."""

        from_attributes = True


class Phase1DeadlineRequest(BaseModel):
    """Request to set Phase 1 deadline."""

    deadline: datetime  # When Phase 1 predictions lock


class Phase2ActivateRequest(BaseModel):
    """Request to activate Phase 2."""

    bracket_deadline: datetime  # When Phase 2 bracket predictions lock


@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    session: DbSession,
    _admin: AdminUser,
) -> AdminStats:
    """Get admin dashboard statistics."""
    # User counts
    total_users = await session.scalar(select(func.count(User.id)))
    active_users = await session.scalar(
        select(func.count(User.id)).where(User.is_active == True)
    )

    # Fixture counts
    total_fixtures = await session.scalar(select(func.count(Fixture.id)))
    completed_fixtures = await session.scalar(
        select(func.count(Fixture.id)).where(Fixture.status == MatchStatus.FINISHED)
    )
    live_fixtures = await session.scalar(
        select(func.count(Fixture.id)).where(
            Fixture.status.in_([MatchStatus.LIVE, MatchStatus.HALFTIME])
        )
    )

    # Prediction and score counts
    total_predictions = await session.scalar(select(func.count(MatchPrediction.id)))
    total_scores = await session.scalar(select(func.count(Score.id)))

    return AdminStats(
        total_users=total_users or 0,
        active_users=active_users or 0,
        total_fixtures=total_fixtures or 0,
        completed_fixtures=completed_fixtures or 0,
        live_fixtures=live_fixtures or 0,
        total_predictions=total_predictions or 0,
        total_scores=total_scores or 0,
    )


@router.get("/users", response_model=list[UserAdminView])
async def get_all_users(
    session: DbSession,
    _admin: AdminUser,
) -> list[UserAdminView]:
    """Get all users with prediction counts (admin only)."""
    # Get users with prediction counts
    # Count prediction rows across every entry the user owns. Predictions
    # are entry-scoped, so we hop through PredictionEntry to attribute them
    # back to the user.
    result = await session.execute(
        select(
            User,
            func.count(MatchPrediction.id).label("prediction_count")
        )
        .outerjoin(PredictionEntry, User.id == PredictionEntry.user_id)
        .outerjoin(MatchPrediction, MatchPrediction.entry_id == PredictionEntry.id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    rows = result.all()

    return [
        UserAdminView(
            id=user.id,
            email=user.email,
            name=user.name,
            auth_provider=user.auth_provider.value,
            is_admin=user.is_admin,
            is_active=user.is_active,
            paid=user.paid,
            created_at=user.created_at,
            prediction_count=count,
        )
        for user, count in rows
    ]


@router.patch("/users/{user_id}/admin", response_model=UserAdminView)
async def toggle_user_admin(
    user_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> UserAdminView:
    """Toggle admin status for a user (admin only)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_admin = not user.is_admin
    user.updated_at = utc_now()
    await session.commit()
    await session.refresh(user)

    # Get prediction count
    count = await session.scalar(
        select(func.count(MatchPrediction.id))
        .join(PredictionEntry, MatchPrediction.entry_id == PredictionEntry.id)
        .where(PredictionEntry.user_id == user_id)
    )

    return UserAdminView(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider.value,
        is_admin=user.is_admin,
        is_active=user.is_active,
        paid=user.paid,
        created_at=user.created_at,
        prediction_count=count or 0,
    )


@router.patch("/users/{user_id}/active", response_model=UserAdminView)
async def toggle_user_active(
    user_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> UserAdminView:
    """Toggle active status for a user (admin only)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = not user.is_active
    user.updated_at = utc_now()
    await session.commit()
    await session.refresh(user)

    # Get prediction count
    count = await session.scalar(
        select(func.count(MatchPrediction.id))
        .join(PredictionEntry, MatchPrediction.entry_id == PredictionEntry.id)
        .where(PredictionEntry.user_id == user_id)
    )

    return UserAdminView(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider.value,
        is_admin=user.is_admin,
        is_active=user.is_active,
        paid=user.paid,
        created_at=user.created_at,
        prediction_count=count or 0,
    )


@router.patch("/users/{user_id}/paid", response_model=UserAdminView)
async def toggle_user_paid(
    user_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> UserAdminView:
    """Toggle paid status for a user (admin only). Used to track who has
    paid the competition entry fee."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.paid = not user.paid
    user.updated_at = utc_now()
    await session.commit()
    await session.refresh(user)

    count = await session.scalar(
        select(func.count(MatchPrediction.id))
        .join(PredictionEntry, MatchPrediction.entry_id == PredictionEntry.id)
        .where(PredictionEntry.user_id == user_id)
    )

    return UserAdminView(
        id=user.id,
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider.value,
        is_admin=user.is_admin,
        is_active=user.is_active,
        paid=user.paid,
        created_at=user.created_at,
        prediction_count=count or 0,
    )


@router.get("/competitions", response_model=list[CompetitionAdminView])
async def get_all_competitions(
    session: DbSession,
    _admin: AdminUser,
) -> list[CompetitionAdminView]:
    """Get all competitions with stats (admin only)."""
    result = await session.execute(
        select(
            Competition,
            func.count(func.distinct(Fixture.id)).label("fixture_count"),
            func.count(func.distinct(User.id)).label("user_count"),
        )
        .outerjoin(Fixture, Competition.id == Fixture.competition_id)
        .outerjoin(User, Competition.id == User.competition_id)
        .group_by(Competition.id)
        .order_by(Competition.created_at.desc())
    )
    rows = result.all()

    return [
        CompetitionAdminView(
            id=comp.id,
            name=comp.name,
            entry_fee=float(comp.entry_fee),
            phase1_deadline=comp.phase1_deadline,
            is_phase2_active=comp.is_phase2_active,
            phase2_activated_at=comp.phase2_activated_at,
            phase2_bracket_deadline=comp.phase2_bracket_deadline,
            phase2_deadline=comp.phase2_deadline,
            is_active=comp.is_active,
            fixture_count=fixture_count,
            user_count=user_count,
        )
        for comp, fixture_count, user_count in rows
    ]


@router.post("/competition/phase2/activate")
async def activate_phase2(
    request: Phase2ActivateRequest,
    session: DbSession,
    _admin: AdminUser,
) -> dict:
    """Activate Phase 2 for the active competition.

    This enables the Phase 2 tab for all users and sets the bracket deadline.
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found"
        )

    if competition.is_phase2_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phase 2 is already active"
        )

    # Activate Phase 2
    competition.is_phase2_active = True
    competition.phase2_activated_at = utc_now()
    competition.phase2_bracket_deadline = request.bracket_deadline
    competition.updated_at = utc_now()

    await session.commit()

    return {
        "status": "Phase 2 activated",
        "bracket_deadline": request.bracket_deadline.isoformat(),
        "activated_at": competition.phase2_activated_at.isoformat(),
    }


@router.post("/competition/phase2/deactivate")
async def deactivate_phase2(
    session: DbSession,
    _admin: AdminUser,
) -> dict:
    """Deactivate Phase 2 for the active competition.

    This hides the Phase 2 tab. Useful for testing or rollback.
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found"
        )

    if not competition.is_phase2_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phase 2 is not active"
        )

    # Deactivate Phase 2
    competition.is_phase2_active = False
    competition.updated_at = utc_now()

    await session.commit()

    return {"status": "Phase 2 deactivated"}


@router.post("/competition/phase1/deadline")
async def set_phase1_deadline(
    request: Phase1DeadlineRequest,
    session: DbSession,
    _admin: AdminUser,
) -> dict:
    """Set the Phase 1 deadline for the active competition.

    This sets when group stage predictions lock.
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found"
        )

    competition.phase1_deadline = request.deadline
    competition.updated_at = utc_now()

    await session.commit()

    return {
        "status": "Phase 1 deadline set",
        "deadline": request.deadline.isoformat(),
    }


class SyncScoresResponse(BaseModel):
    """Response from score sync operation."""

    synced: int
    updated: int
    errors: list[str]


@router.post("/scores/sync", response_model=SyncScoresResponse)
async def sync_scores_from_api(
    session: DbSession,
    _admin: AdminUser,
) -> SyncScoresResponse:
    """Sync live scores from external API (admin only).

    Thin wrapper around `score_sync.sync_scores_once`. The same code path
    powers the background scheduler — this endpoint is the manual escape
    hatch.
    """
    result = await sync_scores_once(session)
    return SyncScoresResponse(
        synced=result.synced,
        updated=result.updated,
        errors=result.errors,
    )


# ============================================================================
# Bonus question answers (admin sets the correct answer per question)
# ============================================================================


class BonusAnswerView(BaseModel):
    """One question + the full list of correct answers (empty if unresolved),
    for the admin UI. Multiple entries in `correct_answers` indicate a tie —
    every entry awards full points to any user who picked it.

    `computed_answers` is the auto-derived answer(s) calculated from
    fixtures + scores (for group_stage and top_flop questions). It's
    purely advisory: the admin can apply it via the UI or override with
    a manual entry. Awards-category questions always have an empty
    `computed_answers` since they're manual-only."""

    question_id: str
    label: str
    category: str
    points: int
    input_type: str
    correct_answers: list[str]
    computed_answers: list[str]
    resolved_at: datetime | None


class BonusAnswerUpdate(BaseModel):
    """Payload for admin setting / replacing the correct answers for a
    question. The full list replaces whatever was previously stored —
    empty list un-resolves the question."""

    question_id: str
    correct_answers: list[str]


def _build_view(
    q,
    rows: list[BonusAnswer] | None,
    computed: list[str] | None = None,
) -> BonusAnswerView:
    """Helper: assemble a BonusAnswerView from a question definition +
    its (possibly empty) list of stored answer rows. `resolved_at` is the
    most recent resolution timestamp across rows; falsy if no rows.
    `computed` is the auto-derived suggestion (empty for awards or when
    no data is available yet)."""
    rs = rows or []
    return BonusAnswerView(
        question_id=q.id,
        label=q.label,
        category=q.category,
        points=q.points,
        input_type=q.input_type,
        correct_answers=[r.correct_answer for r in rs],
        computed_answers=computed or [],
        resolved_at=max((r.resolved_at for r in rs), default=None) if rs else None,
    )


@router.get("/bonus/answers", response_model=list[BonusAnswerView])
async def list_bonus_answers(
    session: DbSession,
    _admin: AdminUser,
) -> list[BonusAnswerView]:
    """List every bonus question with its full list of stored correct
    answers. Joins the YAML question list with the per-competition
    `bonus_answers` rows; questions with no stored answer get an empty
    list and a null `resolved_at`.
    """
    qs = get_bonus_questions()
    comp_result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = comp_result.scalar_one_or_none()
    if not competition:
        return [_build_view(q, None) for q in qs]

    ans_result = await session.execute(
        select(BonusAnswer).where(BonusAnswer.competition_id == competition.id)
    )
    rows_by_qid: dict[str, list[BonusAnswer]] = {}
    for row in ans_result.scalars().all():
        rows_by_qid.setdefault(row.question_id, []).append(row)

    # Auto-computed suggestions for group_stage + top_flop questions.
    # Awards have no entries here (manual-only) and the helper returns []
    # for any qid it doesn't know about, so we don't need to special-case
    # them — they just see an empty `computed_answers` field.
    computed_by_qid = await compute_bonus_answers_for_competition(
        session, competition.id
    )

    return [
        _build_view(q, rows_by_qid.get(q.id), computed_by_qid.get(q.id, []))
        for q in qs
    ]


@router.post("/bonus/answers", response_model=BonusAnswerView)
async def set_bonus_answer(
    payload: BonusAnswerUpdate,
    session: DbSession,
    _admin: AdminUser,
) -> BonusAnswerView:
    """Replace the correct answers for a bonus question. Empty list
    un-resolves the question (all existing rows deleted). Multiple
    entries record a tie — every entry awards full points. Invalidates
    the leaderboard cache so points propagate on the next fetch."""
    valid_questions = {q.id: q for q in get_bonus_questions()}
    if payload.question_id not in valid_questions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown question_id: {payload.question_id}",
        )

    comp_result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = comp_result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition",
        )

    # Normalise + dedupe inbound answers, dropping empty entries.
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in payload.correct_answers:
        s = (raw or "").strip()
        if not s:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s)

    q = valid_questions[payload.question_id]

    # Replace-all semantics: delete every row for this (comp, question)
    # and re-insert the new set. Simpler than diffing, and the table is
    # tiny (12 questions × ~3 answers).
    existing_rows = (
        await session.execute(
            select(BonusAnswer)
            .where(BonusAnswer.competition_id == competition.id)
            .where(BonusAnswer.question_id == payload.question_id)
        )
    ).scalars().all()
    for row in existing_rows:
        await session.delete(row)

    new_rows: list[BonusAnswer] = []
    for ans in cleaned:
        row = BonusAnswer(
            competition_id=competition.id,
            question_id=payload.question_id,
            correct_answer=ans,
        )
        session.add(row)
        new_rows.append(row)
    await session.commit()
    for row in new_rows:
        await session.refresh(row)
    invalidate_cache()

    # Re-compute the auto-suggestion so the frontend can keep showing the
    # "Use computed" chip after a manual save.
    computed_by_qid = await compute_bonus_answers_for_competition(
        session, competition.id
    )
    return _build_view(q, new_rows, computed_by_qid.get(q.id, []))
