"""Tests for the v2.166.0 deadline close-out plumbing.

Pins:
* /competition/phase-status exposes post_deadline_live (default False).
* POST /admin/competition/go-live flips the flag, writes one audit
  event, and is admin-gated.
* Door policy post-deadline: /auth/register refuses, request-magic-link
  silently skips creating unknown accounts (no enumeration leak),
  create_entry raises EntryStateError.
* Pre-deadline everything still works.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user
from app.main import app
from app.models._datetime import utc_now
from app.models.audit import AuditEvent
from app.models.competition import Competition
from app.models.user import AuthProvider, User
from app.services.entries import EntryStateError, create_entry


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_competition(
    session: AsyncSession, *, deadline: datetime
) -> Competition:
    comp = Competition(
        name="Test WC",
        external_id="WC",
        is_active=True,
        phase1_deadline=deadline,
        max_entries_per_user=5,
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
        name="Test User",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
        is_admin=is_admin,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _client_for(db_session: AsyncSession, user: User | None, *, admin: bool):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
        if admin:
            app.dependency_overrides[get_admin_user] = lambda: user
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _past() -> datetime:
    return utc_now() - timedelta(hours=2)


def _future() -> datetime:
    return utc_now() + timedelta(days=1)


# ---------------------------------------------------------------------------
# phase-status + go-live
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_phase_status_exposes_release_flag(db_session: AsyncSession):
    await _make_competition(db_session, deadline=_past())
    user = await _make_user(db_session, email="u@example.com")
    async with _client_for(db_session, user, admin=False) as ac:
        resp = await ac.get("/api/competition/phase-status")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["phase1_locked"] is True
    assert body["post_deadline_live"] is False


@pytest.mark.asyncio
async def test_go_live_flips_flag_and_audits(db_session: AsyncSession):
    comp = await _make_competition(db_session, deadline=_past())
    admin = await _make_user(db_session, email="a@example.com", is_admin=True)
    async with _client_for(db_session, admin, admin=True) as ac:
        resp = await ac.post("/api/admin/competition/go-live", json={"live": True})
        assert resp.status_code == 200
        assert resp.json()["post_deadline_live"] is True
        # Toggling to the same value again writes no second audit row.
        resp2 = await ac.post("/api/admin/competition/go-live", json={"live": True})
        assert resp2.status_code == 200
    app.dependency_overrides.clear()

    await db_session.refresh(comp)
    assert comp.post_deadline_live is True
    events = (
        (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "competition.post_deadline_live_toggled"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].event_metadata == {"from": False, "to": True}


@pytest.mark.asyncio
async def test_go_live_requires_admin(db_session: AsyncSession):
    await _make_competition(db_session, deadline=_past())
    user = await _make_user(db_session, email="pleb@example.com")
    async with _client_for(db_session, user, admin=False) as ac:
        resp = await ac.post("/api/admin/competition/go-live", json={"live": True})
    app.dependency_overrides.clear()
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Door policy — signups
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_register_refused_post_deadline(db_session: AsyncSession):
    await _make_competition(db_session, deadline=_past())
    async with _client_for(db_session, None, admin=False) as ac:
        resp = await ac.post(
            "/api/auth/register",
            json={"email": "late@example.com", "name": "Late", "password": "hunter22"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403
    assert "closed" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_allowed_pre_deadline(db_session: AsyncSession):
    await _make_competition(db_session, deadline=_future())
    async with _client_for(db_session, None, admin=False) as ac:
        resp = await ac.post(
            "/api/auth/register",
            json={"email": "ontime@example.com", "name": "On Time", "password": "hunter22"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_magic_link_skips_unknown_email_post_deadline(
    db_session: AsyncSession,
):
    await _make_competition(db_session, deadline=_past())
    async with _client_for(db_session, None, admin=False) as ac:
        resp = await ac.post(
            "/api/auth/request-magic-link",
            json={"email": "stranger@example.com"},
        )
    app.dependency_overrides.clear()
    # Same generic message (no enumeration leak), but no account created.
    assert resp.status_code == 200
    created = (
        (
            await db_session.execute(
                select(User).where(User.email == "stranger@example.com")
            )
        )
        .scalars()
        .all()
    )
    assert created == []


@pytest.mark.asyncio
async def test_magic_link_still_works_for_existing_user_post_deadline(
    db_session: AsyncSession,
):
    await _make_competition(db_session, deadline=_past())
    await _make_user(db_session, email="veteran@example.com")
    async with _client_for(db_session, None, admin=False) as ac:
        resp = await ac.post(
            "/api/auth/request-magic-link",
            json={"email": "veteran@example.com"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Door policy — entry creation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_entry_refused_post_deadline(db_session: AsyncSession):
    comp = await _make_competition(db_session, deadline=_past())
    user = await _make_user(db_session, email="u2@example.com")
    with pytest.raises(EntryStateError):
        await create_entry(db_session, user=user, competition=comp)


@pytest.mark.asyncio
async def test_create_entry_allowed_pre_deadline(db_session: AsyncSession):
    comp = await _make_competition(db_session, deadline=_future())
    user = await _make_user(db_session, email="u3@example.com")
    entry = await create_entry(db_session, user=user, competition=comp)
    assert entry.id is not None
