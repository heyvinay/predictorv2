"""Tests for cohort-trail service — median rank per cohort over time."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all SQLModel tables
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services.cohort_race import compute_cohort_trail


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _seed_cohorted_pool(session: AsyncSession) -> None:
    """Seed 4 Atlas, 5 JMFA, 2 Guests entries with snapshots over the last 3 days.

    Guests is below the 3-entry threshold and must be suppressed.
    Atlas ranks: [10, 20, 30, 40]  — median = (20+30)/2 = 25.0
    JMFA ranks:  [50, 60, 70, 80, 90] — median = 70.0
    """
    comp = Competition(
        name="t",
        phase1_deadline=utc_now() - timedelta(hours=1),
        is_phase2_active=False,
    )
    session.add(comp)
    await session.flush()

    # (employer, ranks_for_each_entry)
    cohorts = [
        ("atlas",   [10, 20, 30, 40]),
        ("jmfa",    [50, 60, 70, 80, 90]),
        ("neither", [100, 110]),
    ]
    today = date.today()
    entry_number = 0
    for employer, ranks in cohorts:
        for rank in ranks:
            entry_number += 1
            user = User(
                email=f"{employer}-{rank}@test",
                name=f"u-{rank}",
                employer=employer,
                is_admin=False,
                auth_provider=AuthProvider.EMAIL,
            )
            session.add(user)
            await session.flush()

            entry = PredictionEntry(
                user_id=user.id,
                competition_id=comp.id,
                reference=f"T-{uuid.uuid4().hex[:6]}",
                display_name=f"Entry {rank}",
                entry_number=entry_number,
            )
            session.add(entry)
            await session.flush()

            session.add(
                PredictionEntryPhase(
                    entry_id=entry.id,
                    phase=PredictionPhase.PHASE_1,
                    status=EntryStatus.SUBMITTED,
                )
            )

            # Snapshots for last 3 days — same rank each day for simplicity
            for d_offset in range(3):
                session.add(
                    LeaderboardSnapshot(
                        user_id=user.id,
                        entry_id=entry.id,
                        captured_date=today - timedelta(days=2 - d_offset),
                        position=rank,
                        total_points=200 - rank,
                    )
                )

    await session.commit()


async def test_suppresses_cohort_below_3_entries(session: AsyncSession) -> None:
    """Guests cohort has only 2 entries — must be suppressed (< MIN_COHORT_SIZE=3)."""
    await _seed_cohorted_pool(session)
    result = await compute_cohort_trail(session)
    cohort_names = {c.cohort for c in result.cohorts}
    assert "atlas" in cohort_names
    assert "jmfa" in cohort_names
    assert "guests" not in cohort_names  # 2 entries → below threshold


async def test_median_math_even_count(session: AsyncSession) -> None:
    """Atlas: 4 entries at ranks [10, 20, 30, 40] — median = (20+30)/2 = 25.0."""
    await _seed_cohorted_pool(session)
    result = await compute_cohort_trail(session)
    atlas = next(c for c in result.cohorts if c.cohort == "atlas")
    for p in atlas.points:
        assert p.median_rank == pytest.approx(25.0)
    assert atlas.current_median_rank == pytest.approx(25.0)


async def test_median_math_odd_count(session: AsyncSession) -> None:
    """JMFA: 5 entries at ranks [50, 60, 70, 80, 90] — median = 70.0."""
    await _seed_cohorted_pool(session)
    result = await compute_cohort_trail(session)
    jmfa = next(c for c in result.cohorts if c.cohort == "jmfa")
    for p in jmfa.points:
        assert p.median_rank == pytest.approx(70.0)


async def test_generated_at_aware_utc(session: AsyncSession) -> None:
    """generated_at must carry tzinfo (aware-UTC per CLAUDE.md rule)."""
    await _seed_cohorted_pool(session)
    result = await compute_cohort_trail(session)
    assert result.generated_at.tzinfo is not None
