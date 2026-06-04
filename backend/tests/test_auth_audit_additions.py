"""HTTP-level tests for the v2.156.0 audit additions in auth.py.

Covers:
- ``verify_magic_link`` fires ``auth.login_succeeded`` on the success
  path (and not on rejection).
- ``PATCH /api/auth/me`` fires ``user.profile_updated`` when fields
  actually change. Idempotent no-op PATCH does NOT fire — pinning the
  "Last activity" semantic.

Reuses the same in-memory-SQLite + dependency-override pattern as
``test_auth_profile.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import app.models  # noqa: F401 — register every model with metadata
from app.database import get_session
from app.dependencies import get_current_user
from app.main import app
from app.models.audit import AuditEvent
from app.models.magic_link_token import (
    MagicLinkToken,
    generate_magic_token,
    hash_token,
)
from app.models.user import AuthProvider, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def alice(db_session: AsyncSession) -> User:
    u = User(
        email="alice@example.com",
        name="Alice",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, alice: User):
    """HTTP client with dependency overrides — alice is the current user."""

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# verify_magic_link — auth.login_succeeded
# ---------------------------------------------------------------------------
class TestMagicLinkVerifyAudit:
    @pytest.mark.asyncio
    async def test_successful_verify_fires_audit_event(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: User,
    ):
        # Seed a fresh, unused, unexpired magic-link token for alice.
        raw, hashed = generate_magic_token()
        token_row = MagicLinkToken(
            user_id=alice.id,
            token_hash=hashed,
            expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=15),
            used_at=None,
        )
        db_session.add(token_row)
        await db_session.commit()

        resp = await client.get(
            "/api/auth/verify-magic-link", params={"token": raw},
            follow_redirects=False,
        )
        # Magic-link verify redirects on success.
        assert resp.status_code in (302, 307)

        events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "auth.login_succeeded"
                )
            )
        ).scalars().all()
        assert len(events) == 1
        event = events[0]
        assert event.actor_user_id == alice.id
        # The auth provider metadata identifies this as a magic-link flow
        # (vs. email/password or Google, both of which also fire the
        # event but with different provider strings).
        assert event.event_metadata is not None
        assert event.event_metadata.get("auth_provider") == "magic_link"

    @pytest.mark.asyncio
    async def test_invalid_token_does_not_fire_audit(
        self, client: AsyncClient, db_session: AsyncSession, alice: User
    ):
        # Use a token that doesn't exist in the DB.
        resp = await client.get(
            "/api/auth/verify-magic-link",
            params={"token": "nonexistent-token-zz"},
        )
        assert resp.status_code == 400

        events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "auth.login_succeeded"
                )
            )
        ).scalars().all()
        assert events == []  # no audit row written

    @pytest.mark.asyncio
    async def test_used_token_does_not_fire_audit(
        self, client: AsyncClient, db_session: AsyncSession, alice: User
    ):
        # Token already marked used — verify should reject AND not audit.
        raw, hashed = generate_magic_token()
        token_row = MagicLinkToken(
            user_id=alice.id,
            token_hash=hashed,
            expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=15),
            used_at=datetime.now(tz=timezone.utc) - timedelta(minutes=1),
        )
        db_session.add(token_row)
        await db_session.commit()

        resp = await client.get(
            "/api/auth/verify-magic-link", params={"token": raw}
        )
        assert resp.status_code == 400

        events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "auth.login_succeeded"
                )
            )
        ).scalars().all()
        assert events == []


# ---------------------------------------------------------------------------
# update_current_user — user.profile_updated
# ---------------------------------------------------------------------------
class TestProfileUpdateAudit:
    @pytest.mark.asyncio
    async def test_changing_name_fires_audit(
        self, client: AsyncClient, db_session: AsyncSession, alice: User
    ):
        resp = await client.patch(
            "/api/auth/me", json={"name": "Alice Renamed"}
        )
        assert resp.status_code == 200

        events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "user.profile_updated"
                )
            )
        ).scalars().all()
        assert len(events) == 1
        event = events[0]
        assert event.actor_user_id == alice.id
        # Metadata records changed FIELDS only (no values, for PII).
        assert event.event_metadata == {"changed": ["name"]}

    @pytest.mark.asyncio
    async def test_changing_multiple_fields_lists_all(
        self, client: AsyncClient, db_session: AsyncSession, alice: User
    ):
        resp = await client.patch(
            "/api/auth/me",
            json={
                "name": "Alice Renamed",
                "paid_to": "Pool Treasurer",
            },
        )
        assert resp.status_code == 200

        event = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "user.profile_updated"
                )
            )
        ).scalar_one()
        assert event.event_metadata is not None
        # Both fields should appear; we don't pin the order — just the set.
        assert set(event.event_metadata["changed"]) == {"name", "paid_to"}

    @pytest.mark.asyncio
    async def test_idempotent_noop_patch_does_not_fire(
        self, client: AsyncClient, db_session: AsyncSession, alice: User
    ):
        # Alice's name is already "Alice"; PATCH with the same value
        # is a no-op and MUST NOT show up in the audit feed.
        resp = await client.patch("/api/auth/me", json={"name": "Alice"})
        assert resp.status_code == 200

        events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "user.profile_updated"
                )
            )
        ).scalars().all()
        assert events == []

    @pytest.mark.asyncio
    async def test_empty_patch_does_not_fire(
        self, client: AsyncClient, db_session: AsyncSession, alice: User
    ):
        # Completely empty PATCH (no fields set) is also a no-op.
        resp = await client.patch("/api/auth/me", json={})
        assert resp.status_code == 200

        events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "user.profile_updated"
                )
            )
        ).scalars().all()
        assert events == []
