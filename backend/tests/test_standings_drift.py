"""Standings drift verifier (v2.182.0).

Detect-only design: the verifier writes drift events; admins resolve.
Tests cover:
  * Pure compare_standings — agreement, position swap, points diff,
    different team sets.
  * Eligibility filter — only fully-FINISHED groups participate.
  * Admin endpoints — check + open list + dismiss flow.
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
from app.models.fixture import Fixture, MatchStatus
from app.models.standings_drift import (
    DriftEventStatus,
    StandingsDriftEvent,
    TrustedSource,
)
from app.models.user import AuthProvider, User
from app.services.standings_verify import (
    _football_data_to_normalized,
    _groups_with_all_matches_finished,
    _ours_to_normalized,
    compare_standings,
)


KICKOFF = datetime(2026, 6, 14, 17, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


# ───────────────────────────────────────────────────────────────────────────
# compare_standings — pure
# ───────────────────────────────────────────────────────────────────────────


def _row(team: str, position: int, points: int, gd: int = 0, gf: int = 0, ga: int = 0):
    return {
        "position": position,
        "team": team,
        "played": 3,
        "won": (points // 3),
        "drawn": (points % 3),
        "lost": 0,
        "points": points,
        "goals_for": gf,
        "goals_against": ga,
        "goal_difference": gd,
    }


def test_compare_returns_empty_when_standings_agree():
    standings = {
        "A": [_row("Mexico", 1, 9), _row("Korea", 2, 4),
              _row("S. Africa", 3, 3), _row("Czechia", 4, 1)],
    }
    assert compare_standings(standings, standings) == {}


def test_compare_detects_position_swap():
    ours = {"B": [_row("Switzerland", 1, 7), _row("Canada", 2, 4)]}
    theirs = {"B": [_row("Canada", 1, 7), _row("Switzerland", 2, 4)]}
    out = compare_standings(ours, theirs)
    assert "B" in out
    assert len(out) == 1


def test_compare_detects_points_difference():
    ours = {"C": [_row("Brazil", 1, 7), _row("Morocco", 2, 7)]}
    theirs = {"C": [_row("Brazil", 1, 9), _row("Morocco", 2, 7)]}
    out = compare_standings(ours, theirs)
    assert "C" in out


def test_compare_detects_different_team_sets():
    """Different team names in the same group position → drift."""
    ours = {"D": [_row("USA", 1, 6)]}
    theirs = {"D": [_row("Canada", 1, 6)]}
    assert "D" in compare_standings(ours, theirs)


def test_compare_only_returns_disagreeing_groups():
    """Agreement on A, disagreement on B → only B in output."""
    base = [_row("Team1", 1, 9), _row("Team2", 2, 6)]
    other = [_row("Team1", 1, 9), _row("Team2", 2, 7)]  # diff points
    ours = {"A": base, "B": base}
    theirs = {"A": base, "B": other}
    out = compare_standings(ours, theirs)
    assert set(out.keys()) == {"B"}


# ───────────────────────────────────────────────────────────────────────────
# Football-Data normalizer
# ───────────────────────────────────────────────────────────────────────────


def test_football_data_normalizer_maps_field_names():
    payload = [
        {
            "group": "Group A",
            "stage": "ALL",
            "type": "TOTAL",
            "table": [
                {
                    "position": 1,
                    "team": {"name": "Mexico"},
                    "playedGames": 3,
                    "won": 3,
                    "draw": 0,
                    "lost": 0,
                    "points": 9,
                    "goalsFor": 7,
                    "goalsAgainst": 1,
                    "goalDifference": 6,
                },
            ],
        }
    ]
    out = _football_data_to_normalized(payload)
    assert "A" in out
    row = out["A"][0]
    assert row["team"] == "Mexico"
    assert row["drawn"] == 0  # mapped from `draw`
    assert row["goals_for"] == 7
    assert row["goal_difference"] == 6


def test_football_data_normalizer_skips_non_total_tables():
    """Football-Data also returns HOME and AWAY tables — we want TOTAL only."""
    payload = [
        {"group": "Group A", "type": "HOME", "table": [
            {"position": 1, "team": {"name": "X"}, "points": 99,
             "playedGames": 3, "won": 0, "draw": 0, "lost": 0,
             "goalsFor": 0, "goalsAgainst": 0, "goalDifference": 0}
        ]}
    ]
    out = _football_data_to_normalized(payload)
    assert out == {}


# ───────────────────────────────────────────────────────────────────────────
# Eligibility filter — only fully-FINISHED groups
# ───────────────────────────────────────────────────────────────────────────


async def _add_fixture(
    session: AsyncSession,
    comp_id,
    *,
    group: str,
    home: str,
    away: str,
    status: MatchStatus,
):
    fx = Fixture(
        competition_id=comp_id,
        home_team=home,
        away_team=away,
        kickoff=KICKOFF,
        stage="group",
        group=group,
        status=status,
    )
    session.add(fx)
    await session.commit()


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(
        name="WC", external_id="WC", is_active=True,
        created_at=KICKOFF, updated_at=KICKOFF, max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


@pytest.mark.asyncio
async def test_eligibility_includes_only_fully_finished_groups(
    session: AsyncSession, competition: Competition
):
    # Group A: 2 finished, 1 scheduled → NOT eligible.
    await _add_fixture(session, competition.id, group="A", home="X", away="Y", status=MatchStatus.FINISHED)
    await _add_fixture(session, competition.id, group="A", home="Y", away="Z", status=MatchStatus.FINISHED)
    await _add_fixture(session, competition.id, group="A", home="X", away="Z", status=MatchStatus.SCHEDULED)

    # Group B: all FINISHED → eligible.
    await _add_fixture(session, competition.id, group="B", home="P", away="Q", status=MatchStatus.FINISHED)
    await _add_fixture(session, competition.id, group="B", home="Q", away="R", status=MatchStatus.FINISHED)
    await _add_fixture(session, competition.id, group="B", home="P", away="R", status=MatchStatus.FINISHED)

    # Group C: 1 LIVE → NOT eligible.
    await _add_fixture(session, competition.id, group="C", home="A", away="B", status=MatchStatus.LIVE)

    eligible = await _groups_with_all_matches_finished(session)
    assert eligible == {"B"}


# ───────────────────────────────────────────────────────────────────────────
# Admin endpoints — full HTTP round-trip
# ───────────────────────────────────────────────────────────────────────────


async def _make_user(session: AsyncSession, *, email: str, is_admin: bool = False) -> User:
    u = User(
        email=email, name="T", password_hash="x",
        auth_provider=AuthProvider.EMAIL, is_active=True, is_admin=is_admin,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _client_as(session: AsyncSession, current: User):
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current
    app.dependency_overrides[get_admin_user] = lambda: current
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_admin_check_endpoint_no_event_when_no_eligible_groups(
    session: AsyncSession, competition: Competition
):
    """Empty DB + competition with no FINISHED fixtures → check is a no-op."""
    admin = await _make_user(session, email="a@example.com", is_admin=True)
    async with _client_as(session, admin) as ac:
        resp = await ac.post("/api/admin/standings-drift/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source_used"] is None
        assert body["disagreement_count"] == 0
        assert body["created_event_id"] is None
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_open_list_returns_existing_open_events(
    session: AsyncSession, competition: Competition
):
    """Hand-create an open drift event; the list endpoint surfaces it."""
    event = StandingsDriftEvent(
        competition_id=competition.id,
        trusted_source=TrustedSource.FOOTBALL_DATA,
        groups_disagreeing={"groups": {"K": {"ours": [], "theirs": []}}},
        status=DriftEventStatus.OPEN,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    admin = await _make_user(session, email="a@example.com", is_admin=True)
    async with _client_as(session, admin) as ac:
        resp = await ac.get("/api/admin/standings-drift/open")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["id"] == str(event.id)
        assert items[0]["trusted_source"] == "FOOTBALL_DATA"
        assert items[0]["disagreement_count"] == 1
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_dismiss_closes_event_with_audit(
    session: AsyncSession, competition: Competition
):
    event = StandingsDriftEvent(
        competition_id=competition.id,
        trusted_source=TrustedSource.FOOTBALL_DATA,
        groups_disagreeing={"groups": {"K": {"ours": [], "theirs": []}}},
        status=DriftEventStatus.OPEN,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    admin = await _make_user(session, email="a@example.com", is_admin=True)
    async with _client_as(session, admin) as ac:
        resp = await ac.post(
            f"/api/admin/standings-drift/{event.id}/dismiss",
            json={"status": "DISMISSED_OURS_CORRECT", "note": "verified manually"},
        )
        assert resp.status_code == 200
    app.dependency_overrides.clear()

    await session.refresh(event)
    assert event.status == DriftEventStatus.DISMISSED_OURS_CORRECT
    assert event.resolution_note == "verified manually"
    assert event.resolved_at is not None
    assert event.resolved_by_user_id == admin.id


@pytest.mark.asyncio
async def test_double_dismiss_returns_409(
    session: AsyncSession, competition: Competition
):
    """Dismissing an already-closed event returns 409 not 200."""
    event = StandingsDriftEvent(
        competition_id=competition.id,
        trusted_source=TrustedSource.FOOTBALL_DATA,
        groups_disagreeing={"groups": {}},
        status=DriftEventStatus.DISMISSED_TRANSIENT,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    admin = await _make_user(session, email="a@example.com", is_admin=True)
    async with _client_as(session, admin) as ac:
        resp = await ac.post(
            f"/api/admin/standings-drift/{event.id}/dismiss",
            json={"status": "DISMISSED_OURS_CORRECT"},
        )
        assert resp.status_code == 409
    app.dependency_overrides.clear()
