"""HTTP-level tests for the Task F leaderboard visibility rules.

The "blind pool" rule: before the active competition's `phase1_deadline`
passes, a user only sees their own leaderboard rows / breakdowns /
trajectories / climbers. Admins and post-lock viewers see everyone.
Disabled and withdrawn entries are never visible to non-owners.

These tests do not exercise scoring math — they only cover the
visibility/filter behaviour added in Task F. They share the in-memory
SQLite fixture style with `test_entries_api.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models
from app.database import get_session
from app.dependencies import (
    get_admin_user,
    get_current_user,
    get_current_user_optional,
)
from app.main import app
from app.models.competition import Competition
from app.models.entry import (
    EntryStatus,
    PredictionEntry,
    PredictionEntryPhase,
)
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services import leaderboard as leaderboard_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clear_leaderboard_cache():
    """Fresh leaderboard cache per test — calculate_leaderboard is cached."""
    leaderboard_service.invalidate_cache()
    yield
    leaderboard_service.invalidate_cache()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(db_session: AsyncSession) -> Competition:
    """A competition WITHOUT a phase1_deadline — pre-lock state."""
    comp = Competition(
        name="Test World Cup",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


@pytest_asyncio.fixture
async def alice(db_session: AsyncSession) -> User:
    u = User(
        email="alice@example.com",
        name="Alice",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def bob(db_session: AsyncSession) -> User:
    u = User(
        email="bob@example.com",
        name="Bob",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    u = User(
        email="admin@example.com",
        name="Admin",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_admin=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _make_entry(
    session: AsyncSession,
    *,
    user: User,
    competition: Competition,
    display_name: str,
    status: EntryStatus = EntryStatus.SUBMITTED,
) -> PredictionEntry:
    """Create an eligible entry with both phase rows pre-populated.

    Defaults to SUBMITTED so the row shows up on the leaderboard.
    """
    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6].upper()}",
        display_name=display_name,
        entry_number=1,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    for phase in (PredictionPhase.PHASE_1, PredictionPhase.PHASE_2):
        session.add(
            PredictionEntryPhase(entry_id=entry.id, phase=phase, status=status)
        )
    await session.commit()
    await session.refresh(entry)
    return entry


def _set_phase1_locked(competition: Competition, *, locked: bool) -> None:
    """Move phase1_deadline into the past (locked) or future (pre-lock)."""
    if locked:
        competition.phase1_deadline = datetime(2020, 1, 1, tzinfo=timezone.utc)
    else:
        competition.phase1_deadline = datetime(2099, 1, 1, tzinfo=timezone.utc)


def _override(db_session: AsyncSession, *, viewer: User | None, admin: User | None = None):
    """Install dependency overrides.

    Overrides BOTH `get_current_user` (used by `CurrentUser` routes) and
    `get_current_user_optional` (used by `OptionalUser` routes — the
    leaderboard `/` and `/breakdown` use it). Without the optional
    override, OptionalUser routes hit the real auth chain and resolve
    to `None`, which silently swaps Alice/admin for an unauthenticated
    viewer.
    """
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    if viewer is not None:
        app.dependency_overrides[get_current_user] = lambda: viewer
        app.dependency_overrides[get_current_user_optional] = lambda: viewer
    else:
        app.dependency_overrides[get_current_user_optional] = lambda: None
    if admin is not None:
        app.dependency_overrides[get_admin_user] = lambda: admin


# ---------------------------------------------------------------------------
# GET /api/leaderboard/  — entries list visibility
# ---------------------------------------------------------------------------
class TestLeaderboardListVisibility:
    async def test_pre_lock_filters_to_own_rows(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
        bob: User,
    ):
        """Pre-lock, Alice sees only her own row even though Bob has one too."""
        await _make_entry(
            db_session, user=alice, competition=competition, display_name="A1"
        )
        await _make_entry(
            db_session, user=bob, competition=competition, display_name="B1"
        )
        _set_phase1_locked(competition, locked=False)
        db_session.add(competition)
        await db_session.commit()

        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/leaderboard/?refresh=true")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        # Alice's row is present.
        assert len(body["entries"]) >= 1
        # All visible rows belong to Alice — Bob is hidden.
        assert all(row["user_id"] == str(alice.id) for row in body["entries"])
        # total_participants still reflects the true field size.
        assert body["total_participants"] >= 2

    async def test_post_lock_returns_full_field(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
        bob: User,
    ):
        """After the Phase 1 deadline passes, Alice sees Bob's row too."""
        await _make_entry(
            db_session, user=alice, competition=competition, display_name="A1"
        )
        await _make_entry(
            db_session, user=bob, competition=competition, display_name="B1"
        )
        _set_phase1_locked(competition, locked=True)
        db_session.add(competition)
        await db_session.commit()

        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/leaderboard/?refresh=true")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        owners = {row["user_id"] for row in r.json()["entries"]}
        assert str(alice.id) in owners
        assert str(bob.id) in owners

    async def test_admin_sees_everyone_pre_lock(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
        bob: User,
        admin_user: User,
    ):
        """Admins bypass the blind-pool filter."""
        await _make_entry(
            db_session, user=alice, competition=competition, display_name="A1"
        )
        await _make_entry(
            db_session, user=bob, competition=competition, display_name="B1"
        )
        _set_phase1_locked(competition, locked=False)
        db_session.add(competition)
        await db_session.commit()

        _override(db_session, viewer=admin_user, admin=admin_user)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/leaderboard/?refresh=true")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        owners = {row["user_id"] for row in r.json()["entries"]}
        assert {str(alice.id), str(bob.id)} <= owners


# ---------------------------------------------------------------------------
# GET /api/leaderboard/breakdown/{entry_id} — visibility gate
# ---------------------------------------------------------------------------
class TestBreakdownVisibility:
    async def test_non_owner_403_pre_lock(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
        bob: User,
    ):
        entry = await _make_entry(
            db_session, user=alice, competition=competition, display_name="A1"
        )
        _set_phase1_locked(competition, locked=False)
        db_session.add(competition)
        await db_session.commit()

        _override(db_session, viewer=bob)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/leaderboard/breakdown/{entry.id}")
        app.dependency_overrides.clear()
        assert r.status_code == 403

    async def test_non_owner_200_post_lock(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
        bob: User,
    ):
        entry = await _make_entry(
            db_session, user=alice, competition=competition, display_name="A1"
        )
        _set_phase1_locked(competition, locked=True)
        db_session.add(competition)
        await db_session.commit()

        _override(db_session, viewer=bob)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/leaderboard/breakdown/{entry.id}")
        app.dependency_overrides.clear()
        assert r.status_code == 200

    async def test_owner_200_pre_lock(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        entry = await _make_entry(
            db_session, user=alice, competition=competition, display_name="A1"
        )
        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/leaderboard/breakdown/{entry.id}")
        app.dependency_overrides.clear()
        assert r.status_code == 200
