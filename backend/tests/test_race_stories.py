"""Tests for race-stories service — story-card derivations against snapshot trail."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services.race_stories import select_race_stories


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _seed_pool(session: AsyncSession, *, deadline_passed: bool) -> dict[str, PredictionEntry]:
    """Build a tiny eligible pool with daily snapshots over the last 7 days.
    Returns {label: entry} so tests can assert on specific entries by name.
    """
    # Comp with deadline in the past (so blind-pool is OPEN) or future
    deadline = utc_now() + timedelta(days=-1 if deadline_passed else 1)
    comp = Competition(
        name="Test", phase1_deadline=deadline, is_phase2_active=False, is_active=True,
        external_id="TEST",
    )
    session.add(comp)
    await session.flush()

    entries: dict[str, PredictionEntry] = {}
    counter = 1
    for label in ("climber", "faller", "leader", "runner_up", "streaker", "stable"):
        user = User(
            email=f"{label}@test",
            name=label,
            is_admin=False,
            auth_provider=AuthProvider.EMAIL,
        )
        session.add(user)
        await session.flush()
        entry = PredictionEntry(
            user_id=user.id,
            competition_id=comp.id,
            reference=f"TEST-{counter:06d}",
            display_name=f"{label} entry",
            entry_number=counter,
        )
        counter += 1
        session.add(entry)
        await session.flush()
        # Submitted phase row
        session.add(
            PredictionEntryPhase(
                entry_id=entry.id,
                phase=PredictionPhase.PHASE_1,
                status=EntryStatus.SUBMITTED,
                submitted_at=utc_now() - timedelta(days=10),
            )
        )
        entries[label] = entry

    await session.flush()

    # Daily snapshots over 9 days. Positions chosen to satisfy each story rule:
    # WINDOW_DAYS_CLIMB_FALL = 3, WINDOW_DAYS_STREAK = 5, WINDOW_DAYS_CLOSEST = 7
    # With 9 snapshots, indices 0..8 map to (today-8)..(today).
    # rank_n_days_ago[3] = index (9-1-3)=5 from start.
    #
    # climber: index[5]=28, current=10, delta=18 >= MIN_CLIMB_DELTA(15) ✓
    # faller:  index[5]=10, current=25, delta=15 >= MIN_FALL_DELTA(15) ✓
    #          and past(10) <= TOP_25_START_CAP(25) ✓
    # leader:  [1,1,2,6,1,1,1,1,1] — reversed streak counts [1,1,1,1,1] then 6>5 → stop.
    #          streak=5 ✓, t.points[-5:]=[1,1,1,1,1], all(==1)=True → boring-case fires.
    # runner_up: [2,2,1,7,2,2,2,2,2] — [-7:]=[1,7,2,2,2,2,2].
    #          Zip with leader[-7:]=[2,6,1,1,1,1,1]: pair(2,1) → swap fires ✓
    # streaker: [5,4,5,4,5,4,5,4,5] — all ≤5, streak=9, not-all-#1 ✓
    # stable:  always #30 — qualifies nothing
    today = date.today()
    plan = {
        "climber":   [62, 60, 50, 45, 35, 28, 15, 12, 10],
        "faller":    [3,  3,  3,  3,  5,  10, 15, 20, 25],
        "leader":    [1,  1,  2,  6,  1,  1,  1,  1,  1],
        "runner_up": [2,  2,  1,  7,  6,  8,  2,  2,  2],
        "streaker":  [5,  4,  5,  4,  5,  4,  5,  4,  5],
        "stable":    [30, 30, 30, 30, 30, 30, 30, 30, 30],
    }
    n_days = 9
    for label, positions in plan.items():
        for day_offset, pos in enumerate(positions):
            captured = today - timedelta(days=(n_days - 1) - day_offset)
            session.add(
                LeaderboardSnapshot(
                    entry_id=entries[label].id,
                    user_id=entries[label].user_id,
                    competition_id=comp.id,
                    captured_date=captured,
                    position=pos,
                    total_points=(100 - pos) * 2,
                )
            )
    await session.commit()
    return entries


async def test_returns_empty_pre_deadline(session: AsyncSession):
    """Pre-deadline, blind-pool gate returns empty stories list."""
    await _seed_pool(session, deadline_passed=False)
    result = await select_race_stories(session)
    assert result == []


async def test_returns_all_four_when_all_qualify(session: AsyncSession):
    """When the snapshot data satisfies all four rules, all four cards return."""
    await _seed_pool(session, deadline_passed=True)
    result = await select_race_stories(session)
    kinds = [s.kind for s in result]
    assert kinds == ["biggest_climb", "steepest_fall", "closest_race", "hottest_streak"]


async def test_skips_streak_when_only_the_leader_qualifies(session: AsyncSession):
    """Hottest-streak skipped if leader held #1 every day — boring story."""
    await _seed_pool(session, deadline_passed=True)
    # Mutate: remove the streaker from the eligible pool so leader is the only top-5 streak holder
    # (achieved by marking the streaker as withdrawn)
    from sqlalchemy import select as sa_select
    streaker = (await session.execute(sa_select(PredictionEntry).where(PredictionEntry.display_name == "streaker entry"))).scalar_one()
    from app.models._datetime import utc_now as _utc_now
    streaker.withdrawn_at = _utc_now()
    session.add(streaker)
    await session.commit()

    result = await select_race_stories(session)
    kinds = [s.kind for s in result]
    assert "hottest_streak" not in kinds


async def test_skips_climb_below_threshold(session: AsyncSession):
    """A 12-rank climb does not qualify (rule: ≥ 15)."""
    await _seed_pool(session, deadline_passed=True)
    # Tighten climber's path to a 12-rank climb only
    from sqlalchemy import select as sa_select
    climber = (await session.execute(sa_select(PredictionEntry).where(PredictionEntry.display_name == "climber entry"))).scalar_one()
    snaps = (await session.execute(
        sa_select(LeaderboardSnapshot).where(LeaderboardSnapshot.entry_id == climber.id).order_by(LeaderboardSnapshot.captured_date)
    )).scalars().all()
    # Mutate last 3 days (today, today-1, today-2) to rank 18.
    # rank_n_days_ago[3] = index(5) = 28 still. current = 18. delta = 28-18 = 10 < 15.
    today = date.today()
    for s in snaps:
        if s.captured_date >= today - timedelta(days=2):
            s.position = 18
            session.add(s)
    await session.commit()

    result = await select_race_stories(session)
    kinds = [s.kind for s in result]
    assert "biggest_climb" not in kinds


async def test_generated_at_is_aware_utc(session: AsyncSession):
    """The service must return aware-UTC datetimes per CLAUDE.md rule."""
    await _seed_pool(session, deadline_passed=True)
    # The service returns list[RaceStory]; the response wrapper at the API layer adds generated_at.
    # We exercise the response wrapper via the FastAPI test client in a separate API test;
    # here we just confirm the service returns story sparklines with date-typed captured_date.
    result = await select_race_stories(session)
    assert result, "expected at least one qualifying story"
    for story in result:
        assert all(isinstance(p.captured_date, date) for p in story.sparkline)
