"""Admin API routes for dashboard and management."""

import asyncio
import csv
import io
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from app.config import get_settings
from app.dependencies import AdminUser, DbSession
from app.models._datetime import utc_now
from app.models.bonus import BonusAnswer
from app.models.competition import Competition
from app.models.entry import (
    ActorRole,
    EntryStatus,
    PredictionEntry,
    PredictionEntryPhase,
)
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.schemas.admin import (
    AdminBonusAnswer,
    AdminEntryPredictions,
    AuditEventPage,
    BroadcastAudienceCounts,
    BroadcastSendRequest,
    BroadcastSendResult,
    BroadcastTestRequest,
    BroadcastTestResult,
    EngagementSummary,
    FixtureMini,
    SitePulse,
    UserAdminPage,
    UserCohort,
    UserDetailRead,
)
from app.services import entries as entries_service
from app.services import posthog_read
from app.services import pulse as pulse_service
from app.services.audit import query_audit_events, record_audit_event
from app.services.locking import get_active_competition
from app.services.standings_verify import run_verification
from app.models.standings_drift import (
    DriftEventStatus,
    StandingsDriftEvent,
    TrustedSource,
)
from app.services.bonus import (
    compute_bonus_answers_for_competition,
    get_questions as get_bonus_questions,
)
from app.services.broadcast import (
    BroadcastSegment,
    count_all_audiences,
    query_audience,
)
from app.services.completeness import (
    EntryCompletenessResult,
    check_all_eligible_entries,
)
from app.services.email import (
    _compute_group_stage_winner_email_tokens,
    _compute_r2_highlights,
    send_broadcast_email,
)
from app.services.pool_close import PoolCloseError, close_pool, preview_pool_close
from app.services.external_scores import get_score_provider, ExternalScore
from app.services.leaderboard import invalidate_cache
from app.services.score_sync import sync_scores_once
from app.services.users import list_inactive_emails, list_users_with_cohort


router = APIRouter()


class AdminStats(BaseModel):
    """Admin dashboard statistics.

    ``recent_finished_fixtures`` + ``upcoming_fixtures`` (added v2.156.0)
    power the Score-sync card on the redesigned Overview page. Both lists
    are limited to 2 elements server-side; default to empty list rather
    than null so the frontend can render unconditionally.

    ``total_entries`` / ``submitted_entries`` / ``prize_pool`` (added
    v2.160.0) replace the Fixtures + Live cards on the Overview. Prize
    pool = active competition's ``entry_fee × submitted_entries`` — the
    user-facing "what's in the kitty?" number. Computed server-side so
    the math lives in one place; currency-agnostic (just a float).
    """

    total_users: int
    active_users: int
    total_fixtures: int
    completed_fixtures: int
    live_fixtures: int
    total_predictions: int
    total_scores: int
    total_entries: int = 0
    submitted_entries: int = 0
    prize_pool: float = 0.0
    recent_finished_fixtures: list[FixtureMini] = []
    upcoming_fixtures: list[FixtureMini] = []


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

    # Active competition first — both submitted_entries and prize_pool
    # are scoped to it via the shared service helper.
    active_comp = (
        await session.execute(
            select(Competition).where(Competition.is_active.is_(True)).limit(1)
        )
    ).scalar_one_or_none()

    # Total entries — scoped to active competition (was unscoped pre
    # v2.160.5; that inflated the count when test/past competitions
    # shared the DB).
    total_entries = (
        await session.scalar(
            select(func.count(PredictionEntry.id)).where(
                PredictionEntry.competition_id == active_comp.id
            )
        )
        if active_comp is not None
        else 0
    ) or 0

    # Submitted-entries count via the shared helper — same definition
    # as landing /api/landing/stats and the admin Entries page's
    # Submitted stat card. See ``count_eligible_submitted_entries`` in
    # services/entries.py for the canonical rule. Replaces the older
    # any-phase / any-comp query that double-counted via phase_2 rows.
    submitted_entries = (
        await entries_service.count_eligible_submitted_entries(
            session, competition=active_comp
        )
        if active_comp is not None
        else 0
    )

    entry_fee = float(active_comp.entry_fee) if active_comp else 0.0
    prize_pool = entry_fee * submitted_entries

    # Recent finished + upcoming fixtures — small lists (2 each) for the
    # Score-sync card on the Overview page. LEFT JOIN Score so finished
    # fixtures pick up their scores; upcoming fixtures have no scores
    # yet so the join is just LEFT-NULL by definition.
    recent_finished = list(
        (
            await session.execute(
                select(Fixture, Score)
                .outerjoin(Score, Score.fixture_id == Fixture.id)
                .where(Fixture.status == MatchStatus.FINISHED)
                .order_by(Fixture.kickoff.desc())
                .limit(2)
            )
        ).all()
    )
    now = utc_now()
    upcoming = list(
        (
            await session.execute(
                select(Fixture)
                .where(Fixture.status == MatchStatus.SCHEDULED)
                .where(Fixture.kickoff >= now)
                .order_by(Fixture.kickoff.asc())
                .limit(2)
            )
        )
        .scalars()
        .all()
    )

    def _mini(fx: Fixture, sc: Score | None = None) -> FixtureMini:
        return FixtureMini(
            id=fx.id,
            kickoff=fx.kickoff,
            home_team=fx.home_team,
            away_team=fx.away_team,
            home_code=None,
            away_code=None,
            home_score=sc.home_score if sc is not None else None,
            away_score=sc.away_score if sc is not None else None,
            status=fx.status.value,
        )

    return AdminStats(
        total_users=total_users or 0,
        active_users=active_users or 0,
        total_fixtures=total_fixtures or 0,
        completed_fixtures=completed_fixtures or 0,
        live_fixtures=live_fixtures or 0,
        total_predictions=total_predictions or 0,
        total_scores=total_scores or 0,
        total_entries=total_entries or 0,
        submitted_entries=submitted_entries,
        prize_pool=prize_pool,
        recent_finished_fixtures=[_mini(fx, sc) for fx, sc in recent_finished],
        upcoming_fixtures=[_mini(fx) for fx in upcoming],
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

    # Lockout guard (v2.166.0): never demote the LAST active admin —
    # with no admin left, nobody can flip go-live, manage users, or
    # restore admin rights. Promote someone else first.
    if user.is_admin:
        other_admins = await session.scalar(
            select(func.count(User.id)).where(
                User.is_admin == True,  # noqa: E712
                User.is_active == True,  # noqa: E712
                User.id != user.id,
            )
        )
        if not other_admins:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cannot remove admin from the last active admin — "
                    "promote another admin first."
                ),
            )

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

    # Lockout guard (v2.166.0): admin accounts can never be DEACTIVATED
    # — is_active=false blocks every login path (password, magic link,
    # OAuth), so a slip here locks the admin out of production for good.
    # Revoke admin first if an admin account truly must be disabled.
    # Re-activation is always allowed.
    if user.is_active and user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Admin accounts can't be deactivated — remove their "
                "admin role first."
            ),
        )

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


class GoLiveRequest(BaseModel):
    """Toggle the post-deadline release switch."""

    live: bool


@router.post("/competition/go-live")
async def set_post_deadline_live(
    request: GoLiveRequest,
    session: DbSession,
    admin: AdminUser,
) -> dict:
    """Flip the post-deadline release switch (v2.166.0).

    `live=true` opens the V4 dashboard / results / leaderboard to the
    whole pool; `live=false` pulls them back behind the holding stubs.
    The deadline passing alone no longer releases anything — this is
    the admin's manual okay after the post-deadline clean-up.
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found",
        )

    previous = competition.post_deadline_live
    competition.post_deadline_live = request.live
    competition.updated_at = utc_now()
    if previous != request.live:
        record_audit_event(
            session,
            event_type="competition.post_deadline_live_toggled",
            actor_user_id=admin.id,
            actor_role=ActorRole.ADMIN,
            subject_type="competition",
            subject_id=competition.id,
            metadata={"from": previous, "to": request.live},
        )
    await session.commit()

    return {"status": "ok", "post_deadline_live": request.live}


# ---------------------------------------------------------------------------
# Group Stage Winner release switch (v2.181.0)
# ---------------------------------------------------------------------------
class GroupStageWinnerReleaseRequest(BaseModel):
    """Toggle the Group Stage Winner card + broadcast visibility."""

    released: bool


@router.post("/competition/group-stage-winner/release")
async def set_group_stage_winner_released(
    request: GroupStageWinnerReleaseRequest,
    session: DbSession,
    admin: AdminUser,
) -> dict:
    """Flip the Group Stage Winner release switch (v2.181.0).

    `released=true` exposes the GroupStageWinnerCard on the dashboard
    AND lets the GROUP_STAGE_FINAL broadcast template surface real
    winner data when sent. `released=false` re-hides both surfaces —
    use this to retract if the standings change post-flip due to a
    late scoring correction.

    Single audit event per change. Idempotent — flipping to the same
    value twice records nothing on the second call.
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found",
        )

    previous = competition.group_stage_winner_released
    competition.group_stage_winner_released = request.released
    competition.updated_at = utc_now()
    if previous != request.released:
        record_audit_event(
            session,
            event_type="competition.group_stage_winner_released_toggled",
            actor_user_id=admin.id,
            actor_role=ActorRole.ADMIN,
            subject_type="competition",
            subject_id=competition.id,
            metadata={"from": previous, "to": request.released},
        )
    await session.commit()

    return {"status": "ok", "group_stage_winner_released": request.released}


# ---------------------------------------------------------------------------
# Knockout scoring gate (v2.181.1)
# ---------------------------------------------------------------------------
class KnockoutScoringRequest(BaseModel):
    """Toggle the knockout-scoring gate (suppresses all advancement payouts)."""

    enabled: bool


@router.post("/competition/knockout-scoring")
async def set_knockout_scoring_enabled(
    request: KnockoutScoringRequest,
    session: DbSession,
    admin: AdminUser,
) -> dict:
    """Flip the knockout-scoring gate (v2.181.1).

    `enabled=true` instructs the scoring engine to start paying out
    advancement points — group_advance / group_position bracket credits
    AND knockout-stage credits (R32 → winner). `enabled=false` holds
    every advancement payout at zero until flipped.

    Flipping the flag changes every entry's score, so we hard-invalidate
    the leaderboard cache on the same commit. Auditable, idempotent.
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found",
        )

    previous = competition.knockout_scoring_enabled
    competition.knockout_scoring_enabled = request.enabled
    competition.updated_at = utc_now()
    if previous != request.enabled:
        record_audit_event(
            session,
            event_type="competition.knockout_scoring_toggled",
            actor_user_id=admin.id,
            actor_role=ActorRole.ADMIN,
            subject_type="competition",
            subject_id=competition.id,
            metadata={"from": previous, "to": request.enabled},
        )
    await session.commit()

    if previous != request.enabled:
        # Every entry's advancement payouts have just turned on/off,
        # so the leaderboard MUST rebuild on next read. invalidate_cache
        # is a synchronous in-memory drop — no await.
        invalidate_cache()

    return {"status": "ok", "knockout_scoring_enabled": request.enabled}


# ---------------------------------------------------------------------------
# Announcement hero visibility toggle (v2.191.0)
# ---------------------------------------------------------------------------
class AnnouncementHeroRequest(BaseModel):
    """Toggle the dashboard announcement hero on/off."""

    enabled: bool


@router.post("/competition/announcement-hero")
async def set_announcement_hero_enabled(
    request: AnnouncementHeroRequest,
    session: DbSession,
    admin: AdminUser,
) -> dict:
    """Show or hide the dashboard AnnouncementHero for all signed-in users.

    When `enabled=false` the hero is completely hidden — even the fallback
    welcome card won't show. Auditable, idempotent.
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found",
        )

    previous = competition.announcement_hero_enabled
    competition.announcement_hero_enabled = request.enabled
    competition.updated_at = utc_now()
    if previous != request.enabled:
        record_audit_event(
            session,
            event_type="competition.announcement_hero_toggled",
            actor_user_id=admin.id,
            actor_role=ActorRole.ADMIN,
            subject_type="competition",
            subject_id=competition.id,
            metadata={"from": previous, "to": request.enabled},
        )
    await session.commit()

    return {"status": "ok", "announcement_hero_enabled": request.enabled}


# ---------------------------------------------------------------------------
# Standings drift verification (v2.182.0)
# ---------------------------------------------------------------------------
class DriftCheckResult(BaseModel):
    """Outcome of a manually-triggered standings verification."""

    source_used: str | None
    disagreement_count: int
    created_event_id: uuid.UUID | None


class DriftEventOut(BaseModel):
    """One drift event surfaced to the admin UI."""

    id: uuid.UUID
    competition_id: uuid.UUID
    detected_at: datetime
    trusted_source: str
    status: str
    disagreement_count: int
    groups_disagreeing: dict
    resolved_at: datetime | None
    resolution_note: str | None


class DriftDismissRequest(BaseModel):
    """Admin closes a drift event with a status + optional note."""

    status: Literal[
        "DISMISSED_OURS_CORRECT",
        "DISMISSED_TRANSIENT",
        "RESOLVED_VIA_SCORE_EDIT",
    ]
    note: str | None = None


@router.post("/standings-drift/check", response_model=DriftCheckResult)
async def trigger_standings_drift_check(
    session: DbSession,
    admin: AdminUser,
) -> DriftCheckResult:
    """Manually trigger a standings verification (v2.182.0).

    Runs the full source chain (Football-Data primary; ESPN + Wikipedia
    join in 2.182.1). If disagreements are found, opens a new
    `StandingsDriftEvent` row and returns its id. If trusted sources are
    all unavailable, returns source_used=None and disagreement_count=0.
    """
    source, disagreements = await run_verification(session)
    if source is None:
        return DriftCheckResult(
            source_used=None, disagreement_count=0, created_event_id=None
        )

    if not disagreements:
        return DriftCheckResult(
            source_used=source.value, disagreement_count=0, created_event_id=None
        )

    # Open a new drift event for admin review.
    competition = await get_active_competition(session)
    event = StandingsDriftEvent(
        competition_id=competition.id,
        trusted_source=source,
        groups_disagreeing={"groups": disagreements},
        status=DriftEventStatus.OPEN,
    )
    session.add(event)
    record_audit_event(
        session,
        event_type="standings_drift.detected",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="competition",
        subject_id=competition.id,
        metadata={
            "source": source.value,
            "disagreement_count": len(disagreements),
            "groups": sorted(disagreements.keys()),
        },
    )
    await session.commit()
    await session.refresh(event)

    return DriftCheckResult(
        source_used=source.value,
        disagreement_count=len(disagreements),
        created_event_id=event.id,
    )


@router.get("/standings-drift/open", response_model=list[DriftEventOut])
async def list_open_drift_events(
    session: DbSession,
    _admin: AdminUser,
) -> list[DriftEventOut]:
    """List currently-open drift events for the active competition."""
    result = await session.execute(
        select(StandingsDriftEvent)
        .where(StandingsDriftEvent.status == DriftEventStatus.OPEN)
        .order_by(StandingsDriftEvent.detected_at.desc())
    )
    rows = result.scalars().all()
    return [
        DriftEventOut(
            id=r.id,
            competition_id=r.competition_id,
            detected_at=r.detected_at,
            trusted_source=r.trusted_source.value,
            status=r.status.value,
            disagreement_count=len(
                (r.groups_disagreeing or {}).get("groups", {})
            ),
            groups_disagreeing=r.groups_disagreeing or {},
            resolved_at=r.resolved_at,
            resolution_note=r.resolution_note,
        )
        for r in rows
    ]


@router.post("/standings-drift/{event_id}/dismiss")
async def dismiss_drift_event(
    event_id: uuid.UUID,
    request: DriftDismissRequest,
    session: DbSession,
    admin: AdminUser,
) -> dict:
    """Close a drift event with a status + optional note."""
    result = await session.execute(
        select(StandingsDriftEvent).where(StandingsDriftEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Drift event not found"
        )
    if event.status != DriftEventStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Event already in status {event.status.value}",
        )

    event.status = DriftEventStatus(request.status)
    event.resolved_at = utc_now()
    event.resolved_by_user_id = admin.id
    event.resolution_note = request.note
    event.updated_at = utc_now()

    record_audit_event(
        session,
        event_type="standings_drift.dismissed",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="standings_drift_event",
        subject_id=event.id,
        metadata={"resolution": request.status, "note": request.note},
    )
    await session.commit()
    return {"status": "ok", "event_id": str(event.id), "resolution": request.status}


# ---------------------------------------------------------------------------
# Close the pool (v2.166.0) — disable accounts with zero counting
# submissions after the deadline. Preview first, then one confirm click.
# ---------------------------------------------------------------------------
class PoolClosePreviewOut(BaseModel):
    deadline_passed: bool
    accounts_to_disable: int
    submitters_kept: int
    admins_exempt: int
    already_inactive: int
    drafts_withdrawn: int
    eligible_submitted_entries: int


class PoolCloseResultOut(BaseModel):
    disabled_count: int


async def _active_competition_or_404(session: DbSession) -> Competition:
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found",
        )
    return competition


@router.get("/close-pool/preview", response_model=PoolClosePreviewOut)
async def get_pool_close_preview(
    session: DbSession, _admin: AdminUser
) -> PoolClosePreviewOut:
    """Dry-run counts for the Close-the-pool card. No writes."""
    competition = await _active_competition_or_404(session)
    preview = await preview_pool_close(session, competition)
    return PoolClosePreviewOut(**preview.__dict__)


@router.post("/close-pool", response_model=PoolCloseResultOut)
async def run_pool_close(
    session: DbSession, admin: AdminUser
) -> PoolCloseResultOut:
    """Disable every active non-admin account without a counting
    submission. Admin-exempt by construction; refuses pre-deadline;
    idempotent; audited with the affected user ids."""
    competition = await _active_competition_or_404(session)
    try:
        result = await close_pool(session, competition=competition, admin=admin)
    except PoolCloseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    return PoolCloseResultOut(disabled_count=result.disabled_count)


class SyncScoresResponse(BaseModel):
    """Response from score sync operation."""

    synced: int
    updated: int
    # Rows left untouched because an admin verified the score via the
    # /admin/sync editor (manual scores are locked against the API).
    skipped_verified: int = 0
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
        skipped_verified=result.skipped_verified,
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


# ============================================================================
# v2.156.0 — redesigned admin endpoints
# ============================================================================
# Route ORDER matters here: more-specific static-segment routes
# (/users/list, /users/inactive) MUST be declared BEFORE the path-param
# route (/users/{user_id}) so a request to /admin/users/list is matched
# by the list endpoint and not interpreted as user_id="list".
# ============================================================================


# ── Audit feed ──────────────────────────────────────────────────────────────


@router.get("/audit", response_model=AuditEventPage)
async def get_audit_feed(
    session: DbSession,
    _admin: AdminUser,
    event_type: str | None = None,
    namespace: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    subject_type: str | None = None,
    search: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AuditEventPage:
    """Paginated global audit feed for /admin/audit.

    All filters are optional and AND together. ``namespace`` is the
    prefix used by the page's namespace chips (``"auth"`` matches every
    ``auth.*`` event). ``search`` does a case-insensitive substring
    match on the joined actor email + actor name + event type.
    """
    rows, total = await query_audit_events(
        session,
        event_type=event_type,
        namespace=namespace,
        actor_user_id=actor_user_id,
        subject_id=subject_id,
        subject_type=subject_type,
        search=search,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return AuditEventPage(rows=rows, total=total)


# ── Users list (cohort-aware) ───────────────────────────────────────────────


@router.get("/users/list", response_model=UserAdminPage)
async def list_users_v2(
    session: DbSession,
    _admin: AdminUser,
    cohort: UserCohort = UserCohort.ACTIVE,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> UserAdminPage:
    """v2.156.0 paginated users list with derived ``cohort`` / ``last_login_at``
    / ``last_activity_at``.

    Defaults to the ``active`` cohort (joined + admin-not-deactivated) —
    same default as the redesigned ``/admin/users`` page.

    The legacy ``GET /admin/users`` endpoint (non-paginated, flat
    ``list[UserAdminView]``) is left in place for backward compat with
    the existing admin monolith during the rollout. Once the trim of
    ``/admin/+page.svelte`` lands (Task #13), the legacy endpoint can
    be deprecated.
    """
    return await list_users_with_cohort(
        session,
        cohort=cohort,
        search=search,
        limit=limit,
        offset=offset,
    )


# ── Inactive-users CSV export (re-engagement mailshot) ──────────────────────


@router.get("/users/inactive")
async def export_inactive_emails(
    session: DbSession,
    _admin: AdminUser,
    cohort: Literal["signed_up_only", "verified_only", "both"] = "both",
) -> Response:
    """CSV download of the inactive cohort(s) for re-engagement mailshots.

    Returns text/csv with columns:
    ``email,cohort,created_at,last_magic_link_sent_at,last_magic_link_verified_at``.

    The two cohorts are intentionally distinguishable in the CSV so the
    admin can write different copy for each (cohort 1 = "you started but
    didn't click your link"; cohort 2 = "you logged in but didn't finish
    setup"). Pass ``?cohort=signed_up_only`` or ``?cohort=verified_only``
    to restrict the export.
    """
    rows = await list_inactive_emails(session, cohort=cohort)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "email",
            "cohort",
            "created_at",
            "last_magic_link_sent_at",
            "last_magic_link_verified_at",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.email,
                r.cohort.value,
                r.created_at.isoformat() if r.created_at else "",
                r.last_magic_link_sent_at.isoformat()
                if r.last_magic_link_sent_at
                else "",
                r.last_magic_link_verified_at.isoformat()
                if r.last_magic_link_verified_at
                else "",
            ]
        )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="inactive-{cohort}.csv"'
        },
    )


# ── User detail (drill-down) ────────────────────────────────────────────────


@router.get("/users/{user_id}", response_model=UserDetailRead)
async def get_user_detail(
    user_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> UserDetailRead:
    """Full profile + summary metrics + recent activity for
    /admin/users/[id].

    Entries are NOT included here — the frontend fetches them via the
    existing ``admin_list_entries`` call filtered by user_id. Keeping
    the responsibilities separate means this endpoint stays cheap on
    user-detail page load even for users with many entries.
    """
    # Existence check first so 404s short-circuit before the heavier
    # cohort-row computation.
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Reuse the cohort service to derive the row — guarantees the list
    # view and detail view agree on cohort / counts / last-activity
    # for the same user. Search by exact email yields exactly one row.
    page = await list_users_with_cohort(
        session,
        cohort=UserCohort.ALL,
        search=user.email,
        limit=1,
        offset=0,
    )
    if not page.rows:
        # Defensive — should be impossible since the user exists, but
        # cohort filter could in theory exclude (e.g. case-sensitivity).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    row = page.rows[0]

    # Recent activity = the 100 most recent audit events for this user.
    activity, _total = await query_audit_events(
        session, actor_user_id=user_id, limit=100, offset=0
    )

    return UserDetailRead(
        id=row.id,
        email=row.email,
        name=row.name,
        auth_provider=row.auth_provider,
        is_admin=row.is_admin,
        is_active=row.is_active,
        paid=row.paid,
        paid_to=row.paid_to,
        employer=row.employer,
        company_contact=row.company_contact,
        cohort=row.cohort,
        entries_count=row.entries_count,
        submitted_entries_count=row.submitted_entries_count,
        draft_entries_count=row.draft_entries_count,
        prediction_count=row.prediction_count,
        last_login_at=row.last_login_at,
        last_activity_at=row.last_activity_at,
        created_at=row.created_at,
        recent_activity=activity,
    )


# ── User engagement (PostHog mini-card) ─────────────────────────────────────


@router.get(
    "/users/{user_id}/engagement", response_model=EngagementSummary | None
)
async def get_user_engagement(
    user_id: uuid.UUID,
    _admin: AdminUser,
    days: int = 30,
) -> EngagementSummary | None:
    """PostHog read-side engagement summary — last seen, last page,
    session count, avg session duration, 14-day sparkline.

    Returns ``null`` (not an error) when PostHog is disabled in this
    environment (e.g. the env vars ``POSTHOG_PERSONAL_API_KEY`` /
    ``POSTHOG_PROJECT_ID`` are unset locally). The frontend renders
    "—" placeholders on the Engagement card in that case so admins
    aren't shown a stack trace for a missing optional integration.

    Designed as the first consumer of ``services.posthog_read`` —
    a future ``GET /api/me/engagement`` for personalized landing-page
    copy will reuse the same service function unchanged.
    """
    return await posthog_read.get_engagement_summary(user_id, days=days)


# ── Admin entry predictions (slide-over Group/Knockout/Bonus tabs) ──────────


@router.get(
    "/entries/{entry_id}/predictions",
    response_model=AdminEntryPredictions,
)
async def get_admin_entry_predictions(
    entry_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> AdminEntryPredictions:
    """Read-only view of one entry's predictions for the admin slide-over.

    Single round-trip — returns match predictions (Phase 1), the
    aggregated bracket, and the user's bonus answers. Admin-only;
    bypasses the blind-pool visibility check via the same
    ``get_entry_for_view`` precedent as the existing admin entry-detail
    loader. No deadline gate per v2.157.0 decision — admins have full
    read access at all times.

    Audit: deliberately NOT logged. Reads stay invisible by convention
    (the audit log is mutation-focused).
    """
    # Local imports avoid circular references between admin.py and
    # entry_predictions.py (the latter imports the bracket aggregator we
    # reuse here).
    from app.api.entry_predictions import _organize_bracket, _to_match_read
    from app.models.prediction import PredictionPhase
    from app.services import entries as entries_service
    from app.services import predictions as predictions_service

    # Load entry through the visibility helper. AdminUser short-circuits
    # the blind-pool gate.
    entry = await entries_service.get_entry_for_view(
        session, entry_id=entry_id, viewer=_admin
    )

    # Phase 1 match predictions (with fixture join for team names + kickoff).
    match_rows = await predictions_service.get_match_predictions(
        session, entry=entry
    )
    match_predictions = [_to_match_read(p, f) for p, f in match_rows]

    # Phase 1 bracket — aggregated into the shape KnockoutBracket expects.
    team_rows = await predictions_service.get_bracket_predictions(
        session, entry=entry, phase=PredictionPhase.PHASE_1
    )
    bracket = _organize_bracket(team_rows) if team_rows else None

    # Bonus answers — join question_id to the YAML title.
    bonus_rows = await predictions_service.get_bonus_predictions(
        session, entry=entry
    )
    title_by_id = {q.id: q.label for q in get_bonus_questions()}
    bonus_answers = [
        AdminBonusAnswer(
            question_id=r.question_id,
            question_title=title_by_id.get(r.question_id, r.question_id),
            answer=r.answer or None,
        )
        for r in bonus_rows
    ]
    # If the user answered NO bonus questions, still return the 4 question
    # placeholders so the slide-over UI is consistent. Each placeholder
    # has answer=None which the frontend renders as an em-dash.
    answered_ids = {r.question_id for r in bonus_rows}
    for q in get_bonus_questions():
        if q.id not in answered_ids:
            bonus_answers.append(
                AdminBonusAnswer(
                    question_id=q.id, question_title=q.label, answer=None
                )
            )

    return AdminEntryPredictions(
        match_predictions=match_predictions,
        bracket=bracket,
        bonus_answers=bonus_answers,
    )


# ============================================================================
# v2.176.0 — Site Pulse endpoint
# ============================================================================
# At-a-glance engagement panel for the /admin Overview tab. Reads
# PostHog (silent-fail) + audit_events (DB). Admin-only.


@router.get("/pulse", response_model=SitePulse)
async def get_pulse(
    session: DbSession,
    _admin: AdminUser,
) -> SitePulse:
    """Site Pulse — 4 widgets in one shot.

    PostHog-backed widgets (DAU sparkline, Top pages, Top events)
    silent-fail to empty lists when PostHog is unreachable. The
    audit-backed widget (Recent logins) always loads.

    No caching at this layer — the PostHog helpers cache internally
    at 5-minute TTL, so repeated admin reloads are cheap.
    """
    return await pulse_service.get_site_pulse(session)


# ============================================================================
# v2.160.0 — Broadcast email endpoints
# ============================================================================
# Three endpoints: count audience, send a test to a single recipient, send
# the real broadcast. Test sends do NOT emit audit events (they're scratch
# work — would pollute the feed). Real sends emit one ADMIN_BROADCAST_SENT
# event per broadcast (NOT per recipient) summarising segment + counts.
# ============================================================================


def _format_deadline(dt: datetime | None) -> str | None:
    """Format a deadline as ``11 Jun 2026, 17:00 UTC`` (no leading zero on day).

    Returns None if dt is None so the email template can fall back to
    the generic ``before the deadline`` phrase.
    """
    if dt is None:
        return None
    return f"{dt.day} {dt.strftime('%b %Y, %H:%M UTC')}"


async def _active_competition(session) -> Competition | None:
    """Most-recently-created competition. None if there are zero competitions."""
    return (
        await session.execute(
            select(Competition).order_by(Competition.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()


def _deep_link_for_segment(frontend_url: str, segment: BroadcastSegment) -> str:
    """CTA destination for each broadcast segment.

    Pre-deadline segments (SUBMITTERS / NO_ENTRY / DRAFT_HOLDERS) go to
    /entries — they need to land on the wizard to add / submit picks.
    POOL_GHOST and LAPSING are post-deadline re-engagement — they go to
    /results so the recipient lands directly on the scoreboard. v2.176.0.
    GROUP_R1_RECAP (v2.178.0) lands on /leaderboard with UTM tagging so
    PostHog $pageview can attribute the click-through.

    GROUP_R2_RECAP (v2.180.0) intentionally OMITS the UTM tagging.
    R1's recap was flagged by Gmail's promotional filter and bumped to
    the spam bin for many recipients; the UTM tag combined with
    "winner"/"prize"/"announced" phrasing was the most likely lexical
    contributor (UTM-parameters are themselves a campaign signal).
    Trade-off: PostHog can no longer attribute R2 click-throughs.
    Deliverability beats analytics here.
    """
    base = frontend_url.rstrip("/")
    if segment == BroadcastSegment.GROUP_R1_RECAP:
        return (
            f"{base}/leaderboard"
            "?utm_source=email&utm_campaign=group_r1_recap"
        )
    if segment == BroadcastSegment.GROUP_R2_RECAP:
        return f"{base}/leaderboard"
    if segment == BroadcastSegment.GROUP_STAGE_FINAL:
        # v2.181.0 — same UTM-free /leaderboard destination as R2.
        # The recipient lands on the dashboard's winner card via the
        # navbar; the CTA itself lands them on the full standings.
        return f"{base}/leaderboard"
    if segment in (BroadcastSegment.POOL_GHOST, BroadcastSegment.LAPSING):
        return f"{base}/results"
    return f"{base}/entries"


@router.get("/broadcasts/audience", response_model=BroadcastAudienceCounts)
async def get_broadcast_audience(
    session: DbSession,
    _admin: AdminUser,
) -> BroadcastAudienceCounts:
    """Live audience counts for the three broadcast segments.

    Powers the count badges on the broadcast card so the admin can see
    at a glance how many users each nudge would reach before clicking
    anything.
    """
    counts = await count_all_audiences(session)
    return BroadcastAudienceCounts(
        submitters=counts[BroadcastSegment.SUBMITTERS],
        no_entry=counts[BroadcastSegment.NO_ENTRY],
        draft_holders=counts[BroadcastSegment.DRAFT_HOLDERS],
        pool_ghost=counts[BroadcastSegment.POOL_GHOST],
        lapsing=counts[BroadcastSegment.LAPSING],
        group_r1_recap=counts[BroadcastSegment.GROUP_R1_RECAP],
        group_r2_recap=counts[BroadcastSegment.GROUP_R2_RECAP],
        group_stage_final=counts[BroadcastSegment.GROUP_STAGE_FINAL],
    )


@router.post("/broadcasts/test", response_model=BroadcastTestResult)
async def send_broadcast_test(
    payload: BroadcastTestRequest,
    session: DbSession,
    admin: AdminUser,
) -> BroadcastTestResult:
    """Send a single-recipient test of the broadcast template.

    Defaults to the calling admin's own email; admins can override
    ``to_email`` to test cross-client rendering at an alternate
    address (e.g. personal Gmail / Outlook). No audit event — test
    sends are scratch work and would pollute the feed.

    Always returns 200 with ``sent`` indicating success/failure so the
    frontend can render an appropriate toast without try/catch around
    the fetch call.
    """
    to_email = payload.to_email or admin.email
    settings = get_settings()
    deep_link_url = _deep_link_for_segment(settings.frontend_url, payload.segment)

    comp = await _active_competition(session)
    deadline_dt = comp.phase1_deadline if comp else None
    deadline_display = _format_deadline(deadline_dt)

    # R2 recap + Group Stage Final pull live data into their placeholders.
    # The test send wants the same interpolation as the real broadcast —
    # otherwise the admin would see literal {{TOP_1}} or {{WINNER_NAME}}
    # in their test inbox and assume the broadcast is broken (this is
    # what happened in v2.180.0, fixed in v2.180.1 for R2; v2.181.0
    # extends the same pattern to GROUP_STAGE_FINAL).
    tokens: dict[str, str] | None = None
    if payload.segment == BroadcastSegment.GROUP_R2_RECAP:
        tokens = await _compute_r2_highlights(session)
    elif payload.segment == BroadcastSegment.GROUP_STAGE_FINAL:
        tokens = await _compute_group_stage_winner_email_tokens(session)

    try:
        await send_broadcast_email(
            to_email=to_email,
            player_name=admin.name or admin.email.split("@")[0],
            segment=payload.segment,
            deep_link_url=deep_link_url,
            deadline_display=deadline_display,
            deadline_dt=deadline_dt,
            tokens=tokens,
        )
        return BroadcastTestResult(sent=True, to_email=to_email, error=None)
    except Exception as exc:  # noqa: BLE001 — caller wants the error string
        return BroadcastTestResult(
            sent=False, to_email=to_email, error=str(exc)[:200]
        )


@router.post("/broadcasts", response_model=BroadcastSendResult)
async def send_broadcast(
    payload: BroadcastSendRequest,
    session: DbSession,
    admin: AdminUser,
) -> BroadcastSendResult:
    """Real broadcast send (or dry-run preview).

    Flow:
    * ``dry_run=True`` → query the audience, return count + first 5 emails.
      No Resend calls.
    * ``dry_run=False`` → iterate the audience, call Resend per row paced
      at 50ms (well under the free-tier 10/s limit). Records ONE audit
      event summarising the broadcast (segment + counts), NOT per-recipient.

    Errors during individual sends are caught + counted as ``failed`` —
    the broadcast continues so a single transient Resend hiccup doesn't
    leave 50 users un-nudged. The first 3 failure emails are surfaced
    to the admin in ``sample_emails`` for spot-checking.
    """
    audience = await query_audience(session, payload.segment)
    audience_count = len(audience)

    if payload.dry_run:
        return BroadcastSendResult(
            dry_run=True,
            segment=payload.segment,
            audience_count=audience_count,
            sent=0,
            failed=0,
            sample_emails=[row.email for row in audience[:5]],
        )

    # Real send — iterate with pacing.
    settings = get_settings()
    deep_link_url = _deep_link_for_segment(settings.frontend_url, payload.segment)

    comp = await _active_competition(session)
    deadline_dt = comp.phase1_deadline if comp else None
    deadline_display = _format_deadline(deadline_dt)

    # R2 recap + Group Stage Final pre-fetch their placeholder values
    # ONCE here so the per-recipient loop below doesn't re-run the
    # underlying queries N times. The token dict is then passed through
    # every send_broadcast_email call as-is.
    tokens: dict[str, str] | None = None
    if payload.segment == BroadcastSegment.GROUP_R2_RECAP:
        tokens = await _compute_r2_highlights(session)
    elif payload.segment == BroadcastSegment.GROUP_STAGE_FINAL:
        tokens = await _compute_group_stage_winner_email_tokens(session)

    sent = 0
    failed = 0
    failure_samples: list[str] = []

    for idx, row in enumerate(audience):
        try:
            await send_broadcast_email(
                to_email=row.email,
                player_name=row.name or row.email.split("@")[0],
                segment=payload.segment,
                deep_link_url=deep_link_url,
                deadline_display=deadline_display,
                deadline_dt=deadline_dt,
                tokens=tokens,
            )
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
            if len(failure_samples) < 3:
                failure_samples.append(row.email)
        # Pace between sends — last iteration doesn't need to sleep.
        if idx < len(audience) - 1:
            await asyncio.sleep(0.05)

    # Single audit event per broadcast (NOT per recipient). The
    # event_metadata carries enough state to reconstruct what was sent.
    record_audit_event(
        session,
        event_type="admin.broadcast_sent",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="broadcast",
        subject_id=None,
        metadata={
            "segment": payload.segment.value,
            "audience_count": audience_count,
            "sent": sent,
            "failed": failed,
        },
    )
    await session.commit()

    return BroadcastSendResult(
        dry_run=False,
        segment=payload.segment,
        audience_count=audience_count,
        sent=sent,
        failed=failed,
        sample_emails=failure_samples,
    )


# ── Entry completeness check (E.1, report-only) ─────────────────────────────


@router.get(
    "/entries/completeness-check",
    response_model=list[EntryCompletenessResult],
)
async def admin_entries_completeness_check(
    session: DbSession,
    _admin: AdminUser,
    detail: bool = False,
) -> list[EntryCompletenessResult]:
    """Report-only check of pick fullness for every eligible entry.

    Returns ALL eligible entries; the frontend filters to incompletes for
    display. Pass ``?detail=true`` for the per-fixture / per-stage
    drill-down. Admin-only. No enforcement — the admin chases gaps out of
    band using the CSV variant below.
    """
    return await check_all_eligible_entries(session, detail=detail)


@router.get("/entries/completeness-check.csv")
async def admin_entries_completeness_check_csv(
    session: DbSession,
    _admin: AdminUser,
) -> Response:
    """Same check as the JSON endpoint, formatted as CSV. Only includes
    INCOMPLETE entries — one row each, ready for a chase-up mailshot.
    Admin-only."""
    rows = await check_all_eligible_entries(session, detail=False)
    incompletes = [r for r in rows if not r.is_complete]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "entry_id",
            "entry_name",
            "user_name",
            "user_email",
            "missing_match_picks",
            "missing_bracket_picks",
            "missing_bonus_picks",
            "total_missing",
        ]
    )
    for r in incompletes:
        writer.writerow(
            [
                str(r.entry_id),
                r.entry_name,
                r.user_name,
                r.user_email,
                r.missing_match_picks,
                r.missing_bracket_picks,
                r.missing_bonus_picks,
                r.missing_match_picks
                + r.missing_bracket_picks
                + r.missing_bonus_picks,
            ]
        )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="entry-completeness.csv"'
        },
    )
