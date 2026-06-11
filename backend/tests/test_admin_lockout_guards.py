"""Admin-lockout guards (v2.166.0).

`is_active=false` blocks every login path (password, magic link,
OAuth), so these two endpoints are the production-lockout vectors:

* PATCH /admin/users/{id}/active must NEVER deactivate an admin
  account (self or otherwise) — revoke admin first.
* PATCH /admin/users/{id}/admin must never demote the LAST active
  admin — with zero admins nobody can flip go-live or restore rights.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user
from app.main import app
from app.models.user import AuthProvider, User


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_user(
    session: AsyncSession,
    *,
    email: str,
    is_admin: bool = False,
    is_active: bool = True,
) -> User:
    u = User(
        email=email,
        name="T",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=is_active,
        is_admin=is_admin,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _client_as(db_session: AsyncSession, admin: User):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_admin_user] = lambda: admin
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_admin_account_cannot_be_deactivated(db_session: AsyncSession):
    admin = await _make_user(db_session, email="a@example.com", is_admin=True)
    other_admin = await _make_user(db_session, email="b@example.com", is_admin=True)
    async with _client_as(db_session, admin) as ac:
        # Not even another admin — and especially not yourself.
        for target in (admin, other_admin):
            resp = await ac.patch(f"/api/admin/users/{target.id}/active")
            assert resp.status_code == 409, target.email
    app.dependency_overrides.clear()
    await db_session.refresh(admin)
    await db_session.refresh(other_admin)
    assert admin.is_active and other_admin.is_active


@pytest.mark.asyncio
async def test_regular_user_toggle_and_reactivation_still_work(
    db_session: AsyncSession,
):
    admin = await _make_user(db_session, email="a@example.com", is_admin=True)
    pleb = await _make_user(db_session, email="p@example.com")
    inactive_admin = await _make_user(
        db_session, email="ia@example.com", is_admin=True, is_active=False
    )
    async with _client_as(db_session, admin) as ac:
        resp = await ac.patch(f"/api/admin/users/{pleb.id}/active")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False
        # Re-activating an inactive admin is allowed (it's the rescue path).
        resp = await ac.patch(f"/api/admin/users/{inactive_admin.id}/active")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_demoted(db_session: AsyncSession):
    admin = await _make_user(db_session, email="a@example.com", is_admin=True)
    # An INACTIVE admin doesn't count as cover.
    await _make_user(db_session, email="ia@example.com", is_admin=True, is_active=False)
    async with _client_as(db_session, admin) as ac:
        resp = await ac.patch(f"/api/admin/users/{admin.id}/admin")
        assert resp.status_code == 409
    app.dependency_overrides.clear()
    await db_session.refresh(admin)
    assert admin.is_admin is True


@pytest.mark.asyncio
async def test_demoting_one_of_two_admins_is_allowed(db_session: AsyncSession):
    admin = await _make_user(db_session, email="a@example.com", is_admin=True)
    second = await _make_user(db_session, email="b@example.com", is_admin=True)
    async with _client_as(db_session, admin) as ac:
        resp = await ac.patch(f"/api/admin/users/{second.id}/admin")
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is False
        # Promotion of a regular user is unaffected.
        resp = await ac.patch(f"/api/admin/users/{second.id}/admin")
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True
    app.dependency_overrides.clear()
