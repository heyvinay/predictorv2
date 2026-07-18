"""Tournament conclusion end-state (Plan A) — flag, phase-status, admin toggle."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register all tables
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user
from app.main import app
from app.models.competition import Competition
from app.models._datetime import utc_now
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
async def competition(db_session: AsyncSession) -> Competition:
    comp = Competition(
        name="WC26",
        is_active=True,
        phase1_deadline=utc_now(),
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    u = User(
        email="admin@example.com",
        name="Admin",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
        is_admin=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def client_as_admin(db_session: AsyncSession, admin_user: User):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_admin_user] = lambda: admin_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_competition_has_conclusion_fields(competition: Competition):
    assert competition.tournament_concluded is False
    assert competition.final_match_narrative is None


@pytest.mark.asyncio
async def test_phase_status_surfaces_tournament_concluded(
    db_session: AsyncSession, competition: Competition
):
    from app.api.competition import get_phase_status

    status_out = await get_phase_status(session=db_session, _current_user=None)
    assert status_out.tournament_concluded is False

    competition.tournament_concluded = True
    await db_session.commit()
    status_out = await get_phase_status(session=db_session, _current_user=None)
    assert status_out.tournament_concluded is True


@pytest.mark.asyncio
async def test_admin_toggles_conclusion(client_as_admin, competition):
    resp = await client_as_admin.post(
        "/api/admin/competition/conclusion", json={"concluded": True}
    )
    assert resp.status_code == 200
    assert resp.json()["tournament_concluded"] is True

    resp = await client_as_admin.post(
        "/api/admin/competition/conclusion", json={"concluded": False}
    )
    assert resp.json()["tournament_concluded"] is False


@pytest.mark.asyncio
async def test_admin_saves_final_narrative(client_as_admin, competition):
    resp = await client_as_admin.put(
        "/api/admin/competition/final-narrative",
        json={"narrative": "A cagey final broke open on 38'."},
    )
    assert resp.status_code == 200
    assert resp.json()["final_match_narrative"].startswith("A cagey")
