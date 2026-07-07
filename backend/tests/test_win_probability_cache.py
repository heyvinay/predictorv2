"""Stale-while-revalidate cache for the win-probability engine.

Mirrors backend/tests/test_leaderboard_swr.py's pattern exactly — same
StaticPool trick so a background refresh's new session sees the same
in-memory DB as the test's session, same _await_background_refresh
helper, same fast/stale-while-revalidate/cold/invalidate coverage.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.models.user import User
from app.services import win_probability as win_probability_service
from app.services.win_probability import expire_win_probability_cache, get_win_probability


@pytest.fixture(autouse=True)
def _clean_win_probability_state():
    win_probability_service.invalidate_win_probability_cache()
    win_probability_service._refresh_tasks.clear()
    yield
    win_probability_service.invalidate_win_probability_cache()
    win_probability_service._refresh_tasks.clear()
    win_probability_service._background_session_factory = None


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncSession:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(db_session: AsyncSession) -> Competition:
    comp = Competition(
        name="Test World Cup",
        is_active=True,
        knockout_scoring_enabled=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


async def _make_entry(
    db_session: AsyncSession, competition: Competition, *, email: str
) -> PredictionEntry:
    user = User(email=email)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6]}",
        display_name=f"{email}'s Entry",
        entry_number=1,
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    db_session.add(
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.SUBMITTED,
        )
    )
    await db_session.commit()
    return entry


async def _await_background_refresh() -> None:
    task = win_probability_service._refresh_tasks.get(win_probability_service._CACHE_KEY)
    assert task is not None, "expected a background refresh to be scheduled"
    await asyncio.wait_for(task, timeout=5)


@pytest.mark.asyncio
async def test_fresh_cache_hit_returns_same_result_without_recompute(db_session, competition):
    await _make_entry(db_session, competition, email="alice@example.com")
    first = await get_win_probability(db_session)
    assert len(first.uniform.entries) == 1

    await _make_entry(db_session, competition, email="bob@example.com")
    second = await get_win_probability(db_session)

    assert len(second.uniform.entries) == 1, "still-fresh cache must not recompute"


@pytest.mark.asyncio
async def test_expired_cache_serves_stale_and_revalidates(db_session, session_factory, competition):
    win_probability_service._background_session_factory = session_factory

    await _make_entry(db_session, competition, email="alice@example.com")
    first = await get_win_probability(db_session)
    assert len(first.uniform.entries) == 1

    await _make_entry(db_session, competition, email="bob@example.com")
    expire_win_probability_cache()

    stale = await get_win_probability(db_session)
    assert len(stale.uniform.entries) == 1, "stale board should be served as-is"

    await _await_background_refresh()

    fresh = await get_win_probability(db_session)
    assert len(fresh.uniform.entries) == 2, "background rebuild should have landed"


@pytest.mark.asyncio
async def test_invalidate_cache_blocks_for_fresh_data(db_session, competition):
    await _make_entry(db_session, competition, email="alice@example.com")
    first = await get_win_probability(db_session)
    assert len(first.uniform.entries) == 1

    await _make_entry(db_session, competition, email="bob@example.com")
    win_probability_service.invalidate_win_probability_cache()

    fresh = await get_win_probability(db_session)
    assert len(fresh.uniform.entries) == 2, "hard invalidation must rebuild inline"
    assert win_probability_service._refresh_tasks == {}, "no background task expected"


@pytest.mark.asyncio
async def test_only_one_background_refresh_is_scheduled(db_session, session_factory, competition):
    win_probability_service._background_session_factory = session_factory

    await _make_entry(db_session, competition, email="alice@example.com")
    await get_win_probability(db_session)
    expire_win_probability_cache()

    await get_win_probability(db_session)
    task_one = win_probability_service._refresh_tasks.get(win_probability_service._CACHE_KEY)
    await get_win_probability(db_session)
    task_two = win_probability_service._refresh_tasks.get(win_probability_service._CACHE_KEY)
    assert task_one is task_two, "in-flight refresh must be reused"

    await _await_background_refresh()
