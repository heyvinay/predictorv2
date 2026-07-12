"""GET /api/leaderboard/consensus-bracket — per-stage pool pick counts +
actual result per team. Service-level (calls the endpoint fn directly),
same in-memory-DB pattern as test_champion_survival.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.api.leaderboard import consensus_bracket
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score
from app.models.user import AuthProvider, User

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


def _user() -> User:
    # consensus-bracket is public (no admin check); a bare user is enough.
    return User(email="v@test.com", name="V", auth_provider=AuthProvider.EMAIL, is_admin=False)


async def _comp(session: AsyncSession, *, deadline_passed: bool = True) -> Competition:
    deadline = (
        datetime.now(tz=timezone.utc) - timedelta(hours=1)
        if deadline_passed
        else datetime.now(tz=timezone.utc) + timedelta(days=1)
    )
    comp = Competition(
        name="WC26",
        external_id="WC2026",
        is_active=True,
        phase1_deadline=deadline,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.flush()
    return comp


async def _entry_with_picks(
    session: AsyncSession, comp: Competition, picks: dict[str, list[str]]
) -> PredictionEntry:
    """picks = {team: [stages the entry predicted it to reach]}."""
    user = User(
        email=f"u{uuid.uuid4().hex[:6]}@test.com",
        name="U",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(user)
    await session.flush()
    entry = PredictionEntry(
        competition_id=comp.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6]}",
        display_name="Entry",
        entry_number=1,
    )
    session.add(entry)
    await session.flush()
    session.add(
        PredictionEntryPhase(
            entry_id=entry.id, phase=PredictionPhase.PHASE_1, status=EntryStatus.SUBMITTED
        )
    )
    for team, stages in picks.items():
        for stage in stages:
            session.add(
                TeamPrediction(
                    entry_id=entry.id, phase=PredictionPhase.PHASE_1, team=team, stage=stage
                )
            )
    await session.flush()
    return entry


KO = ["round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "winner"]


async def test_counts_picks_per_stage_and_wires_actual_result(session: AsyncSession):
    comp = await _comp(session)
    # A: Spain all the way to champion. B: Spain to the semis. C: France to R16.
    await _entry_with_picks(session, comp, {"Spain": KO})
    await _entry_with_picks(session, comp, {"Spain": KO[:4]})  # r32..sf
    await _entry_with_picks(session, comp, {"France": KO[:2]})  # r32, r16
    # D picks Croatia only to the R32 — Croatia never appears in a KO fixture.
    await _entry_with_picks(session, comp, {"Croatia": ["round_of_32"]})

    # Actual results: Spain reached the semi-final then lost (eliminated).
    sf = Fixture(
        competition_id=comp.id,
        home_team="Spain",
        away_team="England",
        kickoff=datetime.now(tz=timezone.utc) - timedelta(days=1),
        stage="semi_final",
        status=MatchStatus.FINISHED,
    )
    session.add(sf)
    await session.flush()
    session.add(Score(fixture_id=sf.id, home_score=0, away_score=1))  # Spain out
    await session.commit()

    res = await consensus_bracket(session=session, user=_user())
    assert res.eligible_count == 4
    by_team = {r.team: r for r in res.rows}

    spain = by_team["Spain"]
    assert spain.picks_by_stage == {
        "round_of_32": 2,
        "round_of_16": 2,
        "quarter_final": 2,
        "semi_final": 2,
        "final": 1,
        "winner": 1,
    }
    assert spain.actual_stage == "semi_final"
    assert spain.alive is False  # lost the semi

    # Croatia never reached a knockout fixture → actual_stage is None.
    assert by_team["Croatia"].actual_stage is None
    assert by_team["Croatia"].picks_by_stage == {"round_of_32": 1}


async def test_empty_before_deadline_locks(session: AsyncSession):
    comp = await _comp(session, deadline_passed=False)
    await _entry_with_picks(session, comp, {"Spain": KO})
    await session.commit()

    res = await consensus_bracket(session=session, user=_user())
    assert res.rows == []
    assert res.eligible_count == 0
