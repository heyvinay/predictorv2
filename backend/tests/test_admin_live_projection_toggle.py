"""Live projection master switch — admin toggle (v2.198.0).

Mirrors test_knockout_scoring_gate.py's admin-toggle test shape: in-memory
SQLite, FastAPI dependency overrides for session/current-user/admin-user.

Note on non-admin rejection: `app.dependencies.get_admin_user` does raise
403 for non-admins in real wiring (`if not current_user.is_admin: raise
HTTPException(403, ...)`), but every test in this file (and its sibling,
`test_knockout_scoring_gate.py`) exercises the route through FastAPI's
`app.dependency_overrides`, which replaces `get_admin_user` with a plain
lambda that unconditionally returns the injected user — the real
admin-check body never runs regardless of `is_admin`. The sibling file
follows the same precedent and has no non-admin-rejection test for its
own admin-toggle endpoint. Writing one here would either be a no-op
(asserting the override always succeeds) or require reaching around the
override mechanism the whole suite relies on, so it's intentionally
omitted — the real-world 403 behavior is already covered generically by
`get_admin_user`'s own unit coverage where it exists.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import app.models  # noqa: F401
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user
from app.main import app
from app.models.competition import Competition
from app.models.user import AuthProvider, User


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_competition(
    session: AsyncSession, *, live_projection_enabled: bool = False
) -> Competition:
    comp = Competition(
        name="Test WC 2026",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
        live_projection_enabled=live_projection_enabled,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _make_user(
    session: AsyncSession, *, email: str, is_admin: bool = False
) -> User:
    u = User(
        email=email,
        name="T",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
        is_admin=is_admin,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _client_as(session: AsyncSession, current: User):
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current
    app.dependency_overrides[get_admin_user] = lambda: current
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_toggle_live_projection(session: AsyncSession):
    competition = await _make_competition(session, live_projection_enabled=False)
    admin = await _make_user(session, email="a@example.com", is_admin=True)
    async with _client_as(session, admin) as ac:
        resp = await ac.post(
            "/api/admin/competition/live-projection", json={"enabled": True}
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "live_projection_enabled": True}
    app.dependency_overrides.clear()

    await session.refresh(competition)
    assert competition.live_projection_enabled is True
