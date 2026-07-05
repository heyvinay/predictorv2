"""Live projected-leaderboard overlay service tests (v2.198.0).

Conventions mirror test_leaderboard_v4.py: in-memory aiosqlite,
self-contained fixtures. `project_rows` is pure — no DB needed for those
two tests. The remaining tests exercise the DB-backed helpers directly
against a real in-memory session.
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardResponse, PointBreakdown
from app.services.live_projection import (
    _has_live_ko,
    _live_ko_advances,
    apply_live_projection,
    project_rows,
)


def _entry(name: str, total: int, exact: int = 0) -> LeaderboardEntry:
    return LeaderboardEntry(
        entry_id=uuid.uuid4(),
        entry_name=name,
        user_id=uuid.uuid4(),
        user_name=name,
        position=0,
        total_points=total,
        breakdown=PointBreakdown(),
        exact_scores=exact,
    )


def test_project_rows_reranks_and_leaves_banked_untouched():
    james = _entry("James", 512)
    sarah = _entry("Sarah", 498)
    kevin = _entry("Kevin", 470)
    banked = [james, sarah, kevin]  # banked order: James, Sarah, Kevin
    deltas = {kevin.entry_id: 30}  # Kevin's live pick advances → +30 → 500

    out = project_rows(banked, deltas)

    # New list of copies — inputs untouched (cache protection).
    assert banked[0].total_points == 512 and banked[0].projected_total is None
    # Re-ranked by projected total: James 512, Kevin 500, Sarah 498.
    assert [r.entry_name for r in out] == ["James", "Kevin", "Sarah"]
    kevin_out = next(r for r in out if r.entry_name == "Kevin")
    assert kevin_out.projected_total == 500
    assert kevin_out.live_delta == 30
    assert kevin_out.projected_position == 2
    assert kevin_out.total_points == 470  # banked stays banked


def test_project_rows_zero_delta_keeps_banked_order():
    rows = [_entry("A", 300), _entry("B", 200)]
    out = project_rows(rows, {})
    assert [r.projected_total for r in out] == [300, 200]
    assert [r.projected_position for r in out] == [1, 2]
    assert all(r.live_delta == 0 for r in out)


# ---------------------------------------------------------------------------
# Service-level integration tests
# ---------------------------------------------------------------------------


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
        name="Test World Cup",
        external_id="WC",
        is_active=True,
        phase1_deadline=datetime(2020, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
        knockout_scoring_enabled=True,
        live_projection_enabled=True,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


def _fixture(
    competition: Competition,
    *,
    home: str,
    away: str,
    stage: str,
    status: MatchStatus = MatchStatus.SCHEDULED,
) -> Fixture:
    return Fixture(
        competition_id=competition.id,
        home_team=home,
        away_team=away,
        kickoff=datetime(2026, 6, 15, 18, tzinfo=timezone.utc),
        stage=stage,
        status=status,
    )


@pytest.mark.asyncio
async def test_live_advance_uses_penalty_blind_scoreline(db_session, competition):
    fx = _fixture(
        competition,
        home="Brazil",
        away="Ghana",
        stage="round_of_32",
        status=MatchStatus.LIVE,
    )
    db_session.add(fx)
    await db_session.commit()
    await db_session.refresh(fx)

    # Regular-time scoreline favours Brazil, but a bogus in-progress
    # penalty tally (simulating a stray partial pen count while still
    # LIVE) favours Ghana. The decision must ignore the pens.
    db_session.add(
        Score(
            fixture_id=fx.id,
            home_score=1,
            away_score=0,
            home_penalties=1,
            away_penalties=2,
        )
    )
    await db_session.commit()

    advances = await _live_ko_advances(db_session)

    assert len(advances) == 1
    assert advances[0].team == "Brazil"
    assert advances[0].next_stage == "round_of_16"


@pytest.mark.asyncio
async def test_level_live_match_projects_nothing(db_session, competition):
    fx = _fixture(
        competition,
        home="Japan",
        away="Spain",
        stage="round_of_32",
        status=MatchStatus.LIVE,
    )
    db_session.add(fx)
    await db_session.commit()
    await db_session.refresh(fx)

    db_session.add(Score(fixture_id=fx.id, home_score=1, away_score=1))
    await db_session.commit()

    assert await _has_live_ko(db_session) is True
    assert await _live_ko_advances(db_session) == []


@pytest.mark.asyncio
async def test_gates_closed_returns_response_untouched(db_session):
    comp = Competition(
        name="Gated World Cup",
        is_active=True,
        knockout_scoring_enabled=False,
        live_projection_enabled=True,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)

    response = LeaderboardResponse(
        entries=[],
        last_calculated=datetime(2026, 6, 20, tzinfo=timezone.utc),
        total_participants=0,
    )

    out = await apply_live_projection(db_session, response)

    assert out.live_projection_active is False
    assert out is response
