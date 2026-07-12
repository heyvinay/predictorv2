"""GET /api/leaderboard/champion-market-odds — gate + join + fail-open.

Same gate as /win-probability (admin, or Competition.win_probability_enabled).
Polymarket "winner" odds are joined to the competition's real team names
server-side via canonicalize(), and any Polymarket failure degrades to an
empty odds list rather than a 500.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
import app.services.polymarket as polymarket_service
from app.database import get_session
from app.dependencies import get_current_user
from app.main import app
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.user import AuthProvider, User
from app.services.team_match import canonicalize


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_competition(session, *, enabled: bool) -> Competition:
    comp = Competition(
        name="Test WC 2026",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        win_probability_enabled=enabled,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _make_user(session, *, email: str, is_admin: bool = False) -> User:
    u = User(
        email=email,
        name="T",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
        is_admin=is_admin,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _make_fixtures(session, comp: Competition) -> None:
    # Two real semi-finalists + one unresolved slot placeholder (must be
    # excluded from the join).
    kickoff = datetime.now(tz=timezone.utc) + timedelta(days=1)
    session.add_all(
        [
            Fixture(
                competition_id=comp.id,
                home_team="France",
                away_team="Spain",
                kickoff=kickoff,
                stage="semi_final",
                status=MatchStatus.SCHEDULED,
            ),
            Fixture(
                competition_id=comp.id,
                home_team="slot:final:537390:home",
                away_team="TBD",
                kickoff=kickoff,
                stage="final",
                status=MatchStatus.SCHEDULED,
            ),
        ]
    )
    await session.commit()


def _client_as(session, user: User):
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def _stub_poly(monkeypatch):
    """Polymarket returns odds keyed by the canonical team name — exactly
    what the endpoint looks up via canonicalize(internal_name)."""

    async def _odds(_stage):
        return {canonicalize("France"): 0.41, canonicalize("Spain"): 0.34}

    monkeypatch.setattr(polymarket_service, "get_stage_reach_probabilities", _odds)


@pytest.mark.asyncio
async def test_non_admin_forbidden_when_flag_off(session, _stub_poly):
    await _make_competition(session, enabled=False)
    user = await _make_user(session, email="u@example.com", is_admin=False)
    async with _client_as(session, user) as ac:
        resp = await ac.get("/api/leaderboard/champion-market-odds")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_allowed_when_flag_off(session, _stub_poly):
    comp = await _make_competition(session, enabled=False)
    await _make_fixtures(session, comp)
    admin = await _make_user(session, email="a@example.com", is_admin=True)
    async with _client_as(session, admin) as ac:
        resp = await ac.get("/api/leaderboard/champion-market-odds")
    app.dependency_overrides.clear()
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_non_admin_allowed_and_joined_when_flag_on(session, _stub_poly):
    comp = await _make_competition(session, enabled=True)
    await _make_fixtures(session, comp)
    user = await _make_user(session, email="u@example.com", is_admin=False)
    async with _client_as(session, user) as ac:
        resp = await ac.get("/api/leaderboard/champion-market-odds")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    odds = {o["team"]: o["market_odds"] for o in resp.json()["odds"]}
    # Real teams joined to their market odds; slot/TBD placeholders excluded.
    assert odds == {"France": 0.41, "Spain": 0.34}


@pytest.mark.asyncio
async def test_fail_open_returns_empty_odds(session, monkeypatch):
    comp = await _make_competition(session, enabled=True)
    await _make_fixtures(session, comp)
    admin = await _make_user(session, email="a@example.com", is_admin=True)

    async def _boom(_stage):
        raise RuntimeError("polymarket down")

    monkeypatch.setattr(polymarket_service, "get_stage_reach_probabilities", _boom)

    async with _client_as(session, admin) as ac:
        resp = await ac.get("/api/leaderboard/champion-market-odds")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["odds"] == []
