"""Competition API routes."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from app.dependencies import CurrentUser, DbSession
from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.models.user import User
from app.services.entries import count_eligible_submitted_entries
from app.services.locking import get_current_phase, is_phase2_bracket_locked
from app.services.scoring import get_scoring_config


router = APIRouter()


class CompetitionInfo(BaseModel):
    """Public competition info for the rules / landing pages."""

    name: str
    entry_fee: float
    is_phase2_active: bool
    phase1_deadline: datetime | None
    phase2_bracket_deadline: datetime | None
    total_players: int
    paid_players: int
    # Scoring denominator — what rarity divides by, what the leaderboard
    # ranks. Eligible-submitted entries (not users): one user can hold up
    # to 5 entries, so this is typically larger than total_players. Same
    # predicate the scoring engine uses (eligible_entry_ids_select).
    eligible_entries: int


@router.get("/info", response_model=CompetitionInfo)
async def get_competition_info(session: DbSession) -> CompetitionInfo:
    """Public competition metadata — no auth required so the /rules page
    works for prospective joiners. Returns tournament name, entry fee,
    deadlines, current phase, and player counts."""
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if not competition:
        return CompetitionInfo(
            name="World Cup 2026",
            entry_fee=0.0,
            is_phase2_active=False,
            phase1_deadline=None,
            phase2_bracket_deadline=None,
            total_players=0,
            paid_players=0,
            eligible_entries=0,
        )

    total = await session.scalar(
        select(func.count(User.id)).where(User.is_active == True)  # noqa: E712
    )
    paid = await session.scalar(
        select(func.count(User.id))
        .where(User.is_active == True)  # noqa: E712
        .where(User.paid == True)  # noqa: E712
    )
    eligible_entries = await count_eligible_submitted_entries(
        session, competition=competition
    )

    return CompetitionInfo(
        name=competition.name,
        entry_fee=float(competition.entry_fee),
        is_phase2_active=competition.is_phase2_active,
        phase1_deadline=competition.phase1_deadline,
        phase2_bracket_deadline=competition.phase2_bracket_deadline,
        total_players=total or 0,
        paid_players=paid or 0,
        eligible_entries=int(eligible_entries),
    )


class PhaseStatus(BaseModel):
    """Current phase status for frontend."""

    current_phase: str  # 'phase_1' or 'phase_2'
    # Phase 1
    phase1_deadline: datetime | None
    phase1_locked: bool
    # Phase 2
    is_phase2_active: bool
    phase2_bracket_deadline: datetime | None
    phase2_bracket_locked: bool
    # Post-deadline release switch (v2.166.0) — admin-controlled; the
    # V4 pages open to the pool only when this is true.
    post_deadline_live: bool = False
    # Group Stage Winner release switch (v2.181.0) — admin-controlled;
    # gates the GroupStageWinnerCard on the dashboard AND the
    # GROUP_STAGE_FINAL broadcast email's data payload.
    group_stage_winner_released: bool = False
    # Knockout-scoring gate (v2.181.1) — admin-controlled; when false
    # the scoring engine suppresses every advancement payout. Surfaced
    # here so the admin UI can render the toggle's current state.
    knockout_scoring_enabled: bool = False


@router.get("/phase-status", response_model=PhaseStatus)
async def get_phase_status(
    session: DbSession,
    _current_user: CurrentUser,
) -> PhaseStatus:
    """Get current phase status for the active competition.

    This endpoint allows the frontend to determine:
    - Phase 1 deadline and lock status
    - Whether to show the Phase 2 tab
    - Whether the Phase 2 bracket is locked
    - The Phase 2 bracket deadline
    """
    # Get active competition
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    competition = result.scalar_one_or_none()

    current_phase = await get_current_phase(session)
    bracket_locked = await is_phase2_bracket_locked(session)

    # Check if phase 1 is locked (past deadline). aware_utc at the
    # compare site — aiosqlite strips tzinfo on read (datetime rule).
    phase1_locked = False
    if competition and competition.phase1_deadline:
        phase1_locked = utc_now() >= aware_utc(competition.phase1_deadline)

    return PhaseStatus(
        current_phase=current_phase.value,
        phase1_deadline=competition.phase1_deadline if competition else None,
        phase1_locked=phase1_locked,
        is_phase2_active=competition.is_phase2_active if competition else False,
        phase2_bracket_deadline=competition.phase2_bracket_deadline if competition else None,
        phase2_bracket_locked=bracket_locked,
        post_deadline_live=competition.post_deadline_live if competition else False,
        group_stage_winner_released=(
            competition.group_stage_winner_released if competition else False
        ),
        knockout_scoring_enabled=(
            competition.knockout_scoring_enabled if competition else False
        ),
    )


class ScoringConfigResponse(BaseModel):
    """Scoring configuration as the frontend needs it to render per-match
    breakdowns (Outcome / Exact / Rarity pills + Total).

    The rarity formula uses per-fixture predictor counts, not a global
    player count — the frontend has those via `/predictions/agreements`
    (FixtureAgreement.total). For mode='logarithmic':

        R = min(rarity_cap, round(alpha * log2(1 / (2f))))

    where f = agrees_outcome / total and alpha = 10/log2(15) ≈ 2.5596.
    """

    mode: str  # 'fixed' | 'hybrid' (legacy) | 'logarithmic'
    outcome_points: int
    exact_points: int
    rarity_cap: int


@router.get("/scoring-config", response_model=ScoringConfigResponse)
async def get_scoring_config_endpoint(
    _current_user: CurrentUser,
) -> ScoringConfigResponse:
    """Return scoring config so the Results & Fixtures page can project
    per-match rarity bonuses client-side using the same formula the backend
    will eventually score with. Per-fixture predictor counts come from
    /predictions/agreements."""
    config = get_scoring_config()
    match_cfg = config.get("match", {})
    return ScoringConfigResponse(
        mode=config.get("mode", "logarithmic"),
        outcome_points=match_cfg.get("correct_outcome", 5),
        exact_points=match_cfg.get("exact_score", 10),
        rarity_cap=match_cfg.get("rarity_cap", match_cfg.get("hybrid_cap", 10)),
    )
