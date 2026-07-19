"""Leaderboard API routes — entry-scoped.

Each row of the leaderboard is one `PredictionEntry`. Endpoints that
previously took a `user_id` now take an `entry_id`. The `/snapshots/me`
convenience route picks the requesting user's first eligible entry by
default; pass `?entry_id=<uuid>` to target a specific one.
"""

import logging
import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.dependencies import AdminUser, CurrentUser, DbSession, OptionalUser
from app.models.entry import PredictionEntry
from app.models._datetime import utc_now
from app.schemas.leaderboard import LeaderboardResponse, PointBreakdown
from app.services.entries import (
    EntryAccessDeniedError,
    EntryNotFoundError,
    get_entry_for_view,
)
from app.services.leaderboard import calculate_leaderboard, invalidate_cache
from app.services.live_projection import apply_live_projection
from app.services.locking import is_phase1_locked
from app.services.scoring import (
    SCORING_STRATEGIES,
    calculate_entry_points,
    get_scoring_config,
    resolve_default_entry_id,
)
from app.services.snapshots import (
    get_all_snapshots,
    get_entry_trajectory,
    get_steepest_climbers,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class RankSnapshotPoint(BaseModel):
    """One day's rank + points for an entry."""

    position: int
    total_points: int
    captured_date: date


class RankTrajectoryResponse(BaseModel):
    """An entry's rank trajectory over the last N days.

    `points` is oldest → newest. The final entry is the entry's CURRENT
    live rank (not the last DB snapshot) — the endpoint appends it so the
    chart's most recent dot is always current, even if today's daily
    snapshot is still pending.
    """

    entry_id: uuid.UUID
    points: list[RankSnapshotPoint]
    total_participants: int


class SteepestClimberEntry(BaseModel):
    """One row in the steepest-climbers list — one entry, not one user."""

    entry_id: uuid.UUID
    entry_name: str
    user_id: uuid.UUID
    user_name: str
    places: int
    current_position: int
    previous_position: int


class SteepestClimbersResponse(BaseModel):
    """Top-N entries by 7-day rank improvement."""

    days: int
    entries: list[SteepestClimberEntry]


class ScoringConfigResponse(BaseModel):
    """Response model for scoring configuration."""

    mode: str
    available_modes: list[str]
    match: dict[str, Any]
    advancement: dict[str, Any]
    phase_multipliers: dict[str, float]


@router.get("/scoring-rules", response_model=ScoringConfigResponse)
async def get_scoring_rules() -> ScoringConfigResponse:
    """Get the current scoring configuration.

    Returns the scoring rules in effect, including:
    - Current scoring mode (fixed, hybrid, or logarithmic)
    - Available scoring modes
    - Match prediction point values
    - Advancement prediction point values
    - Phase multipliers
    """
    config = get_scoring_config()
    return ScoringConfigResponse(
        mode=config.get("mode", "logarithmic"),
        available_modes=list(SCORING_STRATEGIES.keys()),
        match=config.get("match", {}),
        advancement=config.get("advancement", {}),
        phase_multipliers=config.get("phase_multipliers", {}),
    )


@router.get("/", response_model=LeaderboardResponse)
async def get_leaderboard(
    session: DbSession,
    user: OptionalUser,
    refresh: bool = Query(False, description="Force cache refresh"),
    phase: str | None = Query(None, description="Filter by phase: 'phase_1', 'phase_2', or null for overall"),
) -> LeaderboardResponse:
    """Get full leaderboard with standings — one row per eligible entry.

    Uses 30-second caching for performance. `refresh=true` forces a
    recalculation but is honoured only for admins — for everyone else it
    is ignored (the 30s TTL already keeps standings fresh, and an open
    refresh would let any client stampede the rebuild).
    Includes correct outcomes, exact scores, and position movement tracking.

    The `phase` parameter allows filtering:
    - `null` or omitted: Overall leaderboard (sum of all phases)
    - `phase_1`: Phase 1 points only
    - `phase_2`: Phase 2 points only

    Position rankings are recalculated based on the selected phase's points.

    **Visibility:** before Phase 1 deadline passes, the response only
    includes rows the requester owns (so users can't peek at others'
    progress while predictions are still open). `total_participants`
    stays unfiltered so the user sees the true field size. Admins always
    see everyone.
    """
    if phase is not None and phase not in ("phase_1", "phase_2"):
        phase = None

    force = bool(refresh and user is not None and user.is_admin)
    response = await calculate_leaderboard(session, force_refresh=force, phase=phase)

    # Live projection is a purely additive overlay (see live_projection.py's
    # module docstring) — a bug in it must not take down the banked board
    # for the whole pool. Fail open: log and keep serving the banked response.
    try:
        response = await apply_live_projection(session, response)
    except Exception as e:  # noqa: BLE001 — overlay is best-effort, don't fail the endpoint
        logger.warning("live projection overlay failed: %s", e)

    # Pre-lock blind-pool filter. Post-lock returns full standings.
    if user is None or not user.is_admin:
        locked = await is_phase1_locked(session)
        if not locked:
            if user is None:
                response.entries = []
            else:
                response.entries = [
                    e for e in response.entries if e.user_id == user.id
                ]

    return response


@router.post("/invalidate")
async def invalidate_leaderboard_cache(_admin: AdminUser) -> dict[str, str]:
    """Invalidate the leaderboard cache. Admin-only.

    Call this after scores are updated to force recalculation on next
    request. Internal score-update paths call the service function
    `invalidate_cache()` directly and don't go through this endpoint.
    """
    invalidate_cache()
    return {"status": "cache invalidated"}


@router.get("/breakdown/{entry_id}")
async def get_entry_breakdown(
    entry_id: uuid.UUID, session: DbSession, user: OptionalUser
) -> PointBreakdown:
    """Get detailed point breakdown for a single prediction entry.

    Visibility: owner / admin always; other viewers only after Phase 1
    deadline passes and the entry is eligible. Returns 403 otherwise.
    """
    try:
        await get_entry_for_view(session, entry_id=entry_id, viewer=user)
    except EntryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except EntryAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    return await calculate_entry_points(session, entry_id)


async def _build_trajectory(
    session: DbSession,
    entry_id: uuid.UUID,
    days: int,
) -> RankTrajectoryResponse:
    """Shared implementation for the two trajectory endpoints. Pulls the
    entry's snapshot history then appends the current live rank as the
    last point so the chart's tip is always up to date."""
    snaps = await get_entry_trajectory(session, entry_id, days=days)
    live = await calculate_leaderboard(session, phase=None)
    live_entry = next((e for e in live.entries if e.entry_id == entry_id), None)

    points = [
        RankSnapshotPoint(
            position=s.position,
            total_points=s.total_points,
            captured_date=s.captured_date,
        )
        for s in snaps
    ]
    if live_entry is not None:
        live_point = RankSnapshotPoint(
            position=live_entry.position,
            total_points=live_entry.total_points,
            captured_date=date.today(),
        )
        # If the last snapshot is from today, overwrite it so the chart
        # doesn't show stale data for the current day.
        if points and points[-1].captured_date == live_point.captured_date:
            points[-1] = live_point
        else:
            points.append(live_point)

    return RankTrajectoryResponse(
        entry_id=entry_id,
        points=points,
        total_participants=live.total_participants,
    )


class EntryTrajectory(BaseModel):
    """One entry's labelled rank path for the Race chart."""

    entry_id: uuid.UUID
    entry_name: str
    user_id: uuid.UUID
    user_name: str
    points: list[RankSnapshotPoint]


class AllTrajectoriesResponse(BaseModel):
    """Every eligible entry's rank trajectory (V4 Race chart)."""

    days: int
    entries: list[EntryTrajectory]
    total_participants: int


@router.get("/snapshots", response_model=AllTrajectoriesResponse)
async def get_all_trajectories(
    session: DbSession,
    user: CurrentUser,
    days: int = Query(30, ge=2, le=90),
) -> AllTrajectoriesResponse:
    """Rank trajectories for ALL eligible entries in one response — powers
    the V4 leaderboard's Race bump chart.

    One snapshot query for the whole field instead of N per-entry calls.
    Each entry's final point is its live current rank (same convention as
    the single-entry trajectory endpoints).

    **Visibility:** pre-deadline, non-admins receive only their own
    entries (blind pool); post-deadline everyone sees the full field.
    """
    live = await calculate_leaderboard(session, phase=None)
    rows = live.entries
    if not user.is_admin and not await is_phase1_locked(session):
        rows = [e for e in rows if e.user_id == user.id]

    snaps_by_entry = await get_all_snapshots(
        session, [e.entry_id for e in rows], days=days
    )

    today = date.today()
    entries: list[EntryTrajectory] = []
    for row in rows:
        points = [
            RankSnapshotPoint(
                position=s.position,
                total_points=s.total_points,
                captured_date=s.captured_date,
            )
            for s in snaps_by_entry.get(row.entry_id, [])
        ]
        live_point = RankSnapshotPoint(
            position=row.position,
            total_points=row.total_points,
            captured_date=today,
        )
        if points and points[-1].captured_date == today:
            points[-1] = live_point
        else:
            points.append(live_point)
        entries.append(
            EntryTrajectory(
                entry_id=row.entry_id,
                entry_name=row.entry_name,
                user_id=row.user_id,
                user_name=row.user_name,
                points=points,
            )
        )

    return AllTrajectoriesResponse(
        days=days,
        entries=entries,
        total_participants=live.total_participants,
    )


@router.get("/snapshots/me", response_model=RankTrajectoryResponse)
async def get_my_trajectory(
    session: DbSession,
    user: CurrentUser,
    days: int = Query(7, ge=2, le=90),
    entry_id: uuid.UUID | None = Query(
        None,
        description="Specific entry to read. If omitted, picks the user's most recently-updated eligible entry.",
    ),
) -> RankTrajectoryResponse:
    """Rank trajectory for the current user's selected entry, last `days`
    days (default 7).

    Used by the dashboard's rank-trajectory card. Returned points are
    oldest → newest; the final point is always the entry's live current
    rank, not the most recent stored snapshot.
    """
    if entry_id is None:
        entry_id = await resolve_default_entry_id(session, user.id)
        if entry_id is None:
            raise HTTPException(
                status_code=404,
                detail="No eligible entry found for this user.",
            )

    return await _build_trajectory(session, entry_id, days)


@router.get("/snapshots/{entry_id}", response_model=RankTrajectoryResponse)
async def get_entry_trajectory_route(
    entry_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    days: int = Query(7, ge=2, le=90),
) -> RankTrajectoryResponse:
    """Rank trajectory for any entry — powers the leaderboard's per-row
    sparkline column and the public profile.

    Visibility: owner / admin always; other viewers only after Phase 1
    deadline passes and the entry is eligible.
    """
    try:
        await get_entry_for_view(session, entry_id=entry_id, viewer=user)
    except EntryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except EntryAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    return await _build_trajectory(session, entry_id, days)


@router.get("/climbers", response_model=SteepestClimbersResponse)
async def get_climbers(
    session: DbSession,
    user: CurrentUser,
    days: int = Query(7, ge=2, le=90),
    # Cap raised from 20 → 100 so the Dashboard can request the full field
    # (it asks for 32 to cover any plausible competition size). 422'd
    # previously when the dashboard called /climbers?days=7&limit=32.
    limit: int = Query(5, ge=1, le=100),
) -> SteepestClimbersResponse:
    """Top-N entries by rank improvement over the last `days`.

    Used by the dashboard's "Steepest climb · group of 32" footer. Returns
    `places` positive when the entry climbed (e.g. 14 → 8 yields places=6).
    A user with two climbing entries will appear twice — that's intentional;
    entries are the unit of competition.
    """
    raw = await get_steepest_climbers(session, days=days, limit=limit)

    # Fetch entry display names + owner names in one shot
    entry_ids = [c["entry_id"] for c in raw]
    name_by_entry: dict[uuid.UUID, tuple[str, uuid.UUID, str]] = {}
    if entry_ids:
        result = await session.execute(
            select(PredictionEntry)
            .options(selectinload(PredictionEntry.user))
            .where(PredictionEntry.id.in_(entry_ids))
        )
        for entry in result.scalars().all():
            # Fall back to email-prefix for magic-link sign-ups that
            # haven't picked a display name on /onboarding yet.
            if entry.user:
                owner_name = entry.user.name or entry.user.email.split("@")[0]
            else:
                owner_name = "Unknown"
            name_by_entry[entry.id] = (entry.display_name, entry.user_id, owner_name)

    entries = []
    for c in raw:
        entry_name, user_id, user_name = name_by_entry.get(
            c["entry_id"], ("Unknown entry", c["user_id"], "Unknown")
        )
        entries.append(
            SteepestClimberEntry(
                entry_id=c["entry_id"],
                entry_name=entry_name,
                user_id=user_id,
                user_name=user_name,
                places=c["places"],
                current_position=c["current_position"],
                previous_position=c["previous_position"],
            )
        )

    # Pre-lock: filter to the viewer's own entries (blind pool). Admins
    # see everyone. Post-lock returns the full list.
    if not user.is_admin and not await is_phase1_locked(session):
        entries = [e for e in entries if e.user_id == user.id]

    return SteepestClimbersResponse(days=days, entries=entries)


# --------------------------------------------------------------------------
# Race-tab redesign schemas (2026-06-22 spec)
# --------------------------------------------------------------------------

RaceStoryKind = Literal[
    "biggest_climb",
    "steepest_fall",
    "hottest_streak",
    "phoenix",
    "slow_burn",
    "steady_hand",
]


class SparklinePoint(BaseModel):
    captured_date: date
    rank: int


class RaceStoryOut(BaseModel):
    kind: RaceStoryKind
    title: str
    caption: str
    subject_entry_id: uuid.UUID
    compare_entry_id: uuid.UUID | None = None
    sparkline: list[SparklinePoint]
    compare_sparkline: list[SparklinePoint] | None = None


class RaceStoriesResponse(BaseModel):
    stories: list[RaceStoryOut]
    generated_at: datetime


class ChampionTeamCount(BaseModel):
    team_code: str
    team_name: str
    count: int
    alive: bool


class ChampionSurvivalResponse(BaseModel):
    alive_count: int
    total_count: int
    teams: list[ChampionTeamCount]
    generated_at: datetime


class MatchMarker(BaseModel):
    fixture_id: str
    kickoff: datetime
    home_team_code: str
    away_team_code: str
    home_score: int
    away_score: int
    is_upset: bool
    impact_score: float


class MatchMarkersResponse(BaseModel):
    markers: list[MatchMarker]
    generated_at: datetime


@router.get("/race-stories", response_model=RaceStoriesResponse)
async def race_stories(
    session: DbSession,
    user: CurrentUser,
) -> RaceStoriesResponse:
    """Returns the 0-4 qualifying race-story cards. See spec §Story-cards grid."""
    from app.services.race_stories import select_race_stories  # lazy import: avoid circular
    raw = await select_race_stories(session)
    stories = [
        RaceStoryOut(
            kind=s.kind,
            title=s.title,
            caption=s.caption,
            subject_entry_id=s.subject_entry_id,
            compare_entry_id=s.compare_entry_id,
            sparkline=[SparklinePoint(captured_date=p.captured_date, rank=p.rank) for p in s.sparkline],
            compare_sparkline=(
                [SparklinePoint(captured_date=p.captured_date, rank=p.rank) for p in s.compare_sparkline]
                if s.compare_sparkline
                else None
            ),
        )
        for s in raw
    ]
    return RaceStoriesResponse(stories=stories, generated_at=utc_now())


@router.get("/champion-survival", response_model=ChampionSurvivalResponse)
async def champion_survival(
    session: DbSession,
    user: CurrentUser,
) -> ChampionSurvivalResponse:
    """Returns how much of the pool's champion pick is still alive."""
    from sqlalchemy import func
    from app.models.prediction import PredictionPhase, TeamPrediction
    from app.services.leaderboard import get_eliminated_teams
    from app.services.scoring import eligible_entry_ids_select
    from app.services.team_name import display_team_name

    if not await is_phase1_locked(session):
        return ChampionSurvivalResponse(alive_count=0, total_count=0, teams=[], generated_at=utc_now())

    eliminated: set[str] = await get_eliminated_teams(session)

    rows = (
        await session.execute(
            select(TeamPrediction.team, func.count().label("cnt"))
            .where(TeamPrediction.stage == "winner")
            .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
            .where(TeamPrediction.entry_id.in_(eligible_entry_ids_select()))
            .group_by(TeamPrediction.team)
            .order_by(func.count().desc(), TeamPrediction.team.asc())
        )
    ).all()

    teams: list[ChampionTeamCount] = [
        ChampionTeamCount(
            team_code=team,
            team_name=display_team_name(team),
            count=cnt,
            alive=(team not in eliminated),
        )
        for team, cnt in rows
    ]
    alive_count = sum(t.count for t in teams if t.alive)
    total_count = sum(t.count for t in teams)
    return ChampionSurvivalResponse(
        alive_count=alive_count,
        total_count=total_count,
        teams=teams[:8],  # top 8 per spec
        generated_at=utc_now(),
    )


class BonusHitRateOut(BaseModel):
    question_id: str
    correct_answers: list[str]
    hit_count: int
    eligible_count: int
    hit_rate: float  # 0-1


class BonusHitRatesResponse(BaseModel):
    questions: list[BonusHitRateOut]
    generated_at: datetime


@router.get("/bonus-hit-rates", response_model=BonusHitRatesResponse)
async def bonus_hit_rates(
    session: DbSession,
    user: CurrentUser,
) -> BonusHitRatesResponse:
    """Pool-wide % of eligible entries that got each RESOLVED bonus
    question right. Public: aggregate correctness of answers that are
    already resolved and publicly visible — no odds, no projection, so no
    win-probability gate. Unresolved questions are simply absent from the
    response (nothing computed until an admin records the answer, which
    only happens post-deadline, so no blind-pool concern)."""
    from app.services.bonus import compute_bonus_hit_rates
    from app.services.locking import get_active_competition

    competition = await get_active_competition(session)
    rates = await compute_bonus_hit_rates(
        session, competition.id if competition else None
    )
    return BonusHitRatesResponse(
        questions=[
            BonusHitRateOut(
                question_id=r.question_id,
                correct_answers=r.correct_answers,
                hit_count=r.hit_count,
                eligible_count=r.eligible_count,
                hit_rate=r.hit_rate,
            )
            for r in rates
        ],
        generated_at=utc_now(),
    )


@router.get("/match-markers", response_model=MatchMarkersResponse)
async def match_markers(
    session: DbSession,
    user: CurrentUser,
    days: int = Query(14, ge=1, le=60),
) -> MatchMarkersResponse:
    """Returns the 0-3 most-impactful KO match results for chart annotation."""
    from app.services.race_impact import compute_match_markers  # lazy import: avoid circular
    result = await compute_match_markers(session, days=days)
    return MatchMarkersResponse(
        markers=[
            MatchMarker(
                fixture_id=m.fixture_id,
                kickoff=m.kickoff,
                home_team_code=m.home_team_code,
                away_team_code=m.away_team_code,
                home_score=m.home_score,
                away_score=m.away_score,
                is_upset=m.is_upset,
                impact_score=m.impact_score,
            )
            for m in result.markers
        ],
        generated_at=result.generated_at,
    )


# --------------------------------------------------------------------------
# Dashboard-widgets schemas (2026-06-22 spec)
# --------------------------------------------------------------------------

class DailyMvp(BaseModel):
    captured_date: date
    subject_entry_id: str
    user_name: str
    entry_name: str
    day_points: int
    rank_delta: int  # positive = climbed, negative = dropped


class DailyMvpsResponse(BaseModel):
    mvps: list[DailyMvp]
    generated_at: datetime


class TrailPoint(BaseModel):
    captured_date: date
    your_points: int
    pool_avg_points: float


class EntryTrail(BaseModel):
    entry_id: str
    entry_name: str
    current_rank: int
    current_gap: float
    points: list[TrailPoint]


class PersonalTrailResponse(BaseModel):
    entries: list[EntryTrail]
    generated_at: datetime


class DistBin(BaseModel):
    bucket_start: int
    bucket_end: int
    count: int


class YourEntryMarker(BaseModel):
    entry_id: str
    entry_name: str
    points: int
    position: int


class PoolDistributionResponse(BaseModel):
    bins: list[DistBin]
    bucket_width: int
    min_points: int
    max_points: int
    total_entries: int
    your_entries: list[YourEntryMarker]
    caption: str
    generated_at: datetime


@router.get("/daily-mvps", response_model=DailyMvpsResponse)
async def daily_mvps(
    session: DbSession,
    user: CurrentUser,
) -> DailyMvpsResponse:
    """Returns up to 5 daily MVPs (top scorer per day, most-recent-first)."""
    from app.services.dashboard_stats import compute_daily_mvps

    raw = await compute_daily_mvps(session)
    return DailyMvpsResponse(
        mvps=[
            DailyMvp(
                captured_date=m.captured_date,
                subject_entry_id=m.subject_entry_id,
                user_name=m.user_name,
                entry_name=m.entry_name,
                day_points=m.day_points,
                rank_delta=m.rank_delta,
            )
            for m in raw
        ],
        generated_at=utc_now(),
    )


@router.get("/personal-trail", response_model=PersonalTrailResponse)
async def personal_trail(
    session: DbSession,
    user: CurrentUser,
) -> PersonalTrailResponse:
    """Returns the requesting user's entries' point trails vs the pool average."""
    from app.services.dashboard_stats import compute_personal_trail
    raw = await compute_personal_trail(session, user_id=str(user.id))
    return PersonalTrailResponse(
        entries=[
            EntryTrail(
                entry_id=t.entry_id,
                entry_name=t.entry_name,
                current_rank=t.current_rank,
                current_gap=t.current_gap,
                points=[
                    TrailPoint(captured_date=p.captured_date, your_points=p.your_points, pool_avg_points=p.pool_avg_points)
                    for p in t.points
                ],
            )
            for t in raw
        ],
        generated_at=utc_now(),
    )


@router.get("/pool-distribution", response_model=PoolDistributionResponse)
async def pool_distribution(
    session: DbSession,
    user: CurrentUser,
) -> PoolDistributionResponse:
    """Full-pool points histogram with every entry the user owns marked."""
    from app.services.dashboard_stats import compute_pool_distribution
    r = await compute_pool_distribution(session, user_id=str(user.id))
    return PoolDistributionResponse(
        bins=[
            DistBin(bucket_start=b.bucket_start, bucket_end=b.bucket_end, count=b.count)
            for b in r.bins
        ],
        bucket_width=r.bucket_width,
        min_points=r.min_points,
        max_points=r.max_points,
        total_entries=r.total_entries,
        your_entries=[
            YourEntryMarker(
                entry_id=e.entry_id, entry_name=e.entry_name,
                points=e.points, position=e.position,
            )
            for e in r.your_entries
        ],
        caption=r.caption,
        generated_at=r.generated_at,
    )


# ---------------------------------------------------------------------------
# Group Stage Winner card (v2.181.0)
# ---------------------------------------------------------------------------
# Gated on Competition.group_stage_winner_released. Admins flip the switch
# from /admin at 7pm Malta on Sunday 28 June 2026; until then this endpoint
# returns null and the dashboard card stays hidden. Once released, the
# payload populates the GroupStageWinnerCard above the DailyMvpStrip AND
# fills the GROUP_STAGE_FINAL broadcast email body. Single source of truth.


@router.get("/group-stage-winner", response_model=None)
async def group_stage_winner_endpoint(
    session: DbSession,
    user: CurrentUser,
):
    """Return the Group Stage podium payload (or null if not released).

    URL preserved from v2.181.0 for compat; response shape upgraded in
    v2.183.x from a single winner to top-3 podium so the dashboard card
    can surface the runners-up alongside the champion. Null = card
    hidden (release flag not flipped). Caller decides what to render.
    """
    from sqlalchemy import select
    from app.models.competition import Competition
    from app.schemas.group_stage_winner import GroupStageEntry, GroupStagePodium
    from app.services.group_stage_winner import get_group_stage_podium

    comp_row = (
        await session.execute(
            select(Competition).where(Competition.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if comp_row is None or not comp_row.group_stage_winner_released:
        return None

    podium = await get_group_stage_podium(session)
    if podium is None or not podium.entries:
        return None

    return GroupStagePodium(
        entries=[
            GroupStageEntry(
                entry_id=e.entry_id,
                user_name=e.user_name,
                entry_name=e.entry_name,
                display_name=e.display_name,
                final_rank=e.final_rank,
                total_points=e.total_points,
                outcome_points=e.outcome_points,
                exact_score_extra=e.exact_score_extra,
                rarity_extra=e.rarity_extra,
                bonus_question_points=e.bonus_question_points,
            )
            for e in podium.entries
        ],
        champion_pick=podium.champion_pick,
        champion_alive=podium.champion_alive,
        finalist_picks=podium.finalist_picks,
        finalists_alive=podium.finalists_alive,
        days_at_top=podium.days_at_top,
        total_days=podium.total_days,
        runner_up_gap=podium.runner_up_gap,
        story_line=podium.story_line,
        audit_verified=podium.audit_verified,
        generated_at=podium.generated_at,
    )


# ---------------------------------------------------------------------------
# Final podium / tournament conclusion (Plan A Task A5)
# ---------------------------------------------------------------------------
# Gate: visible to EVERYONE once Competition.tournament_concluded is true;
# admins may preview the payload any time before the flip (dress-rehearsal).
# Mirrors the group-stage-winner endpoint's admin-preview precedent but adds
# an anonymous-allowed path for the post-conclusion, fully-public wrap-up
# page — hence `OptionalUser` rather than `CurrentUser` here.


@router.get("/final-podium", response_model=None)
async def final_podium_endpoint(
    session: DbSession,
    user: OptionalUser,
):
    """Champion announcement payload. Visible to EVERYONE once
    tournament_concluded; admins may preview before the flip."""
    from app.models.competition import Competition
    from app.models.fixture import Fixture
    from app.schemas.tournament_champion import (
        AuditSummaryOut,
        FinalMatchOut,
        FinalPodium,
        FinalPodiumEntry,
        TriondaOut,
    )
    from app.services.final_audit import load_latest_audit_summary
    from app.services.tournament_champion import get_final_podium

    comp = (
        await session.execute(
            select(Competition).where(Competition.is_active.is_(True))
        )
    ).scalar_one_or_none()
    concluded = bool(comp and comp.tournament_concluded)
    if not concluded and not (user and user.is_admin):
        return None

    podium = await get_final_podium(session)
    if podium is None:
        return None

    # The Final fixture (stage == 'final'); its real result overrides A4's
    # leaderboard-leader-pick fallback for champion_hit. Score is a SEPARATE
    # joined table (see app/models/score.py) — must be eager-loaded via
    # selectinload, matching the pattern in app/api/fixtures.py.
    final_fx = (
        (
            await session.execute(
                select(Fixture)
                .options(selectinload(Fixture.score))
                .where(Fixture.stage == "final")
            )
        )
        .scalars()
        .first()
    )

    final_match = None
    actual_winner: str | None = None
    if final_fx is not None:
        score = final_fx.score
        home = away = None
        pens = None
        et = False
        if score is not None:
            # final_home_score/final_away_score are properties on Score
            # that already fall back to regular time when ET is unset.
            home = score.final_home_score
            away = score.final_away_score
            et = score.home_score_et is not None or score.away_score_et is not None
            if score.home_penalties is not None and score.away_penalties is not None:
                pens = f"{score.home_penalties}-{score.away_penalties}"
            if score.outcome == "1":
                actual_winner = final_fx.home_team
            elif score.outcome == "2":
                actual_winner = final_fx.away_team
        final_match = FinalMatchOut(
            home_team=final_fx.home_team,
            away_team=final_fx.away_team,
            home_score=home,
            away_score=away,
            went_to_extra_time=et,
            penalties=pens,
            kickoff=final_fx.kickoff,
            # Fixture carries no venue fields in this codebase — left None
            # rather than guessing at a schema that doesn't exist.
            venue=None,
            narrative=comp.final_match_narrative if comp else None,
        )

    entries = []
    for e in podium["entries"]:
        e = dict(e)
        if actual_winner:
            e["champion_hit"] = e["champion_pick"] == actual_winner
        entries.append(FinalPodiumEntry(**e))

    t = podium["trionda"]
    trionda = TriondaOut(
        recipient_name=t.recipient.user_name if t.recipient else None,
        recipient_entry_id=str(t.recipient.entry_id) if t.recipient else None,
        final_rank=t.recipient.position if t.recipient else None,
        reason=t.reason,
        requires_draw=t.requires_draw,
        draw_candidate_names=[c.user_name for c in t.draw_candidates],
    )

    audit_summary = load_latest_audit_summary()
    audit = AuditSummaryOut(**audit_summary) if audit_summary else None

    return FinalPodium(
        entries=entries,
        trionda=trionda,
        story_line=podium["story_line"],
        total_days=podium["total_days"],
        final_match=final_match,
        audit=audit,
    )


# ---------------------------------------------------------------------------
# Pool-vs-tournament retrospective (Plan A Task A7)
# ---------------------------------------------------------------------------
# Same gate precedent as /final-podium: visible to everyone once
# tournament_concluded, admins may preview beforehand.


@router.get("/pool-retrospective", response_model=None)
async def pool_retrospective_endpoint(
    session: DbSession,
    user: OptionalUser,
):
    """Pool-vs-tournament wrap-up payload (or null pre-conclusion for
    non-admins). Aggregates collective stats (misses/bankers, KO ladder,
    bonus hit rates, champion distribution) plus a per-member personal
    wrap when a signed-in user is present."""
    from sqlalchemy import select as sa_select

    from app.models.competition import Competition
    from app.schemas.pool_retrospective import PoolRetrospective
    from app.services.pool_retrospective import compute_pool_retrospective

    comp = (
        await session.execute(
            sa_select(Competition).where(Competition.is_active.is_(True))
        )
    ).scalar_one_or_none()
    concluded = bool(comp and comp.tournament_concluded)
    if not concluded and not (user and user.is_admin):
        return None

    data = await compute_pool_retrospective(
        session, for_user_id=user.id if user else None
    )
    return PoolRetrospective(**data)


# ---------------------------------------------------------------------------
# Knockout win-probability simulator
# ---------------------------------------------------------------------------
# Gate mirrors the all-entries CSV export pattern (predictions.py):
# admin always; non-admin only once Competition.win_probability_enabled is
# flipped from /admin. Read-time gate — no cache invalidation on toggle.


class TitleWorld(BaseModel):
    """One 'if this team lifts the cup' world for a single entry."""

    team: str
    trophy_odds: float
    p_win_given_champion: float


class DecisiveMatch(BaseModel):
    """One upcoming match and how its result swings the entry's win odds."""

    match_number: int
    stage: str
    home_team: str
    away_team: str
    p_win_if_home: float
    p_win_if_away: float


class EntryWinProbability(BaseModel):
    entry_id: str
    p_win: float
    p_top3: float
    expected_rank: float
    # Per-entry conditional breakdown (uniform view only; the odds-weighted
    # view leaves these at their defaults). Powers the inline "what has to
    # happen for you to win" card in the Win Probability tab.
    projected_points: float = 0.0
    title_worlds: list[TitleWorld] = []
    decisive_matches: list[DecisiveMatch] = []


class TeamStageOdds(BaseModel):
    team: str
    stage_odds: dict[str, float]


class WinProbabilityMeta(BaseModel):
    mode: str
    unresolved_matches: int
    scenario_count: int
    computed_at: datetime


class OddsWeightedView(BaseModel):
    entries: list[EntryWinProbability]
    teams: list[TeamStageOdds]


class OddsCoverage(BaseModel):
    priced: int
    priceable: int


class ScenarioOutcomeOut(BaseModel):
    outcomes: dict[int, str]  # match_number -> winning team (unresolved matches)
    weight: float
    champion_entry_ids: list[str]
    champion_points: int


class MatchMetaEntry(BaseModel):
    match_number: int
    home_team: str
    away_team: str
    stage: str


class WinProbabilityResponse(BaseModel):
    entries: list[EntryWinProbability]
    teams: list[TeamStageOdds]
    meta: WinProbabilityMeta
    # None when nothing in the remaining bracket is priceable yet (every
    # unresolved match still has at least one TBD side) — the frontend's
    # signal to hide the odds-weighted column rather than render a
    # "second view" that's silently identical to the uniform one.
    odds_weighted: OddsWeightedView | None = None
    odds_coverage: OddsCoverage = OddsCoverage(priced=0, priceable=0)
    # NOTE: the raw per-scenario outcome list moved to the separate, public
    # GET /leaderboard/trophy-scenarios endpoint (Path to the Trophy is
    # deliberately NOT gated behind win_probability_enabled, unlike the
    # per-entry P(win)/trophy-odds breakdown this endpoint carries).


def _build_view(
    result: "PoolSimulationResult", *, include_conditionals: bool = False
) -> tuple[list[EntryWinProbability], list[TeamStageOdds]]:
    """Project a PoolSimulationResult into API shape.

    `projected_points` comes straight off the engine's `expected_points` for
    every entry in every view — the frontend picks a single "effective"
    view (odds-weighted when priced, else uniform) for its Prob%/Proj
    columns and the inline entry card, so both views need it populated.
    `include_conditionals` additionally enriches each entry with its title
    worlds + decisive matches via the engine's pure
    `build_entry_conditionals` — requested for whichever view ends up being
    the effective one (currently both, since the odds-weighted view may be
    the one the frontend renders the card from).
    """
    from app.services.win_probability import build_entry_conditionals

    entries: list[EntryWinProbability] = []
    for entry_id, p in result.entries.items():
        projected_points = p.expected_points
        title_worlds: list[TitleWorld] = []
        decisive_matches: list[DecisiveMatch] = []
        if include_conditionals:
            b = build_entry_conditionals(result, entry_id)
            title_worlds = [
                TitleWorld(
                    team=w.team,
                    trophy_odds=w.trophy_odds,
                    p_win_given_champion=w.p_win_given_champion,
                )
                for w in b.title_worlds
            ]
            decisive_matches = [
                DecisiveMatch(
                    match_number=d.match_number,
                    stage=d.stage,
                    home_team=d.home_team,
                    away_team=d.away_team,
                    p_win_if_home=d.p_win_if_home,
                    p_win_if_away=d.p_win_if_away,
                )
                for d in b.decisive_matches
            ]
        entries.append(
            EntryWinProbability(
                entry_id=entry_id,
                p_win=p.p_win,
                p_top3=p.p_top3,
                expected_rank=p.expected_rank,
                projected_points=projected_points,
                title_worlds=title_worlds,
                decisive_matches=decisive_matches,
            )
        )
    teams = [TeamStageOdds(team=team, stage_odds=odds) for team, odds in result.team_stage_odds.items()]
    return entries, teams


@router.get("/win-probability", response_model=WinProbabilityResponse)
async def win_probability_endpoint(
    session: DbSession,
    user: CurrentUser,
) -> WinProbabilityResponse:
    """P(each entry wins the pool) + P(top-3) + expected rank, computed by
    simulating every remaining knockout match under a uniform 50/50
    per-match model, plus an odds-weighted second view when live betting
    odds price at least one of the next unresolved matches. Team
    trophy-odds ride along as a byproduct of the same enumeration. See
    app.services.win_probability for the engine.
    """
    from app.services.locking import get_active_competition
    from app.services.win_probability import get_win_probability

    competition = await get_active_competition(session)
    if not (user.is_admin or (competition and competition.win_probability_enabled)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Win probability not yet released",
        )

    try:
        comparison = await get_win_probability(session)
    except Exception:
        # Fail-open — same philosophy as live_projection.apply_live_projection:
        # a simulator bug degrades to "odds unavailable," never a 500.
        logger.exception("win-probability computation failed")
        return WinProbabilityResponse(
            entries=[],
            teams=[],
            meta=WinProbabilityMeta(
                mode="unavailable",
                unresolved_matches=0,
                scenario_count=0,
                computed_at=utc_now(),
            ),
        )

    uniform = comparison.uniform
    entries, teams = _build_view(uniform, include_conditionals=True)

    odds_weighted = None
    if comparison.odds_weighted is not None:
        odds_entries, odds_teams = _build_view(comparison.odds_weighted, include_conditionals=True)
        odds_weighted = OddsWeightedView(entries=odds_entries, teams=odds_teams)

    return WinProbabilityResponse(
        entries=entries,
        teams=teams,
        meta=WinProbabilityMeta(
            mode=uniform.mode,
            unresolved_matches=uniform.unresolved_matches,
            scenario_count=uniform.scenario_count,
            computed_at=uniform.computed_at,
        ),
        odds_weighted=odds_weighted,
        odds_coverage=OddsCoverage(
            priced=comparison.odds_matches_priced,
            priceable=comparison.odds_matches_priceable,
        ),
    )


class TrophyScenariosResponse(BaseModel):
    scenarios: list[ScenarioOutcomeOut] = []
    match_meta: list[MatchMetaEntry] = []
    generated_at: datetime


@router.get("/trophy-scenarios", response_model=TrophyScenariosResponse)
async def trophy_scenarios(
    session: DbSession,
    user: CurrentUser,
) -> TrophyScenariosResponse:
    """Every remaining bracket completion + who wins the pool under it
    (Path to the Trophy card). Deliberately PUBLIC — no admin/
    win_probability_enabled gate. This is a bracket-completion fact,
    conceptually different from the per-entry P(win)/trophy-odds
    breakdown on /win-probability, which stays gated. Blind-pool gated
    only (empty pre-deadline, same as champion-survival/consensus-bracket)
    — reads the same cached simulation /win-probability uses, so no extra
    compute cost. Fail-open: any simulator error degrades to empty lists,
    never a 500.
    """
    from app.services.win_probability import get_win_probability

    if not await is_phase1_locked(session):
        return TrophyScenariosResponse(scenarios=[], match_meta=[], generated_at=utc_now())

    try:
        comparison = await get_win_probability(session)
    except Exception:
        logger.exception("trophy-scenarios computation failed")
        return TrophyScenariosResponse(scenarios=[], match_meta=[], generated_at=utc_now())

    effective = comparison.odds_weighted or comparison.uniform
    return TrophyScenariosResponse(
        scenarios=[
            ScenarioOutcomeOut(
                outcomes=s.outcomes,
                weight=s.weight,
                champion_entry_ids=list(s.champion_entry_ids),
                champion_points=s.champion_points,
            )
            for s in comparison.scenarios
        ],
        match_meta=[
            MatchMetaEntry(match_number=m, home_team=h, away_team=a, stage=st)
            for m, (h, a, st) in effective.scenario_match_meta.items()
        ],
        generated_at=utc_now(),
    )


class ChampionMarketOdds(BaseModel):
    team: str  # internal team name (matches TeamPrediction.team / fixtures)
    market_odds: float  # 0-1, Polymarket P(this team wins the tournament)


class ChampionMarketOddsResponse(BaseModel):
    odds: list[ChampionMarketOdds]
    computed_at: datetime


@router.get("/champion-market-odds", response_model=ChampionMarketOddsResponse)
async def champion_market_odds(
    session: DbSession,
    user: CurrentUser,
) -> ChampionMarketOddsResponse:
    """Live Polymarket "to win the tournament" odds per team, joined to the
    competition's internal team names server-side (so the frontend matches
    by plain team name, no client canonicalisation).

    Gated identically to /win-probability — admin always, non-admin only
    once `Competition.win_probability_enabled` is flipped on. Same lever,
    same staged rollout: this surfaces market-derived odds, which the flag
    exists to control. Fail-open: any Polymarket hiccup degrades to an
    empty odds list (the service already serves last-good / empty on
    error), never a 500."""
    from app.models.fixture import Fixture
    from app.services.locking import get_active_competition
    from app.services.polymarket import get_stage_reach_probabilities
    from app.services.team_match import canonicalize

    competition = await get_active_competition(session)
    if not (user.is_admin or (competition and competition.win_probability_enabled)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Championship market odds not yet released",
        )

    odds: list[ChampionMarketOdds] = []
    try:
        poly = await get_stage_reach_probabilities("winner")  # {canonical: P(Yes)}
        if poly:
            # Real team names in the competition, joined to Polymarket via the
            # same canonicalize() the win-probability engine uses.
            team_rows = (
                await session.execute(select(Fixture.home_team, Fixture.away_team))
            ).all()
            teams: set[str] = set()
            for home, away in team_rows:
                for t in (home, away):
                    if t and t != "TBD" and not t.startswith("slot:"):
                        teams.add(t)
            for t in sorted(teams):
                p = poly.get(canonicalize(t))
                if p is not None:
                    odds.append(ChampionMarketOdds(team=t, market_odds=p))
    except Exception:
        logger.exception("champion-market-odds computation failed")
        odds = []

    return ChampionMarketOddsResponse(odds=odds, computed_at=utc_now())


class ConsensusTeamRow(BaseModel):
    team: str
    # Furthest stage the team ACTUALLY reached; None = out in the group
    # stage (never seeded into a knockout).
    actual_stage: str | None
    alive: bool
    # stage -> number of eligible entries who picked the team to reach it.
    # Cumulative (a champion pick also counts toward every earlier stage).
    picks_by_stage: dict[str, int]


class ConsensusBracketResponse(BaseModel):
    rows: list[ConsensusTeamRow]
    eligible_count: int  # denominator for the % the frontend renders
    generated_at: datetime


@router.get("/consensus-bracket", response_model=ConsensusBracketResponse)
async def consensus_bracket(
    session: DbSession,
    user: CurrentUser,
) -> ConsensusBracketResponse:
    """Pool pick distribution per knockout stage: for every team that got
    any KO pick, how many eligible entries picked it to reach each stage,
    plus where it ACTUALLY ended up. Public — it's the pool's own picks
    against public results, no odds/projection — but blind-pool gated (no
    data before the deadline locks, same as champion-survival)."""
    from sqlalchemy import func

    from app.models.prediction import PredictionPhase, TeamPrediction
    from app.services.leaderboard import get_eliminated_teams
    from app.services.scoring import eligible_entry_ids_select, get_actual_advancement

    if not await is_phase1_locked(session):
        return ConsensusBracketResponse(rows=[], eligible_count=0, generated_at=utc_now())

    ko_stages = [
        "round_of_32",
        "round_of_16",
        "quarter_final",
        "semi_final",
        "final",
        "winner",
    ]
    eligible_select = eligible_entry_ids_select()
    eligible_count = (
        await session.execute(select(func.count()).select_from(eligible_select.subquery()))
    ).scalar_one()

    count_rows = (
        await session.execute(
            select(TeamPrediction.team, TeamPrediction.stage, func.count().label("cnt"))
            .where(TeamPrediction.stage.in_(ko_stages))
            .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
            .where(TeamPrediction.entry_id.in_(eligible_entry_ids_select()))
            .group_by(TeamPrediction.team, TeamPrediction.stage)
        )
    ).all()

    picks: dict[str, dict[str, int]] = {}
    for team, stage, cnt in count_rows:
        picks.setdefault(team, {})[stage] = cnt

    advancement = await get_actual_advancement(session)  # team -> furthest stage
    eliminated = await get_eliminated_teams(session)

    rows = [
        ConsensusTeamRow(
            team=team,
            actual_stage=advancement.get(team),
            alive=team not in eliminated,
            picks_by_stage=by_stage,
        )
        for team, by_stage in picks.items()
    ]
    # Default order: most-fancied champion first (frontend may re-sort).
    rows.sort(key=lambda r: (-r.picks_by_stage.get("winner", 0), r.team))

    return ConsensusBracketResponse(
        rows=rows, eligible_count=eligible_count, generated_at=utc_now()
    )
