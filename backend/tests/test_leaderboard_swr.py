"""Stale-while-revalidate leaderboard cache (v2.173.0).

The live-score sync expires the board after every applied score — during
matches that's continuous, and the old hard-invalidation forced a
seconds-long blocking rebuild onto whichever user request came next
(measured 1.5–2.4s on the live pool; it stalled the dashboard's first
paint). The SWR path serves the expired board instantly and rebuilds in
the background on a fresh session.

Engine uses StaticPool so the background refresh's NEW session sees the
same in-memory database as the test's session — without it each aiosqlite
connection gets its own empty :memory: DB.
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
from app.models.user import AuthProvider, User
from app.services import leaderboard as leaderboard_service
from app.services.leaderboard import calculate_leaderboard, expire_cache


@pytest.fixture(autouse=True)
def _clean_leaderboard_state():
    leaderboard_service.invalidate_cache()
    leaderboard_service._refresh_tasks.clear()
    yield
    leaderboard_service.invalidate_cache()
    leaderboard_service._refresh_tasks.clear()
    leaderboard_service._background_session_factory = None


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
        external_id="WC",
        is_active=True,
        phase1_deadline=datetime(2020, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


async def _make_entry(
    db_session: AsyncSession, competition: Competition, *, email: str
) -> PredictionEntry:
    user = User(
        email=email,
        name=email.split("@")[0].title(),
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6]}",
        display_name=f"{user.name}'s Entry",
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
    task = leaderboard_service._refresh_tasks.get("overall")
    assert task is not None, "expected a background refresh to be scheduled"
    await asyncio.wait_for(task, timeout=5)


@pytest.mark.asyncio
async def test_expired_cache_serves_stale_and_revalidates(
    db_session, session_factory, competition
):
    """expire_cache() → next call returns the OLD board instantly, then a
    background rebuild lands and the call after that sees the new state."""
    leaderboard_service._background_session_factory = session_factory

    await _make_entry(db_session, competition, email="alice@example.com")
    first = await calculate_leaderboard(db_session)
    assert len(first.entries) == 1

    # New eligible entry + soft expiry (what score-sync now does).
    await _make_entry(db_session, competition, email="bob@example.com")
    expire_cache()

    stale = await calculate_leaderboard(db_session)
    assert len(stale.entries) == 1, "stale board should be served as-is"

    await _await_background_refresh()

    fresh = await calculate_leaderboard(db_session)
    assert len(fresh.entries) == 2, "background rebuild should have landed"


@pytest.mark.asyncio
async def test_invalidate_cache_still_blocks_for_fresh_data(
    db_session, competition
):
    """Hard invalidation keeps read-your-write semantics (admin + tests)."""
    await _make_entry(db_session, competition, email="alice@example.com")
    first = await calculate_leaderboard(db_session)
    assert len(first.entries) == 1

    await _make_entry(db_session, competition, email="bob@example.com")
    leaderboard_service.invalidate_cache()

    fresh = await calculate_leaderboard(db_session)
    assert len(fresh.entries) == 2, "hard invalidation must rebuild inline"
    assert leaderboard_service._refresh_tasks == {}, "no background task expected"


@pytest.mark.asyncio
async def test_expire_cache_without_cache_is_safe(db_session, competition):
    """expire_cache() before anything is cached is a no-op; the first
    request then takes the normal blocking cold path."""
    expire_cache()
    await _make_entry(db_session, competition, email="alice@example.com")
    board = await calculate_leaderboard(db_session)
    assert len(board.entries) == 1


@pytest.mark.asyncio
async def test_only_one_background_refresh_is_scheduled(
    db_session, session_factory, competition
):
    """Repeated stale hits while a refresh is in flight must not stack
    additional rebuild tasks."""
    leaderboard_service._background_session_factory = session_factory

    await _make_entry(db_session, competition, email="alice@example.com")
    await calculate_leaderboard(db_session)
    expire_cache()

    await calculate_leaderboard(db_session)
    task_one = leaderboard_service._refresh_tasks.get("overall")
    await calculate_leaderboard(db_session)
    task_two = leaderboard_service._refresh_tasks.get("overall")
    assert task_one is task_two, "in-flight refresh must be reused"

    await _await_background_refresh()
