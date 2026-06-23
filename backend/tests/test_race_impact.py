"""Tests for race-impact — chart-annotation marker derivations."""
from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — registers all models so create_all sees every table
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score
from app.models._datetime import utc_now
from app.services.race_impact import compute_match_markers


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _seed_fixtures(session: AsyncSession) -> None:
    """Seed a minimal fixture set for most tests:

    - 3 KO FINISHED fixtures (round_of_16) → all 3 should appear as markers
    - 1 group-stage FINISHED fixture → must be excluded (not in SCORED_KO_STAGES)
    - 1 KO SCHEDULED fixture → must be excluded (not FINISHED)
    """
    comp = Competition(
        name="t",
        phase1_deadline=utc_now() - timedelta(days=1),
        is_phase2_active=False,
    )
    session.add(comp)
    await session.flush()

    base = utc_now() - timedelta(days=3)

    fixture_specs = [
        # (kickoff_offset, stage, home_team, away_team, status)
        (timedelta(0),       "round_of_16", "BRA", "ARG", MatchStatus.FINISHED),
        (timedelta(days=1),  "round_of_16", "FRA", "POR", MatchStatus.FINISHED),
        (timedelta(days=2),  "round_of_16", "GER", "NED", MatchStatus.FINISHED),
        (timedelta(0),       "group",        "USA", "CAN", MatchStatus.FINISHED),
        (timedelta(days=1),  "round_of_16", "ESP", "ITA", MatchStatus.SCHEDULED),
    ]

    for offset, stage, home, away, status in fixture_specs:
        f = Fixture(
            competition_id=comp.id,
            kickoff=base + offset,
            stage=stage,
            home_team=home,
            away_team=away,
            status=status,
        )
        session.add(f)
        await session.flush()

        # Attach a Score for every FINISHED fixture
        if status == MatchStatus.FINISHED:
            session.add(Score(fixture_id=f.id, home_score=2, away_score=1))

    await session.commit()


async def test_caps_at_3_markers(session: AsyncSession) -> None:
    """Even with 4+ finished KO fixtures, return at most 3 markers."""
    await _seed_fixtures(session)
    result = await compute_match_markers(session, days=14)
    assert len(result.markers) <= 3


async def test_group_fixtures_excluded(session: AsyncSession) -> None:
    """Group-stage fixtures don't appear in markers (KO-only rule)."""
    await _seed_fixtures(session)
    result = await compute_match_markers(session, days=14)
    for m in result.markers:
        assert m.home_team_code != "USA"


async def test_scheduled_fixtures_excluded(session: AsyncSession) -> None:
    """Only FINISHED fixtures are markers."""
    await _seed_fixtures(session)
    result = await compute_match_markers(session, days=14)
    for m in result.markers:
        assert "ESP" not in (m.home_team_code, m.away_team_code)


async def test_third_place_excluded(session: AsyncSession) -> None:
    """The bronze-medal playoff (stage=third_place) is unscored per CLAUDE.md invariant."""
    comp = Competition(
        name="t",
        phase1_deadline=utc_now() - timedelta(days=1),
        is_phase2_active=False,
    )
    session.add(comp)
    await session.flush()

    f = Fixture(
        competition_id=comp.id,
        kickoff=utc_now() - timedelta(days=1),
        stage="third_place",
        home_team="BEL",
        away_team="CRO",
        status=MatchStatus.FINISHED,
    )
    session.add(f)
    await session.flush()
    session.add(Score(fixture_id=f.id, home_score=2, away_score=1))
    await session.commit()

    result = await compute_match_markers(session, days=14)
    assert all(m.home_team_code != "BEL" for m in result.markers)


async def test_aware_utc(session: AsyncSession) -> None:
    """generated_at and each marker's kickoff must be timezone-aware (UTC)."""
    await _seed_fixtures(session)
    result = await compute_match_markers(session, days=14)
    assert result.generated_at.tzinfo is not None
    for m in result.markers:
        assert m.kickoff.tzinfo is not None
