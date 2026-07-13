"""Tests for audit.get_login_counts_since (v2.212.0, Usage & Adoption
dashboard's Power-users table "Logins" column).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register every model
from app.models.audit import AuditEvent
from app.models.entry import ActorRole
from app.models.user import AuthProvider, User
from app.services.audit import get_login_counts_since

NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=30)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_user(s: AsyncSession, email: str) -> User:
    u = User(email=email, name=email, auth_provider=AuthProvider.EMAIL, is_active=True)
    s.add(u)
    await s.flush()
    return u


async def _login(s: AsyncSession, user_id, when: datetime) -> None:
    s.add(
        AuditEvent(
            event_type="auth.login_succeeded",
            actor_user_id=user_id,
            actor_role=ActorRole.USER,
            created_at=when,
        )
    )


@pytest.mark.asyncio
async def test_counts_logins_since_cutoff(db_session: AsyncSession):
    alice = await _make_user(db_session, "alice@test.com")
    bob = await _make_user(db_session, "bob@test.com")

    await _login(db_session, alice.id, SINCE + timedelta(days=1))
    await _login(db_session, alice.id, SINCE + timedelta(days=2))
    await _login(db_session, alice.id, SINCE - timedelta(days=1))  # before cutoff
    await _login(db_session, bob.id, SINCE + timedelta(days=5))
    await db_session.commit()

    result = await get_login_counts_since(db_session, SINCE)

    assert result[alice.id] == 2  # only the two post-cutoff logins
    assert result[bob.id] == 1


@pytest.mark.asyncio
async def test_user_with_zero_logins_absent_from_result(db_session: AsyncSession):
    ghost = await _make_user(db_session, "ghost@test.com")
    await db_session.commit()

    result = await get_login_counts_since(db_session, SINCE)

    assert ghost.id not in result


@pytest.mark.asyncio
async def test_user_ids_filter_restricts_to_segment(db_session: AsyncSession):
    alice = await _make_user(db_session, "alice2@test.com")
    bob = await _make_user(db_session, "bob2@test.com")
    await _login(db_session, alice.id, SINCE + timedelta(days=1))
    await _login(db_session, bob.id, SINCE + timedelta(days=1))
    await db_session.commit()

    result = await get_login_counts_since(db_session, SINCE, user_ids=[alice.id])

    assert alice.id in result
    assert bob.id not in result


@pytest.mark.asyncio
async def test_empty_user_ids_list_returns_empty_no_query(db_session: AsyncSession):
    result = await get_login_counts_since(db_session, SINCE, user_ids=[])
    assert result == {}
