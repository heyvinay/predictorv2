"""Knockout scoring gate + standings endpoint release (v2.181.1).

Two surfaces shipped together in 2.181.1:

* `Competition.knockout_scoring_enabled` — gates every advancement-point
  payout in `calculate_entry_points`. Default FALSE so the engine sits
  on group-stage match points only until an admin flips it.
* `GET /api/fixtures/standings/actual` — Phase 2 gate dropped, replaced
  with `post_deadline_live OR is_admin` (mirrors the V4 pages' rollout
  pattern). Admins always see; non-admins wait for the admin's "Go
  live" press.

In-memory SQLite per project convention; FastAPI dependency overrides
swap the session and the current user.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user
from app.main import app
from app.models.competition import Competition
from app.models.entry import (
    EntryStatus,
    PredictionEntry,
    PredictionEntryPhase,
)
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score, ScoreSource
from app.models.user import AuthProvider, User
from app.services.scoring import (
    calculate_entry_points,
    is_knockout_scoring_enabled,
)


KICKOFF = datetime(2026, 6, 28, 19, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fixed_scoring_config():
    """Pin the advancement ladder so payout asserts are deterministic."""
    config = {
        "mode": "fixed",
        "match": {"correct_outcome": 5, "exact_score": 10, "hybrid_cap": 10},
        "advancement": {
            "group_advance": 10,
            "group_position": 5,
            "round_of_32": 20,
            "round_of_16": 30,
            "quarter_final": 40,
            "semi_final": 50,
            "final": 75,
            "winner": 100,
        },
        "phase_multipliers": {"phase_1": 1.0, "phase_2": 0.7},
    }
    with patch("app.services.scoring.get_scoring_config", return_value=config):
        yield


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_competition(
    session: AsyncSession,
    *,
    post_deadline_live: bool = False,
    knockout_scoring_enabled: bool = False,
) -> Competition:
    comp = Competition(
        name="Test WC 2026",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
        post_deadline_live=post_deadline_live,
        knockout_scoring_enabled=knockout_scoring_enabled,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _make_user(
    session: AsyncSession, *, email: str, is_admin: bool = False
) -> User:
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


async def _make_entry_with_team_pick(
    session: AsyncSession,
    *,
    competition: Competition,
    user: User,
    pick_team: str,
    pick_stage: str,
) -> PredictionEntry:
    entry = PredictionEntry(
        user_id=user.id,
        competition_id=competition.id,
        reference="TEST01",
        display_name="entry",
        entry_number=1,
        is_disabled=False,
        withdrawn_at=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    phase = PredictionEntryPhase(
        entry_id=entry.id,
        phase=PredictionPhase.PHASE_1,
        status=EntryStatus.SUBMITTED,
    )
    session.add(phase)
    session.add(
        TeamPrediction(
            entry_id=entry.id,
            team=pick_team,
            stage=pick_stage,
            phase=PredictionPhase.PHASE_1,
        )
    )
    await session.commit()
    await session.refresh(entry)
    return entry


async def _seed_ko_fixture(
    session: AsyncSession,
    competition: Competition,
    *,
    stage: str,
    home: str,
    away: str,
) -> Fixture:
    fx = Fixture(
        competition_id=competition.id,
        home_team=home,
        away_team=away,
        kickoff=KICKOFF,
        stage=stage,
        group=None,
        status=MatchStatus.SCHEDULED,
    )
    session.add(fx)
    await session.commit()
    await session.refresh(fx)
    return fx


# ───────────────────────────────────────────────────────────────────────────
# is_knockout_scoring_enabled
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gate_returns_false_when_no_active_competition(session: AsyncSession):
    assert (await is_knockout_scoring_enabled(session)) is False


@pytest.mark.asyncio
async def test_gate_reflects_competition_flag(session: AsyncSession):
    await _make_competition(session, knockout_scoring_enabled=False)
    assert (await is_knockout_scoring_enabled(session)) is False


@pytest.mark.asyncio
async def test_gate_returns_true_when_flag_set(session: AsyncSession):
    await _make_competition(session, knockout_scoring_enabled=True)
    assert (await is_knockout_scoring_enabled(session)) is True


# ───────────────────────────────────────────────────────────────────────────
# calculate_entry_points respects the gate
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_advancement_points_zero_when_gate_off(session: AsyncSession):
    """Even a perfect bracket pick pays nothing while the gate is off."""
    competition = await _make_competition(session, knockout_scoring_enabled=False)
    user = await _make_user(session, email="u@example.com")
    entry = await _make_entry_with_team_pick(
        session,
        competition=competition,
        user=user,
        pick_team="Brazil",
        pick_stage="round_of_32",
    )
    # Brazil is seeded into R32 — lineup-credit would pay 20 if the gate were on.
    await _seed_ko_fixture(
        session, competition, stage="round_of_32", home="Brazil", away="Korea Republic"
    )

    breakdown = await calculate_entry_points(session, entry.id)
    assert breakdown.phase1.round_of_32_points == 0
    assert breakdown.phase1.group_advance_points == 0
    assert breakdown.phase1.group_position_points == 0


@pytest.mark.asyncio
async def test_advancement_points_pay_when_gate_on(session: AsyncSession):
    """Same fixture + same pick + gate ON → the R32 credit pays 20 points."""
    competition = await _make_competition(session, knockout_scoring_enabled=True)
    user = await _make_user(session, email="u@example.com")
    entry = await _make_entry_with_team_pick(
        session,
        competition=competition,
        user=user,
        pick_team="Brazil",
        pick_stage="round_of_32",
    )
    await _seed_ko_fixture(
        session, competition, stage="round_of_32", home="Brazil", away="Korea Republic"
    )

    breakdown = await calculate_entry_points(session, entry.id)
    assert breakdown.phase1.round_of_32_points == 20


@pytest.mark.asyncio
async def test_group_advance_pick_also_gated(session: AsyncSession):
    """group_advance / group_position payouts are gated too — not just
    knockout-stage credits. This is the load-bearing assertion: the gate
    holds the ENTIRE advancement-points block, not just R32-and-above."""
    competition = await _make_competition(session, knockout_scoring_enabled=False)
    user = await _make_user(session, email="u@example.com")
    entry = await _make_entry_with_team_pick(
        session,
        competition=competition,
        user=user,
        pick_team="Brazil",
        pick_stage="group",
    )
    # Brazil seeded into R32 → group_advance would normally pay 10.
    await _seed_ko_fixture(
        session, competition, stage="round_of_32", home="Brazil", away="Korea Republic"
    )

    breakdown = await calculate_entry_points(session, entry.id)
    assert breakdown.phase1.group_advance_points == 0


# ───────────────────────────────────────────────────────────────────────────
# GET /api/fixtures/standings/actual — gate
# ───────────────────────────────────────────────────────────────────────────


def _client_as(session: AsyncSession, current: User):
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current
    app.dependency_overrides[get_admin_user] = lambda: current
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_standings_endpoint_blocks_non_admin_pre_release(session: AsyncSession):
    await _make_competition(session, post_deadline_live=False)
    pleb = await _make_user(session, email="p@example.com")
    async with _client_as(session, pleb) as ac:
        resp = await ac.get("/api/fixtures/standings/actual")
        assert resp.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_standings_endpoint_opens_for_admin_pre_release(session: AsyncSession):
    """Admins always see standings, even before the go-live flip."""
    await _make_competition(session, post_deadline_live=False)
    admin = await _make_user(session, email="a@example.com", is_admin=True)
    async with _client_as(session, admin) as ac:
        resp = await ac.get("/api/fixtures/standings/actual")
        assert resp.status_code == 200
        payload = resp.json()
        assert "standings" in payload
        assert "qualifying_third_place" in payload
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_standings_endpoint_opens_for_pool_post_release(session: AsyncSession):
    await _make_competition(session, post_deadline_live=True)
    pleb = await _make_user(session, email="p@example.com")
    async with _client_as(session, pleb) as ac:
        resp = await ac.get("/api/fixtures/standings/actual")
        assert resp.status_code == 200
    app.dependency_overrides.clear()


# ───────────────────────────────────────────────────────────────────────────
# POST /api/admin/competition/knockout-scoring — admin toggle
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_toggle_flips_flag_and_persists(session: AsyncSession):
    competition = await _make_competition(session, knockout_scoring_enabled=False)
    admin = await _make_user(session, email="a@example.com", is_admin=True)
    async with _client_as(session, admin) as ac:
        resp = await ac.post(
            "/api/admin/competition/knockout-scoring", json={"enabled": True}
        )
        assert resp.status_code == 200
        assert resp.json()["knockout_scoring_enabled"] is True
    app.dependency_overrides.clear()

    await session.refresh(competition)
    assert competition.knockout_scoring_enabled is True


@pytest.mark.asyncio
async def test_admin_toggle_off_zeroes_advancement(session: AsyncSession):
    """End-to-end: flip ON, verify points pay, flip OFF via API, verify
    the same entry's payout drops back to zero — covers the
    audit-trail + cache-invalidate seam."""
    competition = await _make_competition(session, knockout_scoring_enabled=True)
    admin = await _make_user(session, email="a@example.com", is_admin=True)
    entry = await _make_entry_with_team_pick(
        session,
        competition=competition,
        user=admin,
        pick_team="Brazil",
        pick_stage="round_of_32",
    )
    await _seed_ko_fixture(
        session, competition, stage="round_of_32", home="Brazil", away="Korea Republic"
    )

    breakdown_on = await calculate_entry_points(session, entry.id)
    assert breakdown_on.phase1.round_of_32_points == 20

    async with _client_as(session, admin) as ac:
        resp = await ac.post(
            "/api/admin/competition/knockout-scoring", json={"enabled": False}
        )
        assert resp.status_code == 200
    app.dependency_overrides.clear()

    breakdown_off = await calculate_entry_points(session, entry.id)
    assert breakdown_off.phase1.round_of_32_points == 0
