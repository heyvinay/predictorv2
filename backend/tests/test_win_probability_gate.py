"""is_win_probability_enabled() helper + its surface on GET /phase-status.

Mirrors is_knockout_scoring_enabled's fail-closed contract and
test_deadline_close.py's phase-status test shape.
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
from app.dependencies import get_current_user
from app.main import app
from app.models.competition import Competition
from app.models.user import AuthProvider, User
from app.services.scoring import is_win_probability_enabled


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def test_is_win_probability_enabled_false_with_no_active_competition(
    db_session: AsyncSession,
):
    assert await is_win_probability_enabled(db_session) is False


async def test_is_win_probability_enabled_reflects_the_flag(db_session: AsyncSession):
    comp = Competition(name="Test WC", external_id="WC", is_active=True)
    db_session.add(comp)
    await db_session.commit()
    assert await is_win_probability_enabled(db_session) is False

    comp.win_probability_enabled = True
    await db_session.commit()
    assert await is_win_probability_enabled(db_session) is True


@pytest.mark.asyncio
async def test_phase_status_exposes_win_probability_flag(db_session: AsyncSession):
    comp = Competition(
        name="Test WC", external_id="WC", is_active=True, win_probability_enabled=True
    )
    db_session.add(comp)
    await db_session.commit()

    user = User(email="u@example.com", name="U", password_hash="x", auth_provider=AuthProvider.EMAIL)
    db_session.add(user)
    await db_session.commit()

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/competition/phase-status")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["win_probability_enabled"] is True
