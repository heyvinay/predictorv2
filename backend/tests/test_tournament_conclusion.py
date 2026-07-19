"""Tournament conclusion end-state (Plan A) — flag, phase-status, admin toggle."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register all tables
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user, get_current_user_optional
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


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    u = User(
        email="user@example.com",
        name="Regular",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
        is_admin=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def client_as_user(db_session: AsyncSession, regular_user: User):
    """Authenticated but NON-admin. Overrides get_current_user_optional
    directly (not just get_current_user) so OptionalUser-typed routes
    (e.g. GET /leaderboard/) genuinely see a real, non-admin User through
    the actual dependency — same reasoning as test_tournament_champion.py's
    client_as_user fixture.
    """

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: regular_user
    app.dependency_overrides[get_current_user_optional] = lambda: regular_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_anonymous(db_session: AsyncSession):
    """Same AsyncClient shape as client_as_admin, but ONLY get_session is
    overridden — no user/admin override — so the real
    get_current_user_optional dependency runs and yields None for an
    unauthenticated request (no Authorization header sent)."""

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_feedback_accepts_features(client_as_user, monkeypatch):
    sent = {}

    async def fake_send(**kwargs):
        sent.update(kwargs)

    from app.services import email as email_service
    monkeypatch.setattr(email_service, "send_feedback_email", fake_send)

    resp = await client_as_user.post(
        "/api/feedback/",
        json={"rating": 5, "message": "loved it", "features": ["leaderboard", "compare"]},
    )
    assert resp.status_code == 204
    assert "leaderboard" in sent.get("features_line", "")


@pytest.mark.asyncio
async def test_leaderboard_public_when_concluded(client_anonymous, competition, db_session):
    competition.tournament_concluded = True
    await db_session.commit()
    resp = await client_anonymous.get("/api/leaderboard/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_competition_has_conclusion_fields(competition: Competition):
    assert competition.tournament_concluded is False
    assert competition.final_match_narrative is None


@pytest.mark.asyncio
async def test_phase_status_surfaces_tournament_concluded(
    db_session: AsyncSession, competition: Competition
):
    from app.api.competition import get_phase_status

    status_out = await get_phase_status(session=db_session, _user=None)
    assert status_out.tournament_concluded is False

    competition.tournament_concluded = True
    await db_session.commit()
    status_out = await get_phase_status(session=db_session, _user=None)
    assert status_out.tournament_concluded is True


@pytest.mark.asyncio
async def test_phase_status_reachable_anonymously(
    client_anonymous, competition: Competition, db_session: AsyncSession
):
    """★ Regression pin (2026-07-19): GET /competition/phase-status used to
    require CurrentUser (hard auth), so an anonymous browser could never
    learn tournament_concluded — the frontend root layout calls this
    endpoint unconditionally on every page load (including for guests), so
    the public wrap-up page was completely unreachable without signing in.
    Caught by live guest-mode verification, not by the direct-call unit
    test above (which bypasses FastAPI's dependency injection entirely and
    would pass regardless of the route's real auth requirement) — this
    test goes through the actual ASGI/HTTP layer so it can't repeat that
    blind spot."""
    resp = await client_anonymous.get("/api/competition/phase-status")
    assert resp.status_code == 200
    assert resp.json()["tournament_concluded"] is False

    competition.tournament_concluded = True
    await db_session.commit()
    resp = await client_anonymous.get("/api/competition/phase-status")
    assert resp.status_code == 200
    assert resp.json()["tournament_concluded"] is True


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


@pytest.mark.asyncio
async def test_saving_blank_narrative_clears_it(client_as_admin, competition):
    # Save a real narrative first.
    resp = await client_as_admin.put(
        "/api/admin/competition/final-narrative",
        json={"narrative": "Extra time thriller."},
    )
    assert resp.json()["final_match_narrative"] == "Extra time thriller."

    # It round-trips through GET /admin/competitions — the response the
    # admin page's loadData() already fetches and hydrates its "Final
    # match narrative" textarea from on mount.
    resp = await client_as_admin.get("/api/admin/competitions")
    assert resp.status_code == 200
    row = next(c for c in resp.json() if c["id"] == str(competition.id))
    assert row["final_match_narrative"] == "Extra time thriller."

    # Saving blank/whitespace-only input clears it back to None, not "".
    resp = await client_as_admin.put(
        "/api/admin/competition/final-narrative", json={"narrative": "   "}
    )
    assert resp.status_code == 200
    assert resp.json()["final_match_narrative"] is None

    resp = await client_as_admin.get("/api/admin/competitions")
    row = next(c for c in resp.json() if c["id"] == str(competition.id))
    assert row["final_match_narrative"] is None
