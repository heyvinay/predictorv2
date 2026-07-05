"""HTTP-level tests for POST /api/feedback/ (rating + written feedback).

Uses the project's in-memory-SQLite + dependency-override pattern. The
Resend send is mocked — no real email leaves the test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401  — register all models
from app.database import get_session
from app.dependencies import get_current_user
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


@pytest_asyncio.fixture
async def anon_client(db_session: AsyncSession):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_feedback_sends_email(client: AsyncClient, monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr("app.services.email.send_feedback_email", send)
    monkeypatch.setattr("app.services.analytics.capture", lambda **kw: None)

    resp = await client.post(
        "/api/feedback/", json={"rating": 4, "message": "Love the bracket view!"}
    )
    assert resp.status_code == 204
    send.assert_awaited_once()
    kwargs = send.await_args.kwargs
    assert kwargs["rating"] == 4
    assert kwargs["message"] == "Love the bracket view!"
    assert kwargs["reply_to"] == "alice@example.com"
    assert kwargs["user_name"] == "Alice"


@pytest.mark.asyncio
async def test_feedback_strips_whitespace_only_message(client: AsyncClient, monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr("app.services.email.send_feedback_email", send)
    resp = await client.post("/api/feedback/", json={"rating": 3, "message": "   "})
    assert resp.status_code == 422
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_feedback_empty_message_rejected(client: AsyncClient, monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr("app.services.email.send_feedback_email", send)
    resp = await client.post("/api/feedback/", json={"rating": 3, "message": ""})
    assert resp.status_code == 422
    send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("rating", [0, 6, -1])
async def test_feedback_rejects_out_of_range_rating(
    client: AsyncClient, monkeypatch, rating: int
):
    send = AsyncMock()
    monkeypatch.setattr("app.services.email.send_feedback_email", send)
    resp = await client.post("/api/feedback/", json={"rating": rating, "message": "hi"})
    assert resp.status_code == 422
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_feedback_requires_auth(anon_client: AsyncClient, monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr("app.services.email.send_feedback_email", send)
    resp = await anon_client.post("/api/feedback/", json={"rating": 5, "message": "hi"})
    assert resp.status_code == 401
    send.assert_not_awaited()
