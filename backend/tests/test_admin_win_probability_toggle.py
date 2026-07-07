"""Win-probability master switch — admin toggle.

Mirrors test_admin_live_projection_toggle.py's shape exactly (same
in-memory SQLite + FastAPI dependency-override pattern, same note on why
there's no non-admin-rejection test — get_admin_user's override bypasses
the real 403 check in every test in this file's sibling too).
"""

from __future__ import annotations

from datetime import datetime, timezone

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
    session: AsyncSession, *, win_probability_enabled: bool = False
) -> Competition:
    comp = Competition(
        name="Test WC 2026",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
        win_probability_enabled=win_probability_enabled,
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
async def test_toggle_win_probability(session: AsyncSession):
    competition = await _make_competition(session, win_probability_enabled=False)
    admin = await _make_user(session, email="a@example.com", is_admin=True)
    async with _client_as(session, admin) as ac:
        resp = await ac.post(
            "/api/admin/competition/win-probability", json={"enabled": True}
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "win_probability_enabled": True}
    app.dependency_overrides.clear()

    await session.refresh(competition)
    assert competition.win_probability_enabled is True


@pytest.mark.asyncio
async def test_toggle_win_probability_idempotent_no_duplicate_audit(session: AsyncSession):
    """Flipping to the same value it's already at must not record an
    audit event — same idempotence contract as knockout-scoring/live-
    projection toggles."""
    from sqlalchemy import select

    from app.models.audit import AuditEvent

    competition = await _make_competition(session, win_probability_enabled=True)
    admin = await _make_user(session, email="a@example.com", is_admin=True)
    async with _client_as(session, admin) as ac:
        resp = await ac.post(
            "/api/admin/competition/win-probability", json={"enabled": True}
        )
        assert resp.status_code == 200
    app.dependency_overrides.clear()

    audit_rows = (
        await session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "competition.win_probability_toggled"
            )
        )
    ).scalars().all()
    assert audit_rows == []
