"""Tests for v2.176.0 Site Pulse assembler.

Pins the partial-failure contract: if PostHog helpers return empty
(silent contract), the audit-backed Recent Logins widget still loads.
The endpoint never raises on a PostHog outage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register every model
from app.models.audit import AuditEvent
from app.models.entry import ActorRole
from app.models.user import AuthProvider, User
from app.services.pulse import get_site_pulse


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.mark.asyncio
async def test_partial_posthog_failure_still_loads_recent_logins(
    db_session: AsyncSession,
):
    """PostHog widgets return []; audit-backed Recent Logins still loads."""
    # Seed: one user + one auth.login_succeeded event for them.
    u = User(
        email="logger@test.com",
        name="Recent Logger",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
    )
    db_session.add(u)
    await db_session.flush()

    db_session.add(
        AuditEvent(
            event_type="auth.login_succeeded",
            actor_user_id=u.id,
            actor_role=ActorRole.USER,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
    )
    await db_session.commit()

    empty = AsyncMock(return_value=[])
    with patch("app.services.pulse.posthog_read.get_dau_sparkline_14d", empty), \
         patch("app.services.pulse.posthog_read.get_top_pages_7d", empty), \
         patch("app.services.pulse.posthog_read.get_top_events_7d", empty):
        pulse = await get_site_pulse(db_session)

    assert pulse.dau_sparkline == []
    assert pulse.top_pages == []
    assert pulse.top_events == []
    assert len(pulse.recent_logins) == 1
    assert pulse.recent_logins[0].name == "Recent Logger"


@pytest.mark.asyncio
async def test_recent_logins_ordered_desc_by_timestamp(
    db_session: AsyncSession,
):
    """Most recent login first."""
    u = User(
        email="multi@test.com",
        name="Multi Login",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
    )
    db_session.add(u)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    for offset_min in (60, 30, 5):
        db_session.add(
            AuditEvent(
                event_type="auth.login_succeeded",
                actor_user_id=u.id,
                actor_role=ActorRole.USER,
                created_at=now - timedelta(minutes=offset_min),
            )
        )
    await db_session.commit()

    empty = AsyncMock(return_value=[])
    with patch("app.services.pulse.posthog_read.get_dau_sparkline_14d", empty), \
         patch("app.services.pulse.posthog_read.get_top_pages_7d", empty), \
         patch("app.services.pulse.posthog_read.get_top_events_7d", empty):
        pulse = await get_site_pulse(db_session)

    assert len(pulse.recent_logins) == 3
    # Newest first (5 min ago first, then 30, then 60).
    times = [login.login_at for login in pulse.recent_logins]
    assert times == sorted(times, reverse=True)
