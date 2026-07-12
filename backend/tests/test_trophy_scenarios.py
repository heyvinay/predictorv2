"""GET /api/leaderboard/trophy-scenarios — deliberately PUBLIC (no admin /
win_probability_enabled gate), unlike /win-probability. Blind-pool gated
only (empty pre-deadline). Path to the Trophy is meant to be visible to
the whole pool, so this is the one place that must NOT inherit the gate.
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
    async def _empty(_stage):
        return {}

    monkeypatch.setattr(win_probability_service, "get_stage_reach_probabilities", _empty)


async def _make_competition(
    session: AsyncSession, *, win_probability_enabled: bool, deadline_passed: bool
) -> Competition:
    deadline = (
        datetime.now(tz=timezone.utc) - timedelta(hours=1)
        if deadline_passed
        else datetime.now(tz=timezone.utc) + timedelta(days=1)
    )
    comp = Competition(
        name="Test WC 2026",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        phase1_deadline=deadline,
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


async def _make_entry(session: AsyncSession, competition: Competition, user: User) -> PredictionEntry:
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
async def test_non_admin_never_403s_regardless_of_flag(session: AsyncSession):
    """The whole point: unlike /win-probability, a non-admin gets 200 here
    even with win_probability_enabled off."""
    competition = await _make_competition(
        session, win_probability_enabled=False, deadline_passed=True
    )
    user = await _make_user(session, email="u@example.com", is_admin=False)
    await _make_entry(session, competition, user)
    async with _client_as(session, user) as ac:
        resp = await ac.get("/api/leaderboard/trophy-scenarios")
    app.dependency_overrides.clear()
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_empty_before_deadline_locks(session: AsyncSession):
    competition = await _make_competition(
        session, win_probability_enabled=True, deadline_passed=False
    )
    user = await _make_user(session, email="u@example.com", is_admin=False)
    await _make_entry(session, competition, user)
    async with _client_as(session, user) as ac:
        resp = await ac.get("/api/leaderboard/trophy-scenarios")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["scenarios"] == []
    assert body["match_meta"] == []


@pytest.mark.asyncio
async def test_response_shape_once_locked(session: AsyncSession):
    competition = await _make_competition(
        session, win_probability_enabled=False, deadline_passed=True
    )
    user = await _make_user(session, email="u@example.com", is_admin=False)
    await _make_entry(session, competition, user)
    async with _client_as(session, user) as ac:
        resp = await ac.get("/api/leaderboard/trophy-scenarios")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["scenarios"], list)
    assert isinstance(body["match_meta"], list)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_fail_open_returns_empty_lists_not_500(session: AsyncSession, monkeypatch):
    competition = await _make_competition(
        session, win_probability_enabled=False, deadline_passed=True
    )
    user = await _make_user(session, email="u@example.com", is_admin=False)
    await _make_entry(session, competition, user)

    async def _boom(_session):
        raise RuntimeError("simulator exploded")

    monkeypatch.setattr(win_probability_service, "get_win_probability", _boom)

    async with _client_as(session, user) as ac:
        resp = await ac.get("/api/leaderboard/trophy-scenarios")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["scenarios"] == []
    assert body["match_meta"] == []
