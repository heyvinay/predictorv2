"""Tests for score_sync: windowing logic and the external-score apply path."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score
from app.services.external_scores import ExternalScore
from app.services.score_sync import (
    ScoreSyncResult,
    _apply_external_score,
    has_active_or_imminent_match,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), external_id="WC")
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


def _fixture(competition_id, *, kickoff: datetime, status: MatchStatus, ext: str) -> Fixture:
    return Fixture(
        competition_id=competition_id,
        external_id=ext,
        home_team="Mexico",
        away_team="South Africa",
        kickoff=kickoff,
        stage="group",
        group="A",
        status=status,
    )


NOW = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_returns_false_when_db_empty(session, competition) -> None:
    assert await has_active_or_imminent_match(session, now=NOW) is False


@pytest.mark.asyncio
async def test_returns_true_when_match_is_live(session, competition) -> None:
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(hours=1), status=MatchStatus.LIVE, ext="1"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_true_when_match_is_at_halftime(session, competition) -> None:
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(minutes=45), status=MatchStatus.HALFTIME, ext="2"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_true_for_imminent_kickoff_within_buffer(session, competition) -> None:
    # Kickoff in 9 minutes — within the 10-minute pre-kickoff buffer
    session.add(_fixture(competition.id, kickoff=NOW + timedelta(minutes=9), status=MatchStatus.SCHEDULED, ext="3"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_false_when_kickoff_is_far_away(session, competition) -> None:
    # Kickoff in 2 hours — outside the buffer
    session.add(_fixture(competition.id, kickoff=NOW + timedelta(hours=2), status=MatchStatus.SCHEDULED, ext="4"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is False


@pytest.mark.asyncio
async def test_returns_true_for_potentially_overrunning_match(session, competition) -> None:
    # Status still SCHEDULED but kickoff was 2 hours ago — could be a match
    # whose status didn't update from a missed poll. Buffer says yes-poll.
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(hours=2), status=MatchStatus.SCHEDULED, ext="5"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_false_when_match_finished_long_ago(session, competition) -> None:
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(days=1), status=MatchStatus.FINISHED, ext="6"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is False


# ---------------------------------------------------------------------------
# _apply_external_score: status transitions + idempotence
# ---------------------------------------------------------------------------


def _ext(status: MatchStatus, *, home: int = 1, away: int = 0, minute: int | None = None) -> ExternalScore:
    return ExternalScore(
        external_id="100",
        home_team="Mexico",
        away_team="South Africa",
        home_score=home,
        away_score=away,
        status=status,
        minute=minute,
    )


@pytest_asyncio.fixture
async def live_fixture(session: AsyncSession, competition: Competition) -> Fixture:
    f = _fixture(competition.id, kickoff=NOW - timedelta(hours=1), status=MatchStatus.LIVE, ext="100")
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


@pytest.mark.asyncio
async def test_apply_creates_score_and_flips_status_to_live(session, competition) -> None:
    f = _fixture(competition.id, kickoff=NOW, status=MatchStatus.SCHEDULED, ext="100")
    session.add(f)
    await session.commit()

    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.LIVE, minute=12), result)
    await session.commit()

    assert result.synced == 1
    assert f.status == MatchStatus.LIVE
    assert f.minute == 12
    score = (await session.execute(select(Score).where(Score.fixture_id == f.id))).scalar_one()
    assert (score.home_score, score.away_score) == (1, 0)


@pytest.mark.asyncio
async def test_apply_finished_transition_lands(session, competition, live_fixture) -> None:
    """LIVE → FINISHED with the same scoreline must still be applied — the
    status change alone is what releases scoring for the match."""
    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.LIVE, minute=88), result)
    await session.commit()

    result2 = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.FINISHED), result2)
    await session.commit()

    assert result2.updated == 1
    assert live_fixture.status == MatchStatus.FINISHED


@pytest.mark.asyncio
async def test_apply_identical_data_is_a_noop(session, competition, live_fixture) -> None:
    """Re-delivered FINISHED matches (the filter includes them every poll)
    must not count as updates or rewrite rows."""
    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.FINISHED), result)
    await session.commit()
    assert result.synced + result.updated == 1

    result2 = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.FINISHED), result2)
    await session.commit()

    assert result2.synced == 0
    assert result2.updated == 0


@pytest.mark.asyncio
async def test_apply_skips_verified_score(session, competition, live_fixture) -> None:
    session.add(Score(fixture_id=live_fixture.id, home_score=2, away_score=2, verified=True))
    live_fixture.status = MatchStatus.FINISHED
    await session.commit()

    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.LIVE, home=0, away=0), result)
    await session.commit()

    assert result.skipped_verified == 1
    score = (await session.execute(select(Score).where(Score.fixture_id == live_fixture.id))).scalar_one()
    assert (score.home_score, score.away_score) == (2, 2)
    assert live_fixture.status == MatchStatus.FINISHED
