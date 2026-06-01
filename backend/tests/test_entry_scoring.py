"""Tests for entry-based scoring, leaderboard, snapshots.

Covers the Task D contract:
- `calculate_entry_points(entry_id)` isolates points to one entry
- `calculate_leaderboard()` returns one row per eligible entry
- Withdrawn / disabled / draft / ready entries are excluded
- Snapshot trajectory + climbers are entry-keyed
- Movement uses yesterday's snapshot by entry_id

Uses in-memory SQLite per the project convention.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

# Ensure every model is registered with SQLModel.metadata.
import app.models  # noqa: F401
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score, ScoreSource
from app.models.user import AuthProvider, User
from app.services import leaderboard as leaderboard_service
from app.services.leaderboard import calculate_leaderboard
from app.services.scoring import calculate_entry_points
from app.services.snapshots import (
    get_entry_trajectory,
    get_steepest_climbers,
)


# ---------------------------------------------------------------------------
# Fixed-mode scoring config so test expectations are deterministic.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _fixed_scoring_config():
    """Force fixed scoring (no hybrid rarity bonus) for deterministic asserts."""
    config = {
        "mode": "fixed",
        "match": {"correct_outcome": 5, "exact_score": 10, "hybrid_cap": 10},
        # Bracket points bumped 2026-06-01 to match the /rules page —
        # 20/30/40/50/75/100 ladder (was 10/15/20/40/60/100).
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


@pytest.fixture(autouse=True)
def _clear_leaderboard_cache():
    """Fresh in-memory leaderboard cache per test."""
    leaderboard_service.invalidate_cache()
    yield
    leaderboard_service.invalidate_cache()


# ---------------------------------------------------------------------------
# DB / model fixtures
# ---------------------------------------------------------------------------
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
    comp = Competition(
        name="Test WC 2026",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


@pytest_asyncio.fixture
async def alice(session: AsyncSession) -> User:
    u = User(
        email="alice@example.com",
        name="Alice",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


@pytest_asyncio.fixture
async def bob(session: AsyncSession) -> User:
    u = User(
        email="bob@example.com",
        name="Bob",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


@pytest_asyncio.fixture
async def finished_fixture(
    session: AsyncSession, competition: Competition
) -> Fixture:
    """Brazil 2-1 Germany — Brazil wins (outcome = '1')."""
    f = Fixture(
        competition_id=competition.id,
        home_team="Brazil",
        away_team="Germany",
        kickoff=datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
        stage="group",
        group="A",
        status=MatchStatus.FINISHED,
    )
    session.add(f)
    await session.commit()
    await session.refresh(f)

    score = Score(
        fixture_id=f.id,
        home_score=2,
        away_score=1,
        source=ScoreSource.MANUAL,
        verified=True,
    )
    session.add(score)
    await session.commit()
    return f


# ---------------------------------------------------------------------------
# Helpers — construct an entry directly without going through the service
# layer so each test can pinpoint a single field (status, withdrawn, etc.).
# ---------------------------------------------------------------------------
async def _make_entry(
    session: AsyncSession,
    *,
    user: User,
    competition: Competition,
    entry_number: int = 1,
    display_name: str | None = None,
    status: EntryStatus = EntryStatus.SUBMITTED,
    is_disabled: bool = False,
    withdrawn_at: datetime | None = None,
) -> PredictionEntry:
    """Construct an entry + its phase rows. Status is applied to both
    phase_1 and phase_2 unless overridden later in the test."""
    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{entry_number:06d}-{uuid.uuid4().hex[:4]}",
        display_name=display_name or f"Entry {entry_number}",
        entry_number=entry_number,
        is_disabled=is_disabled,
        withdrawn_at=withdrawn_at,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    for phase in (PredictionPhase.PHASE_1, PredictionPhase.PHASE_2):
        session.add(
            PredictionEntryPhase(
                entry_id=entry.id,
                phase=phase,
                status=status,
            )
        )
    await session.commit()
    await session.refresh(entry)
    return entry


async def _add_match_pick(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    fixture: Fixture,
    home: int,
    away: int,
    phase: PredictionPhase = PredictionPhase.PHASE_1,
) -> MatchPrediction:
    pred = MatchPrediction(
        entry_id=entry.id,
        fixture_id=fixture.id,
        home_score=home,
        away_score=away,
        phase=phase,
    )
    session.add(pred)
    await session.commit()
    await session.refresh(pred)
    return pred


# ---------------------------------------------------------------------------
# 1. Two entries from one user have independent points
# ---------------------------------------------------------------------------
class TestEntryPointsIsolation:
    async def test_two_entries_same_user_independent_points(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        finished_fixture: Fixture,
    ):
        """Same user, same fixture, divergent picks → different totals."""
        e1 = await _make_entry(
            session, user=alice, competition=competition, entry_number=1
        )
        e2 = await _make_entry(
            session, user=alice, competition=competition, entry_number=2
        )

        # Brazil 2-1 actual. e1 picks 2-1 (exact); e2 picks 3-0 (correct
        # outcome only).
        await _add_match_pick(
            session, entry=e1, fixture=finished_fixture, home=2, away=1
        )
        await _add_match_pick(
            session, entry=e2, fixture=finished_fixture, home=3, away=0
        )

        b1 = await calculate_entry_points(session, e1.id)
        b2 = await calculate_entry_points(session, e2.id)

        # Exact score: 5 outcome + 10 exact = 15
        assert b1.total == 15
        # Correct outcome only: 5
        assert b2.total == 5
        assert b1.total != b2.total


# ---------------------------------------------------------------------------
# 2. Withdrawn entries excluded
# ---------------------------------------------------------------------------
class TestEligibilityFilters:
    async def test_withdrawn_entry_excluded_from_leaderboard(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        finished_fixture: Fixture,
    ):
        live = await _make_entry(
            session, user=alice, competition=competition, entry_number=1
        )
        withdrawn = await _make_entry(
            session,
            user=alice,
            competition=competition,
            entry_number=2,
            withdrawn_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        await _add_match_pick(
            session, entry=live, fixture=finished_fixture, home=2, away=1
        )
        await _add_match_pick(
            session, entry=withdrawn, fixture=finished_fixture, home=2, away=1
        )

        board = await calculate_leaderboard(session, force_refresh=True)
        ids = [row.entry_id for row in board.entries]
        assert live.id in ids
        assert withdrawn.id not in ids

    async def test_disabled_entry_excluded_from_leaderboard(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        finished_fixture: Fixture,
    ):
        live = await _make_entry(
            session, user=alice, competition=competition, entry_number=1
        )
        disabled = await _make_entry(
            session,
            user=alice,
            competition=competition,
            entry_number=2,
            is_disabled=True,
        )
        await _add_match_pick(
            session, entry=live, fixture=finished_fixture, home=2, away=1
        )
        await _add_match_pick(
            session, entry=disabled, fixture=finished_fixture, home=2, away=1
        )

        board = await calculate_leaderboard(session, force_refresh=True)
        ids = [row.entry_id for row in board.entries]
        assert live.id in ids
        assert disabled.id not in ids

    async def test_draft_entries_excluded_from_leaderboard(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        finished_fixture: Fixture,
    ):
        """Only SUBMITTED entries appear on the leaderboard; DRAFT is excluded.

        The old 'ready'/'locked' statuses were removed in the 6→3 lifecycle
        simplification. WITHDRAWN exclusion is covered by
        test_withdrawn_entry_excluded_from_leaderboard.
        """
        submitted = await _make_entry(
            session,
            user=alice,
            competition=competition,
            entry_number=1,
            status=EntryStatus.SUBMITTED,
        )
        draft = await _make_entry(
            session,
            user=alice,
            competition=competition,
            entry_number=2,
            status=EntryStatus.DRAFT,
        )
        for entry in (submitted, draft):
            await _add_match_pick(
                session, entry=entry, fixture=finished_fixture, home=2, away=1
            )

        board = await calculate_leaderboard(session, force_refresh=True)
        ids = [row.entry_id for row in board.entries]
        assert ids == [submitted.id]


# ---------------------------------------------------------------------------
# 3. Entry trajectory + climbers grouped by entry
# ---------------------------------------------------------------------------
class TestSnapshots:
    async def test_entry_trajectory_isolated(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
    ):
        """Trajectory queries return only the requested entry's snapshots."""
        e1 = await _make_entry(
            session, user=alice, competition=competition, entry_number=1
        )
        e2 = await _make_entry(
            session, user=alice, competition=competition, entry_number=2
        )

        today = date.today()
        yesterday = today - timedelta(days=1)

        session.add_all(
            [
                LeaderboardSnapshot(
                    user_id=alice.id,
                    entry_id=e1.id,
                    position=1,
                    total_points=20,
                    captured_date=yesterday,
                ),
                LeaderboardSnapshot(
                    user_id=alice.id,
                    entry_id=e1.id,
                    position=2,
                    total_points=25,
                    captured_date=today,
                ),
                LeaderboardSnapshot(
                    user_id=alice.id,
                    entry_id=e2.id,
                    position=5,
                    total_points=8,
                    captured_date=today,
                ),
            ]
        )
        await session.commit()

        e1_traj = await get_entry_trajectory(session, e1.id, days=7)
        assert [s.position for s in e1_traj] == [1, 2]

        e2_traj = await get_entry_trajectory(session, e2.id, days=7)
        assert [s.position for s in e2_traj] == [5]

    async def test_climbers_grouped_by_entry_one_user_can_appear_twice(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
    ):
        """Two entries from one user can both appear in the climbers list
        — entries are the unit, not users."""
        e1 = await _make_entry(
            session, user=alice, competition=competition, entry_number=1
        )
        e2 = await _make_entry(
            session, user=alice, competition=competition, entry_number=2
        )

        today = date.today()
        a_week_ago = today - timedelta(days=6)

        # e1 climbed 10 → 3 (7 places); e2 climbed 8 → 2 (6 places).
        session.add_all(
            [
                LeaderboardSnapshot(
                    user_id=alice.id,
                    entry_id=e1.id,
                    position=10,
                    total_points=5,
                    captured_date=a_week_ago,
                ),
                LeaderboardSnapshot(
                    user_id=alice.id,
                    entry_id=e1.id,
                    position=3,
                    total_points=40,
                    captured_date=today,
                ),
                LeaderboardSnapshot(
                    user_id=alice.id,
                    entry_id=e2.id,
                    position=8,
                    total_points=10,
                    captured_date=a_week_ago,
                ),
                LeaderboardSnapshot(
                    user_id=alice.id,
                    entry_id=e2.id,
                    position=2,
                    total_points=45,
                    captured_date=today,
                ),
            ]
        )
        await session.commit()

        climbers = await get_steepest_climbers(session, days=7, limit=5)
        ids = [c["entry_id"] for c in climbers]
        assert e1.id in ids
        assert e2.id in ids
        # Both rows belong to Alice — confirming a user shows up twice.
        assert all(c["user_id"] == alice.id for c in climbers)


# ---------------------------------------------------------------------------
# 4. Zero predictions returns a zero breakdown
# ---------------------------------------------------------------------------
class TestEdgeCases:
    async def test_calculate_entry_points_no_predictions_is_zero(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
    ):
        entry = await _make_entry(
            session, user=alice, competition=competition, entry_number=1
        )
        breakdown = await calculate_entry_points(session, entry.id)
        assert breakdown.total == 0
        assert breakdown.correct_outcomes == 0
        assert breakdown.exact_scores == 0
        assert breakdown.total_predictions == 0


# ---------------------------------------------------------------------------
# 5. Movement uses yesterday's snapshot by entry_id
# ---------------------------------------------------------------------------
class TestMovement:
    async def test_movement_uses_previous_leaderboard_position_by_entry(
        self,
        session: AsyncSession,
        alice: User,
        bob: User,
        competition: Competition,
        finished_fixture: Fixture,
    ):
        """Movement is computed against the cached previous position keyed
        by entry_id. Two consecutive leaderboard calls with a swap in order
        should produce positive/negative movement values for the swapped
        entries."""
        e_alice = await _make_entry(
            session, user=alice, competition=competition, entry_number=1
        )
        e_bob = await _make_entry(
            session, user=bob, competition=competition, entry_number=1
        )

        # First pass: Bob exact (15), Alice outcome only (5). Bob leads.
        await _add_match_pick(
            session, entry=e_alice, fixture=finished_fixture, home=3, away=0
        )
        await _add_match_pick(
            session, entry=e_bob, fixture=finished_fixture, home=2, away=1
        )

        first = await calculate_leaderboard(session, force_refresh=True)
        positions = {row.entry_id: row.position for row in first.entries}
        assert positions[e_bob.id] == 1
        assert positions[e_alice.id] == 2
        # No prior cache → movement should be 0 on first pass.
        for row in first.entries:
            assert row.movement == 0

        # Flip the picks so Alice now has the exact score and Bob doesn't.
        await session.execute(
            MatchPrediction.__table__.update()
            .where(MatchPrediction.entry_id == e_alice.id)
            .values(home_score=2, away_score=1)
        )
        await session.execute(
            MatchPrediction.__table__.update()
            .where(MatchPrediction.entry_id == e_bob.id)
            .values(home_score=3, away_score=0)
        )
        await session.commit()

        second = await calculate_leaderboard(session, force_refresh=True)
        movements = {row.entry_id: row.movement for row in second.entries}
        # Alice climbed from 2 → 1, +1 (positive = up).
        assert movements[e_alice.id] == 1
        # Bob fell from 1 → 2, -1.
        assert movements[e_bob.id] == -1
