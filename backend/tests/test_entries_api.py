"""HTTP-level tests for the entries API.

Service-level tests in `test_entries_service.py` cover the state machine
and business rules. These tests cover the HTTP boundary:
- auth enforcement (401 without token, 403 cross-user)
- request body parsing
- response serialization
- exception → status-code translation

Uses FastAPI's `dependency_overrides` to bypass auth and substitute an
in-memory SQLite session, mirroring the project's existing test pattern.
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

import app.models  # noqa: F401  — ensure all models are registered
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user
from app.main import app
from app.models.competition import Competition
from app.models.user import AuthProvider, User


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Fresh in-memory SQLite, schema created from SQLModel.metadata."""
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


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, alice: User):
    """Test client with `alice` injected as the authenticated user.

    Use `client_as(...)` to switch users within a test.
    """
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[get_admin_user] = lambda: alice  # default; per-test overrides may swap
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth — 401 without token
# ---------------------------------------------------------------------------
class TestAuth:
    async def test_unauthenticated_list_returns_401(
        self, db_session: AsyncSession, competition: Competition
    ):
        """No `get_current_user` override → real auth chain runs → 401."""
        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/entries")
        app.dependency_overrides.clear()
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Happy-path: create + list + get
# ---------------------------------------------------------------------------
class TestEntriesHappyPath:
    async def test_create_returns_201_and_entry(
        self, client: AsyncClient, competition: Competition
    ):
        response = await client.post(
            "/api/entries",
            json={"display_name": "My First Picks"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["display_name"] == "My First Picks"
        assert body["entry_number"] == 1
        assert body["reference"].startswith("WC26-")
        # Both phase rows present in the response.
        assert len(body["phases"]) == 2

    async def test_list_returns_created_entries(
        self, client: AsyncClient, competition: Competition
    ):
        await client.post("/api/entries", json={"display_name": "A"})
        await client.post("/api/entries", json={"display_name": "B"})
        response = await client.get("/api/entries")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        names = {e["display_name"] for e in body}
        assert names == {"A", "B"}


# ---------------------------------------------------------------------------
# Cross-user access — 403 even with another auth'd user
# ---------------------------------------------------------------------------
class TestCrossUserAccess:
    async def test_other_user_cannot_get_alices_entry(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
        bob: User,
    ):
        async def override_session():
            yield db_session

        # First create an entry as Alice via the API.
        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: alice
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/entries", json={"display_name": "Alice's"})
            entry_id = r.json()["id"]

        # Switch to Bob; access denied.
        app.dependency_overrides[get_current_user] = lambda: bob
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/entries/{entry_id}")
        app.dependency_overrides.clear()
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Admin endpoints — read settings, list entries
# ---------------------------------------------------------------------------
class TestAdminEndpoints:
    async def test_admin_can_read_entry_settings(
        self,
        db_session: AsyncSession,
        competition: Competition,
        admin_user: User,
    ):
        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_admin_user] = lambda: admin_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/admin/competition/entry-settings")
        app.dependency_overrides.clear()
        assert response.status_code == 200
        body = response.json()
        assert body["max_entries_per_user"] == 5
        assert body["payment_mode"] == "per_entry"

    async def test_admin_can_update_settings(
        self,
        db_session: AsyncSession,
        competition: Competition,
        admin_user: User,
    ):
        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_admin_user] = lambda: admin_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.patch(
                "/api/admin/competition/entry-settings",
                json={"max_entries_per_user": 3},
            )
        app.dependency_overrides.clear()
        assert response.status_code == 200
        assert response.json()["max_entries_per_user"] == 3


# ---------------------------------------------------------------------------
# Limit error → 409
# ---------------------------------------------------------------------------
class TestLimitError:
    async def test_exceeding_limit_returns_409(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        competition.max_entries_per_user = 1
        await db_session.commit()

        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: alice
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.post("/api/entries", json={})
            assert r1.status_code == 201
            r2 = await ac.post("/api/entries", json={})
        app.dependency_overrides.clear()
        assert r2.status_code == 409
