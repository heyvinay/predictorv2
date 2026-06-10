"""Batched outcome counts + single-flight leaderboard rebuild (v2.161.0).

Pins the performance refactor's behavioural contracts:

1. `get_all_outcome_counts` equals manual per-fixture counting and only
   counts ELIGIBLE entries' predictions (SUBMITTED, not disabled, not
   withdrawn) — the rarity-eligibility product decision.
2. `calculate_entry_points` returns identical breakdowns with and without
   the precomputed caches.
3. Leaderboard rows read correct_outcomes / exact_scores straight from the
   breakdown (the redundant per-entry stats query was deleted).
4. Concurrent cold loads trigger exactly ONE rebuild (single-flight lock).
5. A DRAFT entry's own breakdown never crashes — base points pay, rarity
   is 0 because its predictions are outside the eligible-only counts.

Uses in-memory SQLite per the project convention.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score, ScoreSource
from app.models.user import AuthProvider, User
from app.services import leaderboard as leaderboard_service
from app.services.leaderboard import calculate_leaderboard
from app.services.scoring import (
    calculate_entry_points,
    get_actual_advancement,
    get_all_outcome_counts,
)


@pytest.fixture(autouse=True)
def _fixed_scoring_config():
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


@pytest.fixture(autouse=True)
def _clear_leaderboard_cache():
    leaderboard_service.invalidate_cache()
    yield
    leaderboard_service.invalidate_cache()


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


async def _make_entry(
    session: AsyncSession,
    *,
    user: User,
    competition: Competition,
    entry_number: int = 1,
    status: EntryStatus = EntryStatus.SUBMITTED,
    is_disabled: bool = False,
    withdrawn_at: datetime | None = None,
) -> PredictionEntry:
    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{entry_number:06d}-{uuid.uuid4().hex[:4]}",
        display_name=f"Entry {entry_number}",
        entry_number=entry_number,
        is_disabled=is_disabled,
        withdrawn_at=withdrawn_at,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    for phase in (PredictionPhase.PHASE_1, PredictionPhase.PHASE_2):
        session.add(
            PredictionEntryPhase(entry_id=entry.id, phase=phase, status=status)
        )
    await session.commit()
    await session.refresh(entry)
    return entry


async def _add_fixture(
    session: AsyncSession,
    competition: Competition,
    *,
    home: str = "Brazil",
    away: str = "Germany",
    home_score: int = 2,
    away_score: int = 1,
) -> Fixture:
    f = Fixture(
        competition_id=competition.id,
        home_team=home,
        away_team=away,
        kickoff=datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
        stage="group",
        group="A",
        status=MatchStatus.FINISHED,
    )
    session.add(f)
    await session.commit()
    await session.refresh(f)
    session.add(
        Score(
            fixture_id=f.id,
            home_score=home_score,
            away_score=away_score,
            source=ScoreSource.MANUAL,
            verified=True,
        )
    )
    await session.commit()
    return f


async def _add_pick(
    session: AsyncSession,
    entry: PredictionEntry,
    fixture: Fixture,
    home: int,
    away: int,
) -> None:
    session.add(
        MatchPrediction(
            entry_id=entry.id,
            fixture_id=fixture.id,
            home_score=home,
            away_score=away,
            phase=PredictionPhase.PHASE_1,
        )
    )
    await session.commit()


# ---------------------------------------------------------------------------
# 1. Batched counts == manual counts; eligibility filter applies
# ---------------------------------------------------------------------------
class TestGetAllOutcomeCounts:
    async def test_matches_manual_per_fixture_counts(
        self, session: AsyncSession, alice: User, competition: Competition
    ):
        f1 = await _add_fixture(session, competition, home="Brazil", away="Germany")
        f2 = await _add_fixture(session, competition, home="Spain", away="Italy")

        e1 = await _make_entry(session, user=alice, competition=competition, entry_number=1)
        e2 = await _make_entry(session, user=alice, competition=competition, entry_number=2)
        e3 = await _make_entry(session, user=alice, competition=competition, entry_number=3)

        # f1: two home-wins, one draw. f2: one away-win.
        await _add_pick(session, e1, f1, 2, 1)  # "1"
        await _add_pick(session, e2, f1, 3, 0)  # "1"
        await _add_pick(session, e3, f1, 1, 1)  # "X"
        await _add_pick(session, e1, f2, 0, 2)  # "2"

        counts = await get_all_outcome_counts(session)
        assert counts[f1.id] == {"1": 2, "X": 1, "2": 0}
        assert counts[f2.id] == {"1": 0, "X": 0, "2": 1}

    async def test_excludes_ineligible_entries(
        self, session: AsyncSession, alice: User, competition: Competition
    ):
        """DRAFT / withdrawn / disabled entries' predictions are invisible
        to the rarity denominator."""
        f1 = await _add_fixture(session, competition)

        eligible = await _make_entry(
            session, user=alice, competition=competition, entry_number=1
        )
        draft = await _make_entry(
            session, user=alice, competition=competition, entry_number=2,
            status=EntryStatus.DRAFT,
        )
        withdrawn = await _make_entry(
            session, user=alice, competition=competition, entry_number=3,
            withdrawn_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        disabled = await _make_entry(
            session, user=alice, competition=competition, entry_number=4,
            is_disabled=True,
        )
        for entry in (eligible, draft, withdrawn, disabled):
            await _add_pick(session, entry, f1, 2, 1)

        counts = await get_all_outcome_counts(session)
        # Only the eligible entry's prediction is counted.
        assert counts[f1.id] == {"1": 1, "X": 0, "2": 0}


# ---------------------------------------------------------------------------
# 2. Precomputed caches don't change the result
# ---------------------------------------------------------------------------
class TestCacheParameterEquivalence:
    async def test_with_and_without_caches_identical(
        self, session: AsyncSession, alice: User, competition: Competition
    ):
        f1 = await _add_fixture(session, competition)
        entry = await _make_entry(session, user=alice, competition=competition)
        await _add_pick(session, entry, f1, 2, 1)

        plain = await calculate_entry_points(session, entry.id)
        cached = await calculate_entry_points(
            session,
            entry.id,
            outcome_counts_by_fixture=await get_all_outcome_counts(session),
            actual_advancement=await get_actual_advancement(session),
        )
        assert plain.model_dump() == cached.model_dump()


# ---------------------------------------------------------------------------
# 3. Leaderboard rows read stats from the breakdown
# ---------------------------------------------------------------------------
class TestLeaderboardRowStats:
    async def test_rows_carry_breakdown_stats(
        self, session: AsyncSession, alice: User, competition: Competition
    ):
        f1 = await _add_fixture(session, competition)
        f2 = await _add_fixture(session, competition, home="Spain", away="Italy")
        entry = await _make_entry(session, user=alice, competition=competition)
        await _add_pick(session, entry, f1, 2, 1)  # exact
        await _add_pick(session, entry, f2, 1, 0)  # outcome only (actual 2-1)

        board = await calculate_leaderboard(session, force_refresh=True)
        row = next(r for r in board.entries if r.entry_id == entry.id)
        assert row.correct_outcomes == 2
        assert row.exact_scores == 1
        assert row.correct_outcomes == row.breakdown.correct_outcomes
        assert row.exact_scores == row.breakdown.exact_scores


# ---------------------------------------------------------------------------
# 4. Single-flight: concurrent cold loads rebuild once
# ---------------------------------------------------------------------------
class TestSingleFlight:
    async def test_concurrent_cold_calls_one_rebuild(self):
        """Five concurrent cold calls → exactly one rebuild; everyone gets
        the same standings. StaticPool shares the single in-memory SQLite
        connection across the per-call sessions."""
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", poolclass=StaticPool
        )
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as setup:
            comp = Competition(
                name="Test WC 2026",
                external_id="WC",
                is_active=True,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                max_entries_per_user=5,
            )
            setup.add(comp)
            await setup.commit()
            await setup.refresh(comp)
            user = User(
                email="solo@example.com",
                name="Solo",
                password_hash="x",
                auth_provider=AuthProvider.EMAIL,
            )
            setup.add(user)
            await setup.commit()
            await setup.refresh(user)
            await _make_entry(setup, user=user, competition=comp)

        rebuild_calls = 0
        real_rebuild = leaderboard_service._rebuild_leaderboard

        async def counting_rebuild(*args, **kwargs):
            nonlocal rebuild_calls
            rebuild_calls += 1
            return await real_rebuild(*args, **kwargs)

        async def one_call():
            async with factory() as s:
                return await calculate_leaderboard(s, force_refresh=False)

        with patch.object(
            leaderboard_service, "_rebuild_leaderboard", counting_rebuild
        ):
            results = await asyncio.gather(*[one_call() for _ in range(5)])

        assert rebuild_calls == 1
        assert all(r.total_participants == 1 for r in results)


# ---------------------------------------------------------------------------
# 5. Draft-owner breakdown: base points, zero rarity, no crash
# ---------------------------------------------------------------------------
class TestDraftOwnerBreakdown:
    async def test_draft_entry_gets_base_points_without_rarity(
        self, session: AsyncSession, alice: User, competition: Competition
    ):
        """Pins the Step 5e product decision: a DRAFT entry's own
        prediction sits OUTSIDE the eligible-only outcome counts, so the
        owner viewing /breakdown sees base points (outcome + exact) with a
        0 rarity bonus — and nothing raises."""
        log_config = {
            "mode": "logarithmic",
            "match": {"correct_outcome": 5, "exact_score": 10, "rarity_cap": 10},
            "advancement": {},
            "phase_multipliers": {"phase_1": 1.0, "phase_2": 0.7},
        }
        f1 = await _add_fixture(session, competition)
        draft = await _make_entry(
            session, user=alice, competition=competition,
            status=EntryStatus.DRAFT,
        )
        await _add_pick(session, draft, f1, 2, 1)  # exact

        with patch(
            "app.services.scoring.get_scoring_config", return_value=log_config
        ):
            breakdown = await calculate_entry_points(session, draft.id)

        # outcome (5) + exact (10), rarity 0 — correct_predictors is 0 in
        # the eligible-only counts, which the formula guards.
        assert breakdown.total == 15
        assert breakdown.correct_outcomes == 1
        assert breakdown.exact_scores == 1
