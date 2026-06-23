"""Leaderboard API routes — entry-scoped.

Each row of the leaderboard is one `PredictionEntry`. Endpoints that
previously took a `user_id` now take an `entry_id`. The `/snapshots/me`
convenience route picks the requesting user's first eligible entry by
default; pass `?entry_id=<uuid>` to target a specific one.
"""

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

RaceStoryKind = Literal["biggest_climb", "steepest_fall", "closest_race", "hottest_streak"]


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


class CohortTrailPoint(BaseModel):
    captured_date: date
    median_rank: float


CohortKind = Literal["atlas", "jmfa", "guests", "all"]


class CohortTrailItem(BaseModel):
    cohort: CohortKind
    entry_count: int
    points: list[CohortTrailPoint]
    current_median_rank: float


class CohortAnnotation(BaseModel):
    cohort: CohortKind
    captured_date: date
    caption: str


class CohortTrailResponse(BaseModel):
    cohorts: list[CohortTrailItem]
    annotations: list[CohortAnnotation]
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


@router.get("/cohort-trail", response_model=CohortTrailResponse)
async def cohort_trail(
    session: DbSession,
    user: CurrentUser,
    days: int = Query(30, ge=7, le=90),
) -> CohortTrailResponse:
    """Returns the median rank trail per cohort over the last `days` days."""
    from app.services.cohort_race import compute_cohort_trail
    result = await compute_cohort_trail(session, days=days)
    return CohortTrailResponse(
        cohorts=[
            CohortTrailItem(
                cohort=c.cohort,
                entry_count=c.entry_count,
                points=[
                    CohortTrailPoint(captured_date=p.captured_date, median_rank=p.median_rank)
                    for p in c.points
                ],
                current_median_rank=c.current_median_rank,
            )
            for c in result.cohorts
        ],
        annotations=[
            CohortAnnotation(cohort=a.cohort, captured_date=a.captured_date, caption=a.caption)
            for a in result.annotations
        ],
        generated_at=result.generated_at,
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
    points_delta: int
    count: int


class PoolDistributionResponse(BaseModel):
    user_points: int
    window_size: int
    bins: list[DistBin]
    next_rank_points_away: int | None
    next_rank_position: int | None
    near_count: int
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
    """Returns the histogram of entries around the requesting user's points total."""
    from app.services.dashboard_stats import compute_pool_distribution
    r = await compute_pool_distribution(session, user_id=str(user.id))
    return PoolDistributionResponse(
        user_points=r.user_points,
        window_size=r.window_size,
        bins=[DistBin(points_delta=b.points_delta, count=b.count) for b in r.bins],
        next_rank_points_away=r.next_rank_points_away,
        next_rank_position=r.next_rank_position,
        near_count=r.near_count,
        caption=r.caption,
        generated_at=r.generated_at,
    )
