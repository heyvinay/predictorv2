"""Bulk rank-trajectory endpoint (v2.164.0) — GET /api/leaderboard/snapshots.

Powers the V4 leaderboard's Race bump chart: every eligible entry's
snapshot history in one response, each ending in the live current rank.
HTTP-level tests via ASGITransport, mirroring test_leaderboard_admin_gate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.database import get_session
from app.dependencies import get_current_user, get_current_user_optional
from app.main import app
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.leaderboard_snapshot import LeaderboardSnapshot
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


async def _make_competition(
    db_session: AsyncSession, *, locked: bool = True
) -> Competition:
    deadline = (
        datetime(2020, 1, 1, tzinfo=timezone.utc)
        if locked
        else datetime(2099, 1, 1, tzinfo=timezone.utc)
    )
    comp = Competition(
        name="Test World Cup",
        external_id="WC",
        is_active=True,
        phase1_deadline=deadline,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


async def _make_user(db_session: AsyncSession, email: str, **kw) -> User:
    u = User(
        email=email,
        name=email.split("@")[0].title(),
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        **kw,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _make_entry(
    session: AsyncSession, *, user: User, competition: Competition
) -> PredictionEntry:
    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6].upper()}",
        display_name=f"{user.name}'s XI",
        entry_number=1,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    session.add(
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.SUBMITTED,
        )
    )
    await session.commit()
    return entry


def _override(db_session: AsyncSession, *, viewer: User | None):
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


class TestBulkSnapshots:
    async def test_all_entries_with_history_and_live_tip(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        comp = await _make_competition(db_session, locked=True)
        alice = await _make_user(db_session, "alice@example.com")
        bob = await _make_user(db_session, "bob@example.com")
        a = await _make_entry(db_session, user=alice, competition=comp)
        b = await _make_entry(db_session, user=bob, competition=comp)

        today = datetime.now(timezone.utc).date()
        db_session.add_all(
            [
                LeaderboardSnapshot(
                    user_id=alice.id, entry_id=a.id, position=2,
                    total_points=10, captured_date=today - timedelta(days=2),
                ),
                LeaderboardSnapshot(
                    user_id=alice.id, entry_id=a.id, position=1,
                    total_points=20, captured_date=today - timedelta(days=1),
                ),
            ]
        )
        await db_session.commit()

        _override(db_session, viewer=alice)
        r = await client.get("/api/leaderboard/snapshots?days=30")
        assert r.status_code == 200
        data = r.json()
        assert data["days"] == 30
        assert data["total_participants"] == 2
        by_id = {e["entry_id"]: e for e in data["entries"]}
        assert set(by_id) == {str(a.id), str(b.id)}

        a_points = by_id[str(a.id)]["points"]
        # 2 history rows + live tip appended for today.
        assert len(a_points) == 3
        dates = [p["captured_date"] for p in a_points]
        assert dates == sorted(dates)
        assert a_points[-1]["captured_date"] == today.isoformat()

        # Bob has no snapshots — just the live tip.
        assert len(by_id[str(b.id)]["points"]) == 1

        # Names ride along for chart labels.
        assert by_id[str(a.id)]["entry_name"] == "Alice's XI"
        assert by_id[str(a.id)]["user_name"] == "Alice"

    async def test_blind_pool_pre_deadline(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        comp = await _make_competition(db_session, locked=False)
        alice = await _make_user(db_session, "alice@example.com")
        bob = await _make_user(db_session, "bob@example.com")
        a = await _make_entry(db_session, user=alice, competition=comp)
        await _make_entry(db_session, user=bob, competition=comp)

        _override(db_session, viewer=alice)
        r = await client.get("/api/leaderboard/snapshots")
        assert r.status_code == 200
        data = r.json()
        assert [e["entry_id"] for e in data["entries"]] == [str(a.id)]
        # Field size stays honest even when rows are filtered.
        assert data["total_participants"] == 2

    async def test_admin_sees_all_pre_deadline(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        comp = await _make_competition(db_session, locked=False)
        admin = await _make_user(db_session, "admin@example.com", is_admin=True)
        bob = await _make_user(db_session, "bob@example.com")
        await _make_entry(db_session, user=admin, competition=comp)
        await _make_entry(db_session, user=bob, competition=comp)

        _override(db_session, viewer=admin)
        r = await client.get("/api/leaderboard/snapshots")
        assert r.status_code == 200
        assert len(r.json()["entries"]) == 2

    async def test_requires_auth(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        await _make_competition(db_session, locked=True)
        _override(db_session, viewer=None)
        r = await client.get("/api/leaderboard/snapshots")
        assert r.status_code == 401

    async def test_days_validation(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        comp = await _make_competition(db_session, locked=True)
        alice = await _make_user(db_session, "alice@example.com")
        await _make_entry(db_session, user=alice, competition=comp)
        _override(db_session, viewer=alice)
        assert (await client.get("/api/leaderboard/snapshots?days=1")).status_code == 422
        assert (await client.get("/api/leaderboard/snapshots?days=91")).status_code == 422
