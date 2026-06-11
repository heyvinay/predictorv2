"""V4 leaderboard row fields (v2.164.0).

Service-level tests for the additive `LeaderboardEntry` fields that feed
the V4 /leaderboard frontend: employer pool, champion / finalist picks
with alive flags, and snapshot-based daily movement.

Conventions mirror test_leaderboard_admin_gate.py: in-memory aiosqlite,
self-contained fixtures, cache cleared around every test.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score
from app.models.user import AuthProvider, Employer, User
from app.services import leaderboard as leaderboard_service
from app.services.leaderboard import calculate_leaderboard, get_eliminated_teams


@pytest.fixture(autouse=True)
def _clear_leaderboard_cache():
    leaderboard_service.invalidate_cache()
    yield
    leaderboard_service.invalidate_cache()


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
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


async def _make_entry(
    db_session: AsyncSession,
    competition: Competition,
    *,
    email: str,
    employer: Employer | None = None,
    entry_number: int = 1,
) -> PredictionEntry:
    user = User(
        email=email,
        name=email.split("@")[0].title(),
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        employer=employer,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6]}",
        display_name=f"{user.name}'s Entry",
        entry_number=entry_number,
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    db_session.add(
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.SUBMITTED,
        )
    )
    await db_session.commit()
    return entry


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


# ---------------------------------------------------------------------------
# V4 row fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v4_fields_present(db_session, competition):
    entry = await _make_entry(
        db_session, competition, email="alice@example.com", employer=Employer.ATLAS
    )
    db_session.add_all(
        [
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="winner"),
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="final"),
            TeamPrediction(entry_id=entry.id, team="France", stage="final"),
        ]
    )
    await db_session.commit()

    board = await calculate_leaderboard(db_session, force_refresh=True)
    assert len(board.entries) == 1
    row = board.entries[0]
    assert row.employer == "atlas"
    assert row.champion_pick == "Brazil"
    assert row.champion_alive is True
    assert sorted(row.finalist_picks) == ["Brazil", "France"]
    assert row.finalists_alive == 2
    assert row.daily_movement is None  # no snapshots yet


@pytest.mark.asyncio
async def test_employer_none_and_neither(db_session, competition):
    await _make_entry(db_session, competition, email="guest@example.com")
    await _make_entry(
        db_session, competition, email="ext@example.com", employer=Employer.NEITHER
    )
    board = await calculate_leaderboard(db_session, force_refresh=True)
    employers = sorted(str(e.employer) for e in board.entries)
    assert employers == ["None", "neither"]


@pytest.mark.asyncio
async def test_phase2_team_predictions_ignored(db_session, competition):
    entry = await _make_entry(db_session, competition, email="alice@example.com")
    db_session.add_all(
        [
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="winner"),
            # Dormant phase_2 row must never leak into the V4 fields.
            TeamPrediction(
                entry_id=entry.id,
                team="Germany",
                stage="winner",
                phase=PredictionPhase.PHASE_2,
            ),
        ]
    )
    await db_session.commit()

    board = await calculate_leaderboard(db_session, force_refresh=True)
    assert board.entries[0].champion_pick == "Brazil"


# ---------------------------------------------------------------------------
# Elimination logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ko_loser_eliminated(db_session, competition):
    fx = _fixture(
        competition,
        home="Brazil",
        away="Germany",
        stage="quarter_final",
        status=MatchStatus.FINISHED,
    )
    db_session.add(fx)
    await db_session.commit()
    db_session.add(Score(fixture_id=fx.id, home_score=2, away_score=1))
    await db_session.commit()

    eliminated = await get_eliminated_teams(db_session)
    assert eliminated == {"Germany"}


@pytest.mark.asyncio
async def test_ko_loss_kills_champion_pick(db_session, competition):
    entry = await _make_entry(db_session, competition, email="alice@example.com")
    db_session.add_all(
        [
            TeamPrediction(entry_id=entry.id, team="Germany", stage="winner"),
            TeamPrediction(entry_id=entry.id, team="Germany", stage="final"),
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="final"),
        ]
    )
    fx = _fixture(
        competition,
        home="Brazil",
        away="Germany",
        stage="semi_final",
        status=MatchStatus.FINISHED,
    )
    db_session.add(fx)
    await db_session.commit()
    db_session.add(Score(fixture_id=fx.id, home_score=1, away_score=0))
    await db_session.commit()

    board = await calculate_leaderboard(db_session, force_refresh=True)
    row = board.entries[0]
    assert row.champion_alive is False
    assert row.finalists_alive == 1  # Brazil still alive


@pytest.mark.asyncio
async def test_group_nonqualifier_eliminated_when_r32_real(db_session, competition):
    # Four group teams; two reach a fully seeded R32.
    db_session.add_all(
        [
            _fixture(competition, home="Brazil", away="Egypt", stage="group",
                     status=MatchStatus.FINISHED),
            _fixture(competition, home="France", away="Italy", stage="group",
                     status=MatchStatus.FINISHED),
            _fixture(competition, home="Brazil", away="France", stage="round_of_32"),
        ]
    )
    await db_session.commit()

    eliminated = await get_eliminated_teams(db_session)
    assert eliminated == {"Egypt", "Italy"}


@pytest.mark.asyncio
async def test_no_group_elimination_while_r32_has_placeholders(
    db_session, competition
):
    db_session.add_all(
        [
            _fixture(competition, home="Brazil", away="Egypt", stage="group",
                     status=MatchStatus.FINISHED),
            # Placeholder lineup name → round not fully real yet.
            _fixture(competition, home="Brazil", away="Winner of Match 12",
                     stage="round_of_32"),
        ]
    )
    await db_session.commit()

    eliminated = await get_eliminated_teams(db_session)
    assert eliminated == set()


@pytest.mark.asyncio
async def test_no_group_elimination_without_r32_fixtures(db_session, competition):
    db_session.add(
        _fixture(competition, home="Brazil", away="Egypt", stage="group",
                 status=MatchStatus.FINISHED)
    )
    await db_session.commit()
    assert await get_eliminated_teams(db_session) == set()


# ---------------------------------------------------------------------------
# Daily movement from snapshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daily_movement_from_yesterday_snapshot(db_session, competition):
    alice = await _make_entry(db_session, competition, email="alice@example.com")
    bob = await _make_entry(db_session, competition, email="bob@example.com")

    today = datetime.now(timezone.utc).date()
    db_session.add_all(
        [
            # Alice was #2 yesterday, #5 two days ago — yesterday wins.
            LeaderboardSnapshot(
                user_id=alice.user_id, entry_id=alice.id, position=5,
                total_points=0, captured_date=today - timedelta(days=2),
            ),
            LeaderboardSnapshot(
                user_id=alice.user_id, entry_id=alice.id, position=2,
                total_points=0, captured_date=today - timedelta(days=1),
            ),
            # A today-snapshot must NOT count as "yesterday".
            LeaderboardSnapshot(
                user_id=bob.user_id, entry_id=bob.id, position=9,
                total_points=0, captured_date=today,
            ),
        ]
    )
    await db_session.commit()

    board = await calculate_leaderboard(db_session, force_refresh=True)
    by_id = {e.entry_id: e for e in board.entries}
    # Both entries have 0 points → tied at position 1.
    assert by_id[alice.id].daily_movement == 2 - by_id[alice.id].position
    assert by_id[bob.id].daily_movement is None
