"""Leaderboard API routes — entry-scoped.

Each row of the leaderboard is one `PredictionEntry`. Endpoints that
previously took a `user_id` now take an `entry_id`. The `/snapshots/me`
convenience route picks the requesting user's first eligible entry by
default; pass `?entry_id=<uuid>` to target a specific one.
"""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.dependencies import AdminUser, CurrentUser, DbSession, OptionalUser
from app.models.entry import PredictionEntry
from app.models.user import User
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
from app.services.snapshots import get_entry_trajectory, get_steepest_climbers

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
