"""Service-level tests for the audit reader (v2.156.0).

Pins the contracts of:
- :func:`app.services.audit.query_audit_events`
- :func:`app.services.audit.last_login_for_users`
- :func:`app.services.audit.last_activity_for_users`

Uses the project's in-memory-SQLite fixture pattern. The portable
JSONB-with-variant column means JSON metadata round-trips through
SQLite cleanly for tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register every model with metadata
from app.models.audit import AuditEvent
from app.models.entry import ActorRole
from app.models.user import AuthProvider, User
from app.services.audit import (
    last_activity_for_users,
    last_login_for_users,
    query_audit_events,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


def _utc(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def alice_and_bob(session: AsyncSession) -> tuple[User, User]:
    alice = User(email="alice@example.com", name="Alice", auth_provider=AuthProvider.EMAIL)
    bob = User(email="bob@other.test", name="Bob", auth_provider=AuthProvider.EMAIL)
    session.add(alice)
    session.add(bob)
    await session.commit()
    await session.refresh(alice)
    await session.refresh(bob)
    return alice, bob


@pytest_asyncio.fixture
async def mixed_audit_log(
    session: AsyncSession, alice_and_bob: tuple[User, User]
) -> tuple[User, User]:
    """Seed an audit log with 6 rows across both users + 1 system row.

    Chronological order:
      [oldest] alice login (1 May)
               bob login (5 May)
               alice profile update (10 May)
               bob entry created (15 May)
               alice login (20 May) — her newer login
               system failed-login (25 May)
      [newest] bob entry submitted (30 May)
    """
    alice, bob = alice_and_bob

    events = [
        AuditEvent(
            event_type="auth.login_succeeded",
            actor_user_id=alice.id,
            actor_role=ActorRole.USER,
            subject_type="user",
            subject_id=alice.id,
            created_at=_utc(2026, 5, 1, 9, 0),
        ),
        AuditEvent(
            event_type="auth.login_succeeded",
            actor_user_id=bob.id,
            actor_role=ActorRole.USER,
            subject_type="user",
            subject_id=bob.id,
            created_at=_utc(2026, 5, 5, 10, 0),
        ),
        AuditEvent(
            event_type="user.profile_updated",
            actor_user_id=alice.id,
            actor_role=ActorRole.USER,
            subject_type="user",
            subject_id=alice.id,
            event_metadata={"changed": ["name"]},
            created_at=_utc(2026, 5, 10, 11, 0),
        ),
        AuditEvent(
            event_type="entry.created",
            actor_user_id=bob.id,
            actor_role=ActorRole.USER,
            subject_type="entry",
            subject_id=uuid4(),
            created_at=_utc(2026, 5, 15, 12, 0),
        ),
        AuditEvent(
            event_type="auth.login_succeeded",
            actor_user_id=alice.id,
            actor_role=ActorRole.USER,
            subject_type="user",
            subject_id=alice.id,
            created_at=_utc(2026, 5, 20, 13, 0),
        ),
        AuditEvent(
            event_type="auth.login_failed",
            actor_user_id=None,  # system event — unknown email
            actor_role=ActorRole.SYSTEM,
            event_metadata={"email": "unknown@nowhere.test"},
            created_at=_utc(2026, 5, 25, 14, 0),
        ),
        AuditEvent(
            event_type="entry.phase_submitted",
            actor_user_id=bob.id,
            actor_role=ActorRole.USER,
            subject_type="entry",
            subject_id=uuid4(),
            created_at=_utc(2026, 5, 30, 15, 0),
        ),
    ]
    for e in events:
        session.add(e)
    await session.commit()
    return alice, bob


# ---------------------------------------------------------------------------
# query_audit_events
# ---------------------------------------------------------------------------
class TestQueryAuditEvents:
    @pytest.mark.asyncio
    async def test_default_returns_all_newest_first(
        self, session: AsyncSession, mixed_audit_log
    ):
        rows, total = await query_audit_events(session)
        assert total == 7
        assert len(rows) == 7
        # Newest-first ordering
        timestamps = [r.created_at for r in rows]
        assert timestamps == sorted(timestamps, reverse=True)

    @pytest.mark.asyncio
    async def test_event_type_exact_match(
        self, session: AsyncSession, mixed_audit_log
    ):
        rows, total = await query_audit_events(
            session, event_type="auth.login_succeeded"
        )
        assert total == 3
        assert all(r.event_type == "auth.login_succeeded" for r in rows)

    @pytest.mark.asyncio
    async def test_namespace_prefix_match(
        self, session: AsyncSession, mixed_audit_log
    ):
        rows, total = await query_audit_events(session, namespace="auth")
        # login_succeeded × 3 + login_failed × 1 = 4
        assert total == 4
        assert all(r.event_type.startswith("auth.") for r in rows)

    @pytest.mark.asyncio
    async def test_actor_user_id_filter(
        self, session: AsyncSession, mixed_audit_log
    ):
        alice, _bob = mixed_audit_log
        rows, total = await query_audit_events(session, actor_user_id=alice.id)
        # alice: 2 logins + 1 profile_updated = 3
        assert total == 3
        assert all(r.actor_user_id == alice.id for r in rows)

    @pytest.mark.asyncio
    async def test_search_by_actor_email_substring(
        self, session: AsyncSession, mixed_audit_log
    ):
        rows, total = await query_audit_events(session, search="alice")
        assert total == 3
        assert all(r.actor_email == "alice@example.com" for r in rows)

    @pytest.mark.asyncio
    async def test_search_by_actor_name_substring(
        self, session: AsyncSession, mixed_audit_log
    ):
        # "Bob" is alice/Bob — case-insensitive substring
        rows, total = await query_audit_events(session, search="bob")
        # bob: 1 login + 1 entry created + 1 entry submitted = 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_search_by_event_type_substring(
        self, session: AsyncSession, mixed_audit_log
    ):
        rows, total = await query_audit_events(session, search="profile")
        assert total == 1
        assert rows[0].event_type == "user.profile_updated"

    @pytest.mark.asyncio
    async def test_search_is_case_insensitive(
        self, session: AsyncSession, mixed_audit_log
    ):
        upper, _ = await query_audit_events(session, search="ALICE")
        lower, _ = await query_audit_events(session, search="alice")
        assert len(upper) == len(lower) == 3

    @pytest.mark.asyncio
    async def test_since_until_window(
        self, session: AsyncSession, mixed_audit_log
    ):
        # closed-open [since, until) — May 10 inclusive to May 20 exclusive
        rows, total = await query_audit_events(
            session, since=_utc(2026, 5, 10), until=_utc(2026, 5, 20)
        )
        # 10 May (profile), 15 May (entry created) — 20 May login excluded
        assert total == 2

    @pytest.mark.asyncio
    async def test_left_join_survives_null_actor(
        self, session: AsyncSession, mixed_audit_log
    ):
        # System event has actor_user_id=None — must still appear with
        # NULL actor_name / actor_email rather than being filtered out.
        rows, total = await query_audit_events(
            session, event_type="auth.login_failed"
        )
        assert total == 1
        assert rows[0].actor_user_id is None
        assert rows[0].actor_name is None
        assert rows[0].actor_email is None

    @pytest.mark.asyncio
    async def test_limit_and_offset(
        self, session: AsyncSession, mixed_audit_log
    ):
        first_two, total = await query_audit_events(session, limit=2, offset=0)
        next_two, _ = await query_audit_events(session, limit=2, offset=2)
        assert total == 7
        assert len(first_two) == 2
        assert len(next_two) == 2
        # No overlap
        assert {r.id for r in first_two}.isdisjoint({r.id for r in next_two})

    @pytest.mark.asyncio
    async def test_subject_id_filter(
        self, session: AsyncSession, mixed_audit_log
    ):
        alice, _bob = mixed_audit_log
        rows, total = await query_audit_events(session, subject_id=alice.id)
        # alice as subject: 2 logins + 1 profile_updated = 3
        assert total == 3
        assert all(r.subject_id == alice.id for r in rows)


# ---------------------------------------------------------------------------
# last_login_for_users
# ---------------------------------------------------------------------------
class TestLastLoginForUsers:
    @pytest.mark.asyncio
    async def test_returns_latest_per_user(
        self, session: AsyncSession, mixed_audit_log
    ):
        alice, bob = mixed_audit_log
        out = await last_login_for_users(session, [alice.id, bob.id])
        # Alice has two logins on 1 May and 20 May → latest is 20 May
        assert out[alice.id] == _utc(2026, 5, 20, 13, 0)
        # Bob has one login on 5 May
        assert out[bob.id] == _utc(2026, 5, 5, 10, 0)

    @pytest.mark.asyncio
    async def test_user_with_no_login_absent_from_result(
        self, session: AsyncSession, mixed_audit_log
    ):
        # Make a fresh user with no audit history.
        ghost = User(
            email="ghost@nowhere.test",
            name=None,
            auth_provider=AuthProvider.EMAIL,
        )
        session.add(ghost)
        await session.commit()
        await session.refresh(ghost)
        out = await last_login_for_users(session, [ghost.id])
        assert out == {}

    @pytest.mark.asyncio
    async def test_empty_input_short_circuits(self, session: AsyncSession):
        # No DB roundtrip needed; sanity-check the early return.
        assert await last_login_for_users(session, []) == {}


# ---------------------------------------------------------------------------
# last_activity_for_users
# ---------------------------------------------------------------------------
class TestLastActivityForUsers:
    @pytest.mark.asyncio
    async def test_includes_writes_not_just_logins(
        self, session: AsyncSession, mixed_audit_log
    ):
        alice, bob = mixed_audit_log
        out = await last_activity_for_users(session, [alice.id, bob.id])
        # Alice's latest activity is her profile_updated... wait, her
        # latest login is 20 May (newer than profile_updated 10 May)
        # so last_activity for her = 20 May 13:00.
        assert out[alice.id] == _utc(2026, 5, 20, 13, 0)
        # Bob's latest is entry.phase_submitted on 30 May 15:00 — broader
        # than his last login (5 May).
        assert out[bob.id] == _utc(2026, 5, 30, 15, 0)
        # The point of the test: bob's last_activity > his last_login.
        logins = await last_login_for_users(session, [bob.id])
        assert out[bob.id] > logins[bob.id]

    @pytest.mark.asyncio
    async def test_empty_input_short_circuits(self, session: AsyncSession):
        assert await last_activity_for_users(session, []) == {}
