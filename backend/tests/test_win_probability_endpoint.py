"""GET /api/leaderboard/win-probability — gate + response shape.

Mirrors test_admin_win_probability_toggle.py's session/client fixtures and
predictions.py's `not (user.is_admin or competition.<flag>)` gate pattern
used by the all-entries CSV export.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
import app.services.win_probability as win_probability_service
from app.database import get_session
from app.dependencies import get_current_user
from app.main import app
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.fixture(autouse=True)
def _clean_win_probability_cache():
    win_probability_service.invalidate_win_probability_cache()
    yield
    win_probability_service.invalidate_win_probability_cache()


@pytest.fixture(autouse=True)
def _stub_polymarket(monkeypatch):
    """Gate/response-shape tests never need real network — stub
    Polymarket so the odds-weighted branch stays local."""

    async def _empty(_stage):
        return {}

    monkeypatch.setattr(win_probability_service, "get_stage_reach_probabilities", _empty)


async def _make_competition(
    session: AsyncSession, *, win_probability_enabled: bool
) -> Competition:
    comp = Competition(
        name="Test WC 2026",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        win_probability_enabled=win_probability_enabled,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _make_user(session: AsyncSession, *, email: str, is_admin: bool = False) -> User:
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


async def _make_entry(
    session: AsyncSession, competition: Competition, user: User
) -> PredictionEntry:
    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference="WC26-000001",
        display_name="Entry",
        entry_number=1,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    session.add(
        PredictionEntryPhase(
            entry_id=entry.id, phase=PredictionPhase.PHASE_1, status=EntryStatus.SUBMITTED
        )
    )
    await session.commit()
    return entry


def _client_as(session: AsyncSession, user: User):
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_non_admin_forbidden_when_flag_off(session: AsyncSession):
    await _make_competition(session, win_probability_enabled=False)
    user = await _make_user(session, email="u@example.com", is_admin=False)
    async with _client_as(session, user) as ac:
        resp = await ac.get("/api/leaderboard/win-probability")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_allowed_even_when_flag_off(session: AsyncSession):
    competition = await _make_competition(session, win_probability_enabled=False)
    admin = await _make_user(session, email="a@example.com", is_admin=True)
    await _make_entry(session, competition, admin)
    async with _client_as(session, admin) as ac:
        resp = await ac.get("/api/leaderboard/win-probability")
    app.dependency_overrides.clear()
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_non_admin_allowed_when_flag_on(session: AsyncSession):
    competition = await _make_competition(session, win_probability_enabled=True)
    user = await _make_user(session, email="u@example.com", is_admin=False)
    await _make_entry(session, competition, user)
    async with _client_as(session, user) as ac:
        resp = await ac.get("/api/leaderboard/win-probability")
    app.dependency_overrides.clear()
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_response_shape_and_probabilities_sum_to_one(session: AsyncSession):
    competition = await _make_competition(session, win_probability_enabled=True)
    admin = await _make_user(session, email="a@example.com", is_admin=True)
    await _make_entry(session, competition, admin)
    async with _client_as(session, admin) as ac:
        resp = await ac.get("/api/leaderboard/win-probability")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert "entries" in body
    assert "teams" in body
    assert "meta" in body
    assert body["meta"]["mode"] == "exact"

    entry = body["entries"][0]
    assert set(entry) >= {"entry_id", "p_win", "p_top3", "expected_rank"}
    assert round(sum(e["p_win"] for e in body["entries"]), 6) == 1.0

    # No ODDS_API_KEY in test settings -> nothing priced -> odds_weighted
    # stays absent rather than surfacing a misleadingly-identical copy.
    assert body["odds_weighted"] is None
    assert body["odds_coverage"] == {"priced": 0, "priceable": 0}


@pytest.mark.asyncio
async def test_engine_failure_degrades_to_unavailable_not_500(session: AsyncSession, monkeypatch):
    """A bug in the simulator must never surface as a 500 to the pool —
    same fail-open philosophy as live_projection.apply_live_projection."""
    competition = await _make_competition(session, win_probability_enabled=True)
    user = await _make_user(session, email="u@example.com", is_admin=False)
    await _make_entry(session, competition, user)

    async def _boom(_session):
        raise RuntimeError("simulator exploded")

    monkeypatch.setattr(win_probability_service, "get_win_probability", _boom)

    async with _client_as(session, user) as ac:
        resp = await ac.get("/api/leaderboard/win-probability")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["entries"] == []
    assert body["teams"] == []
    assert body["meta"]["mode"] == "unavailable"
