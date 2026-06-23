"""Tests for dashboard-stats service — daily MVPs, personal trail, pool distribution.

Project-truth model names (adapted from plan):
- PredictionEntry.display_name (NOT entry_name), .is_disabled, .withdrawn_at
- PredictionEntryPhase.status = EntryStatus.SUBMITTED
- LeaderboardSnapshot.position (NOT rank); no competition_id on snapshot
- Uses session.execute(...) not .exec() (raw SQLAlchemy convention).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — registers all models
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services.dashboard_stats import compute_daily_mvps


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared DB fixture (aiosqlite in-memory — same pattern as test_champion_survival)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_basic_pool(
    session: AsyncSession, *, deadline_passed: bool = True
):
    """Seed 5 eligible entries with daily snapshots over the last 6 days."""
    deadline = (
        utc_now() - timedelta(hours=1)
        if deadline_passed
        else utc_now() + timedelta(days=1)
    )
    comp = Competition(
        name="t",
        external_id="WC",
        is_active=True,
        phase1_deadline=deadline,
        is_phase2_active=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.flush()

    entries: dict[str, PredictionEntry] = {}
    for idx, label in enumerate(("a", "b", "c", "d", "e")):
        user = User(
            email=f"{label}@t",
            name=label.upper(),
            is_admin=False,
            password_hash="x",
            auth_provider=AuthProvider.EMAIL,
        )
        session.add(user)
        await session.flush()
        entry = PredictionEntry(
            user_id=user.id,
            competition_id=comp.id,
            reference=f"WC26-{uuid.uuid4().hex[:6]}",
            display_name=f"{label}-entry",
            entry_number=1,
            is_disabled=False,
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
        entries[label] = entry

    # Daily snapshots, 6 days of history. Points go up over time.
    # On Day 5 (today), entry A scored +20 (most), so A is today's MVP.
    today = date.today()
    plan = {
        "a": [100, 105, 110, 120, 130, 150],  # +5,+5,+10,+10,+20 (today MVP)
        "b": [100, 110, 120, 125, 135, 140],
        "c": [100, 105, 115, 130, 140, 145],
        "d": [100, 108, 113, 121, 130, 135],
        "e": [100, 102, 105, 110, 115, 122],
    }
    for label, points_path in plan.items():
        for d_offset, pts in enumerate(points_path):
            session.add(
                LeaderboardSnapshot(
                    entry_id=entries[label].id,
                    user_id=entries[label].user_id,
                    captured_date=today - timedelta(days=5 - d_offset),
                    position=1,
                    total_points=pts,
                )
            )
    await session.commit()
    return entries, comp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_daily_mvps_returns_empty_pre_deadline(session: AsyncSession):
    await _seed_basic_pool(session, deadline_passed=False)
    result = await compute_daily_mvps(session)
    assert result == []


async def test_daily_mvps_picks_top_day_scorer(session: AsyncSession):
    entries, _comp = await _seed_basic_pool(session)
    result = await compute_daily_mvps(session)
    # Today's MVP (most-recent-first): entry A with +20
    assert result, "Expected at least one MVP"
    today_mvp = result[0]
    assert today_mvp.subject_entry_id == str(entries["a"].id)
    assert today_mvp.day_points == 20


async def test_daily_mvps_caps_at_5(session: AsyncSession):
    await _seed_basic_pool(session)
    result = await compute_daily_mvps(session)
    assert len(result) <= 5


async def test_daily_mvps_tie_break_lower_rank_wins(session: AsyncSession):
    """When two entries score the same day-points, the lower current rank wins."""
    comp = Competition(
        name="t",
        external_id="WC",
        is_active=True,
        phase1_deadline=utc_now() - timedelta(hours=1),
        is_phase2_active=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.flush()
    today = date.today()
    for label in ("hi", "lo"):
        user = User(
            email=f"{label}@t",
            name=label,
            is_admin=False,
            password_hash="x",
            auth_provider=AuthProvider.EMAIL,
        )
        session.add(user)
        await session.flush()
        entry = PredictionEntry(
            user_id=user.id,
            competition_id=comp.id,
            reference=f"WC26-{uuid.uuid4().hex[:6]}",
            display_name=label,
            entry_number=1,
            is_disabled=False,
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
        # Both scored exactly +10 today
        session.add(
            LeaderboardSnapshot(
                entry_id=entry.id,
                user_id=user.id,
                captured_date=today - timedelta(days=1),
                position=10 if label == "lo" else 5,
                total_points=90,
            )
        )
        session.add(
            LeaderboardSnapshot(
                entry_id=entry.id,
                user_id=user.id,
                captured_date=today,
                position=10 if label == "lo" else 5,
                total_points=100,
            )
        )
    await session.commit()

    result = await compute_daily_mvps(session)
    # "hi" is at rank 5 (lower number = better) so should win the tie
    assert result, "Expected at least one MVP"
    assert result[0].user_name == "hi"


async def test_daily_mvps_captured_date_is_date(session: AsyncSession):
    await _seed_basic_pool(session)
    result = await compute_daily_mvps(session)
    for mvp in result:
        assert isinstance(mvp.captured_date, date)
