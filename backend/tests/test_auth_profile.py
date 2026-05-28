"""HTTP-level tests for profile updates + the sign-in CAPTCHA gate.

Covers `PATCH /api/auth/me` (the new onboarding/profile fields and their
validators) and the Turnstile gate on `POST /api/auth/request-magic-link`.

Uses the project's in-memory-SQLite + dependency-override pattern.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import app.models  # noqa: F401  — register all models
from app.database import get_session
from app.dependencies import get_current_user
from app.main import app
from app.models.magic_link_token import MagicLinkToken
from app.models.user import AuthProvider, Employer, User


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
    u = User(email="alice@example.com", name="Alice", auth_provider=AuthProvider.EMAIL)
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, alice: User):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── PATCH /auth/me — profile fields ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_employer_atlas_needs_no_contact(client: AsyncClient):
    resp = await client.patch("/api/auth/me", json={"employer": "atlas"})
    assert resp.status_code == 200
    assert resp.json()["employer"] == "atlas"


@pytest.mark.asyncio
async def test_employer_neither_without_contact_rejected(client: AsyncClient):
    resp = await client.patch("/api/auth/me", json={"employer": "neither"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_employer_neither_with_contact_ok(client: AsyncClient):
    resp = await client.patch(
        "/api/auth/me", json={"employer": "neither", "company_contact": "Dana at Atlas"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["employer"] == "neither"
    assert body["company_contact"] == "Dana at Atlas"


@pytest.mark.asyncio
async def test_set_paid_to(client: AsyncClient):
    resp = await client.patch("/api/auth/me", json={"paid_to": "Sam"})
    assert resp.status_code == 200
    assert resp.json()["paid_to"] == "Sam"


@pytest.mark.asyncio
async def test_partial_update_preserves_other_fields(
    client: AsyncClient, db_session: AsyncSession, alice: User
):
    # Set employer first, then update only the paid_to — employer must survive.
    await client.patch("/api/auth/me", json={"employer": "jmfa"})
    resp = await client.patch("/api/auth/me", json={"paid_to": "Sam"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["paid_to"] == "Sam"
    assert body["employer"] == "jmfa"


# ── CAPTCHA gate on request-magic-link ───────────────────────────────────────


@pytest.mark.asyncio
async def test_magic_link_passes_when_captcha_disabled(client: AsyncClient):
    # No TURNSTILE_SECRET_KEY in the test env → verify_turnstile short-circuits.
    resp = await client.post("/api/auth/request-magic-link", json={"email": "new@example.com"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_magic_link_rejected_on_failed_captcha(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    async def fake_verify(token, remoteip=None):
        return False

    monkeypatch.setattr("app.api.auth.verify_turnstile", fake_verify)
    resp = await client.post(
        "/api/auth/request-magic-link",
        json={"email": "blocked@example.com", "captcha_token": "bad"},
    )
    assert resp.status_code == 400
    # No token row should have been minted.
    rows = (await db_session.execute(select(MagicLinkToken))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_magic_link_succeeds_on_passed_captcha(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    async def fake_verify(token, remoteip=None):
        return True

    monkeypatch.setattr("app.api.auth.verify_turnstile", fake_verify)
    resp = await client.post(
        "/api/auth/request-magic-link",
        json={"email": "ok@example.com", "captcha_token": "good"},
    )
    assert resp.status_code == 200
    rows = (await db_session.execute(select(MagicLinkToken))).scalars().all()
    assert len(rows) == 1
