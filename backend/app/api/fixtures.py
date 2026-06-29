"""Fixtures API routes."""

import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.dependencies import AdminUser, CurrentUser, DbSession, OptionalUser
from app.models._datetime import utc_now
from app.models.audit import ActorRole
from app.models.fixture import Fixture, MatchStatus
from app.schemas.fixture import (
    FixtureCreate,
    FixtureRead,
    FixtureScore,
    FixturesByGroup,
    FixtureStatusUpdate,
    FixtureUpdate,
    LockStatus,
)
from app.services.audit import record_audit_event
from app.services.ko_lineup_resolver import (
    KoLineupResolver,
    build_ko_lineup_resolver,
    resolve_ko_pair,
)
from app.services.locking import get_active_competition
from app.services.standings import (
    get_actual_group_standings,
    get_group_positions,
    get_qualifying_third_place_teams,
)

router = APIRouter()

LOCK_MINUTES = 5


def fixture_to_read(
    fixture: Fixture,
    resolver: KoLineupResolver | None = None,
) -> FixtureRead:
    """Convert Fixture model to FixtureRead schema.

    When `resolver` is supplied, slot placeholders are replaced by real
    team names across ALL knockout stages (v2.184.x — extends the v2.182.1
    R32-only resolver to R16/QF/SF/F by walking the bracket). The DB rows
    themselves are never written — Football-Data's eventual official
    lineup still wins when it lands via score_sync.
    """
    time_until = fixture.time_until_lock(LOCK_MINUTES)

    # Emit score whenever a row exists — covers LIVE / HALFTIME / FINISHED.
    # The score_scheduler writes Score rows for in-play matches too, so the
    # Dashboard can read live numbers from the same field used for finals.
    score_data = None
    if fixture.score:
        score_data = FixtureScore(
            home_score=fixture.score.home_score,
            away_score=fixture.score.away_score,
            home_score_et=fixture.score.home_score_et,
            away_score_et=fixture.score.away_score_et,
            home_penalties=fixture.score.home_penalties,
            away_penalties=fixture.score.away_penalties,
            outcome=fixture.score.outcome,
            verified=fixture.score.verified,
        )

    home_team = fixture.home_team
    away_team = fixture.away_team
    if resolver is not None and fixture.stage in (
        "round_of_32",
        "round_of_16",
        "quarter_final",
        "semi_final",
        "final",
    ):
        resolved_home, resolved_away = resolve_ko_pair(resolver, fixture)
        if resolved_home:
            home_team = resolved_home
        if resolved_away:
            away_team = resolved_away

    return FixtureRead(
        id=fixture.id,
        home_team=home_team,
        away_team=away_team,
        kickoff=fixture.kickoff,
        stage=fixture.stage,
        group=fixture.group,
        match_number=fixture.match_number,
        status=fixture.status,
        minute=fixture.minute,
        is_locked=fixture.is_locked(LOCK_MINUTES),
        time_until_lock=int(time_until.total_seconds()) if time_until else None,
        score=score_data,
    )


@router.get("/", response_model=list[FixtureRead])
async def get_all_fixtures(session: DbSession, _user: OptionalUser) -> list[FixtureRead]:
    """Get all fixtures ordered by kickoff time."""
    result = await session.execute(select(Fixture).options(selectinload(Fixture.score)).order_by(Fixture.kickoff, Fixture.match_number))
    fixtures = result.scalars().all()
    resolver = await build_ko_lineup_resolver(session)
    return [fixture_to_read(f, resolver) for f in fixtures]


@router.get("/groups", response_model=list[FixturesByGroup])
async def get_group_fixtures(session: DbSession, _user: OptionalUser) -> list[FixturesByGroup]:
    """Get group stage fixtures organized by group."""
    result = await session.execute(
        select(Fixture)
        .options(selectinload(Fixture.score))
        .where(Fixture.stage == "group")
        .order_by(Fixture.group, Fixture.kickoff, Fixture.match_number)
    )
    fixtures = result.scalars().all()

    # Group-stage endpoint never returns knockout fixtures, so no resolver
    # build required — saves one DB round-trip on the hottest path.
    groups: dict[str, list[FixtureRead]] = {}
    for fixture in fixtures:
        group = fixture.group or "Unknown"
        if group not in groups:
            groups[group] = []
        groups[group].append(fixture_to_read(fixture))

    return [FixturesByGroup(group=g, fixtures=f) for g, f in sorted(groups.items())]


@router.get("/knockout", response_model=list[FixtureRead])
async def get_knockout_fixtures(session: DbSession, _user: OptionalUser) -> list[FixtureRead]:
    """Get knockout stage fixtures."""
    result = await session.execute(
        select(Fixture)
        .options(selectinload(Fixture.score))
        .where(Fixture.stage != "group")
        .order_by(Fixture.kickoff, Fixture.match_number)
    )
    fixtures = result.scalars().all()
    resolver = await build_ko_lineup_resolver(session)
    return [fixture_to_read(f, resolver) for f in fixtures]


class TeamStandingResponse(BaseModel):
    """Team standing in a group."""

    team: str
    group: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int


class ActualStandingsResponse(BaseModel):
    """Actual group standings computed from finished matches."""

    standings: dict[str, list[TeamStandingResponse]]
    qualifying_third_place: list[TeamStandingResponse]


@router.get("/knockout/actual", response_model=list[FixtureRead])
async def get_actual_knockout_fixtures(
    session: DbSession,
    current_user: CurrentUser,
) -> list[FixtureRead]:
    """Get knockout fixtures with actual teams (requires Phase 2 active).

    This endpoint returns knockout fixtures where team names have been
    populated based on actual group stage results.
    """
    # Check if Phase 2 is active
    competition = await get_active_competition(session)
    if not competition or not competition.is_phase2_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phase 2 is not active",
        )

    # Get knockout fixtures
    result = await session.execute(
        select(Fixture)
        .options(selectinload(Fixture.score))
        .where(Fixture.stage != "group")
        .order_by(Fixture.kickoff, Fixture.match_number)
    )
    fixtures = result.scalars().all()

    resolver = await build_ko_lineup_resolver(session)
    return [fixture_to_read(f, resolver) for f in fixtures]


@router.get("/standings/actual", response_model=ActualStandingsResponse)
async def get_actual_standings(
    session: DbSession,
    current_user: CurrentUser,
) -> ActualStandingsResponse:
    """Actual group standings computed from finished matches (v2.181.1).

    Gate: admin always; non-admin only when the active competition has
    flipped `post_deadline_live` ('Go live' on /admin). Mirrors the V4
    pages' rollout pattern — admins verify standings in prod, then one
    flip exposes the page to the pool. No phase gate: standings are
    derived from public match results, so the only reason to hide them
    is the pre-tournament holding window.
    """
    competition = await get_active_competition(session)
    if not current_user.is_admin and (
        not competition or not competition.post_deadline_live
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Standings not yet released",
        )

    standings = await get_actual_group_standings(session)
    qualifying_third = await get_qualifying_third_place_teams(session)

    return ActualStandingsResponse(
        standings={
            group: [TeamStandingResponse(**t) for t in teams]
            for group, teams in standings.items()
        },
        qualifying_third_place=[TeamStandingResponse(**t) for t in qualifying_third],
    )


@router.get("/{fixture_id}", response_model=FixtureRead)
async def get_fixture(fixture_id: uuid.UUID, session: DbSession, _user: OptionalUser) -> FixtureRead:
    """Get a single fixture by ID."""
    result = await session.execute(select(Fixture).options(selectinload(Fixture.score)).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    # Build resolver only when the requested fixture is in R32 — saves a
    # standings query on every group-fixture detail open.
    resolver = await build_ko_lineup_resolver(session) if fixture.stage == "round_of_32" else None
    return fixture_to_read(fixture, resolver)


@router.get("/{fixture_id}/lock-status", response_model=LockStatus)
async def get_lock_status(
    fixture_id: uuid.UUID, session: DbSession, _user: OptionalUser
) -> LockStatus:
    """Check lock status for a fixture."""
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    locks_at = fixture.kickoff - timedelta(minutes=LOCK_MINUTES)

    return LockStatus(
        fixture_id=fixture.id,
        is_locked=fixture.is_locked(LOCK_MINUTES),
        locks_at=locks_at,
        time_remaining=fixture.time_until_lock(LOCK_MINUTES),
    )


# Admin endpoints
@router.post("/", response_model=FixtureRead, status_code=status.HTTP_201_CREATED)
async def create_fixture(
    fixture_data: FixtureCreate,
    session: DbSession,
    _admin: AdminUser,
) -> FixtureRead:
    """Create a new fixture (admin only)."""
    fixture = Fixture(
        competition_id=fixture_data.competition_id,
        home_team=fixture_data.home_team,
        away_team=fixture_data.away_team,
        kickoff=fixture_data.kickoff,
        stage=fixture_data.stage,
        group=fixture_data.group,
        match_number=fixture_data.match_number,
        external_id=fixture_data.external_id,
        status=MatchStatus.SCHEDULED,
    )
    session.add(fixture)
    await session.commit()
    await session.refresh(fixture)
    return fixture_to_read(fixture)


@router.put("/{fixture_id}", response_model=FixtureRead)
async def update_fixture(
    fixture_id: uuid.UUID,
    fixture_data: FixtureUpdate,
    session: DbSession,
    admin: AdminUser,
) -> FixtureRead:
    """Update a fixture (admin only)."""
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    update_data = fixture_data.model_dump(exclude_unset=True)
    old_values = {field: getattr(fixture, field) for field in update_data}
    for field, value in update_data.items():
        setattr(fixture, field, value)

    fixture.updated_at = utc_now()

    record_audit_event(
        session,
        event_type="fixture.admin_update",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="fixture",
        subject_id=fixture.id,
        metadata={
            "stage": fixture.stage,
            "old": {k: str(v) for k, v in old_values.items()},
            "new": {k: str(v) for k, v in update_data.items()},
        },
    )

    await session.commit()
    await session.refresh(fixture)
    # fixture_to_read touches fixture.score — load it explicitly; a lazy
    # load after refresh raises MissingGreenlet under the async driver.
    await session.refresh(fixture, attribute_names=["score"])
    return fixture_to_read(fixture)


@router.patch("/{fixture_id}/status", response_model=FixtureRead)
async def update_fixture_status(
    fixture_id: uuid.UUID,
    status_data: FixtureStatusUpdate,
    session: DbSession,
    _admin: AdminUser,
) -> FixtureRead:
    """Update fixture status and minute (admin only)."""
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    fixture.status = status_data.status
    if status_data.minute is not None:
        fixture.minute = status_data.minute
    fixture.updated_at = utc_now()

    await session.commit()
    await session.refresh(fixture)
    # Same MissingGreenlet guard as update_fixture above.
    await session.refresh(fixture, attribute_names=["score"])
    return fixture_to_read(fixture)


@router.delete("/{fixture_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fixture(
    fixture_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> None:
    """Delete a fixture (admin only)."""
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    await session.delete(fixture)
    await session.commit()
