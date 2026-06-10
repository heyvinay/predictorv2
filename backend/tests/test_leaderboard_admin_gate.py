"""Admin gating of leaderboard cache controls (v2.161.0).

`POST /api/leaderboard/invalidate` requires an admin; `?refresh=true` on
`GET /api/leaderboard/` is honoured only for admins (silently ignored for
everyone else — the 30s TTL keeps standings fresh, and an open refresh
would let any client stampede the rebuild).

HTTP-level tests via ASGITransport, mirroring test_leaderboard_visibility.
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
    get_current_user,
    get_current_user_optional,
)
from app.main import app
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services import leaderboard as leaderboard_service


@pytest.fixture(autouse=True)
def _clear_leaderboard_cache():
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
    comp = Competition(
        name="Test World Cup",
        external_id="WC",
        is_active=True,
        # Locked (deadline passed) so the blind-pool filter doesn't hide
        # rows — these tests are about cache controls, not visibility.
        phase1_deadline=datetime(2020, 1, 1, tzinfo=timezone.utc),
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
    entry_number: int = 1,
) -> PredictionEntry:
    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6].upper()}",
        display_name="Entry",
        entry_number=entry_number,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    for phase in (PredictionPhase.PHASE_1, PredictionPhase.PHASE_2):
        session.add(
            PredictionEntryPhase(
                entry_id=entry.id, phase=phase, status=EntryStatus.SUBMITTED
            )
        )
    await session.commit()
    return entry


def _override(db_session: AsyncSession, *, viewer: User | None):
    """get_admin_user chains through get_current_user, so overriding
    get_current_user is enough to emulate admin/non-admin viewers; the
    real 403 branch in get_admin_user still runs."""
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    if viewer is not None:
        app.dependency_overrides[get_current_user] = lambda: viewer
        app.dependency_overrides[get_current_user_optional] = lambda: viewer
    else:
        app.dependency_overrides[get_current_user_optional] = lambda: None


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /invalidate
# ---------------------------------------------------------------------------
class TestInvalidateGate:
    async def test_unauthenticated_gets_401(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        _override(db_session, viewer=None)
        r = await client.post("/api/leaderboard/invalidate")
        assert r.status_code == 401

    async def test_non_admin_gets_403(
        self, db_session: AsyncSession, alice: User, client: AsyncClient
    ):
        _override(db_session, viewer=alice)
        r = await client.post("/api/leaderboard/invalidate")
        assert r.status_code == 403

    async def test_admin_gets_200(
        self, db_session: AsyncSession, admin_user: User, client: AsyncClient
    ):
        _override(db_session, viewer=admin_user)
        r = await client.post("/api/leaderboard/invalidate")
        assert r.status_code == 200
        assert r.json() == {"status": "cache invalidated"}


# ---------------------------------------------------------------------------
# GET /?refresh=true
# ---------------------------------------------------------------------------
class TestRefreshGate:
    async def test_refresh_ignored_for_non_admin(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
        client: AsyncClient,
    ):
        """Warm the cache, add a new entry, then hit ?refresh=true as a
        regular user — the stale cache (without the new entry) is served."""
        await _make_entry(db_session, user=alice, competition=competition)
        _override(db_session, viewer=alice)

        warm = await client.get("/api/leaderboard/")
        assert warm.status_code == 200
        assert warm.json()["total_participants"] == 1

        await _make_entry(
            db_session, user=alice, competition=competition, entry_number=2
        )

        r = await client.get("/api/leaderboard/?refresh=true")
        assert r.status_code == 200
        # Refresh was ignored → still the cached single-entry standings.
        assert r.json()["total_participants"] == 1

    async def test_refresh_honoured_for_admin(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
        admin_user: User,
        client: AsyncClient,
    ):
        await _make_entry(db_session, user=alice, competition=competition)
        _override(db_session, viewer=admin_user)

        warm = await client.get("/api/leaderboard/")
        assert warm.status_code == 200
        assert warm.json()["total_participants"] == 1

        await _make_entry(
            db_session, user=alice, competition=competition, entry_number=2
        )

        r = await client.get("/api/leaderboard/?refresh=true")
        assert r.status_code == 200
        # Admin refresh forces the rebuild → new entry visible.
        assert r.json()["total_participants"] == 2
