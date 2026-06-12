"""Door policy (v2.166.0) — post-deadline signup refusal, all three doors.

NEW account creation must be refused once the active competition's
phase-1 deadline passes; EXISTING users keep signing in (they need to
see results). The gate is `_signups_closed()` in `app.api.auth`, shared
by all three entry points:

  1. POST /api/auth/register        → 403, nothing created
  2. POST /api/auth/request-magic-link (unknown email)
                                    → generic 200, NO user, NO token,
                                      no email (anti-enumeration)
  3. Google OAuth callback          → 403 (same helper — covered here at
                                      the helper level; the SSO handshake
                                      itself isn't worth mocking)

Uses the project's in-memory-SQLite + dependency-override pattern
(see test_auth_profile.py). Turnstile is unconfigured in tests, so the
magic-link CAPTCHA gate passes through; Resend is unconfigured, so the
email send falls back to logging.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import app.models  # noqa: F401  — register all models
from app.api.auth import SIGNUPS_CLOSED_DETAIL, _signups_closed
from app.database import get_session
from app.main import app
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.magic_link_token import MagicLinkToken
from app.models.user import AuthProvider, User


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_competition(
    db_session: AsyncSession, *, deadline: datetime
) -> Competition:
    comp = Competition(
        name="WC2026",
        external_id="WC",
        is_active=True,
        phase1_deadline=deadline,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


PAST = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)
FUTURE_DELTA = timedelta(days=30)

REGISTER_BODY = {
    "email": "newcomer@example.com",
    "password": "CorrectHorse9!",
    "name": "New Comer",
}


async def _user_count(db_session: AsyncSession) -> int:
    rows = await db_session.execute(select(User))
    return len(rows.scalars().all())


# ── Door 1: /register ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_refused_after_deadline(client, db_session):
    await _make_competition(db_session, deadline=PAST)

    resp = await client.post("/api/auth/register", json=REGISTER_BODY)

    assert resp.status_code == 403
    assert resp.json()["detail"] == SIGNUPS_CLOSED_DETAIL
    assert await _user_count(db_session) == 0, "403 must create nothing"


@pytest.mark.asyncio
async def test_register_open_before_deadline(client, db_session):
    await _make_competition(db_session, deadline=utc_now() + FUTURE_DELTA)

    resp = await client.post("/api/auth/register", json=REGISTER_BODY)

    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert await _user_count(db_session) == 1


# ── Door 2: /request-magic-link with an unknown email ───────────────────────


@pytest.mark.asyncio
async def test_magic_link_unknown_email_creates_nothing_after_deadline(
    client, db_session
):
    await _make_competition(db_session, deadline=PAST)

    resp = await client.post(
        "/api/auth/request-magic-link", json={"email": "stranger@example.com"}
    )

    # Same generic message as a real send — no enumeration leak.
    assert resp.status_code == 200
    assert "registered" in resp.json()["message"]
    assert await _user_count(db_session) == 0, "no account may be created"
    tokens = (await db_session.execute(select(MagicLinkToken))).scalars().all()
    assert tokens == [], "no sign-in token may be issued"


@pytest.mark.asyncio
async def test_magic_link_existing_user_still_works_after_deadline(
    client, db_session
):
    await _make_competition(db_session, deadline=PAST)
    user = User(
        email="veteran@example.com", name="Vet", auth_provider=AuthProvider.EMAIL
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post(
        "/api/auth/request-magic-link", json={"email": "veteran@example.com"}
    )

    assert resp.status_code == 200
    tokens = (
        (
            await db_session.execute(
                select(MagicLinkToken).where(MagicLinkToken.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(tokens) == 1, "existing users must keep getting sign-in links"


# ── Door 3 (shared gate): _signups_closed — also guards the Google OAuth
#    callback, whose SSO handshake isn't worth mocking here ──────────────────


@pytest.mark.asyncio
async def test_signups_closed_helper_states(db_session):
    # No active competition at all → open (pre-config dev state).
    assert await _signups_closed(db_session) is False

    comp = await _make_competition(db_session, deadline=utc_now() + FUTURE_DELTA)
    assert await _signups_closed(db_session) is False

    comp.phase1_deadline = PAST
    db_session.add(comp)
    await db_session.commit()
    assert await _signups_closed(db_session) is True
