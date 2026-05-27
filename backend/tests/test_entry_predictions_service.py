"""Tests for the entry-scoped prediction service.

Covers the brief-mandated rules:
- Same user can hold divergent predictions across two entries for one fixture
- Locked phase rejects all prediction writes
- Fixture individually locked rejects writes
- Cross-entry / cross-user access forbidden
- Score range, withdrawn / disabled entries, phase deadline guards
- Audit events are written on every mutation

Uses in-memory SQLite per the project convention.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import app.models  # noqa: F401 — register every model with metadata
from app.models.audit import AuditEvent
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.user import AuthProvider, User
from app.services import entries as entries_service
from app.services import predictions as predictions_service
from app.services.predictions import (
    PredictionAccessDeniedError,
    PredictionLockedError,
    PredictionValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
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
async def fixture_future(
    session: AsyncSession, competition: Competition
) -> Fixture:
    """A fixture 7 days from now — not locked, freely predictable."""
    f = Fixture(
        competition_id=competition.id,
        home_team="Brazil",
        away_team="Germany",
        kickoff=datetime.now(timezone.utc) + timedelta(days=7),
        stage="group",
        group="A",
        status=MatchStatus.SCHEDULED,
    )
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


@pytest_asyncio.fixture
async def fixture_locked(
    session: AsyncSession, competition: Competition
) -> Fixture:
    """A fixture within the 5-min lock window (kickoff in 2 min)."""
    f = Fixture(
        competition_id=competition.id,
        home_team="Spain",
        away_team="Italy",
        kickoff=datetime.now(timezone.utc) + timedelta(minutes=2),
        stage="group",
        group="B",
        status=MatchStatus.SCHEDULED,
    )
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


@pytest_asyncio.fixture
async def alice_entry(
    session: AsyncSession, alice: User, competition: Competition
) -> PredictionEntry:
    entry = await entries_service.create_entry(
        session, user=alice, competition=competition
    )
    await session.commit()
    return entry


# ---------------------------------------------------------------------------
# Same user, two entries, same fixture — divergent picks
# ---------------------------------------------------------------------------
class TestTwoEntriesSameFixture:
    """The (entry_id, fixture_id) uniqueness must allow this case."""

    async def test_same_user_two_entries_can_differ(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        fixture_future: Fixture,
    ):
        e1 = await entries_service.create_entry(
            session, user=alice, competition=competition
        )
        e2 = await entries_service.create_entry(
            session, user=alice, competition=competition
        )
        await session.commit()

        await predictions_service.upsert_match_prediction(
            session,
            entry=e1,
            user=alice,
            competition=competition,
            fixture_id=fixture_future.id,
            home_score=2,
            away_score=1,
        )
        await predictions_service.upsert_match_prediction(
            session,
            entry=e2,
            user=alice,
            competition=competition,
            fixture_id=fixture_future.id,
            home_score=0,
            away_score=3,
        )
        await session.commit()

        rows = (
            await session.execute(
                select(MatchPrediction).where(
                    MatchPrediction.fixture_id == fixture_future.id
                )
            )
        ).scalars().all()
        by_entry = {r.entry_id: (r.home_score, r.away_score) for r in rows}
        assert by_entry[e1.id] == (2, 1)
        assert by_entry[e2.id] == (0, 3)


# ---------------------------------------------------------------------------
# Phase lock — rejects writes once entry's phase is not DRAFT
# ---------------------------------------------------------------------------
class TestPhaseStatusLock:
    # The former `test_ready_status_rejects_write` was removed: the `ready`
    # status no longer exists after the 6→3 lifecycle simplification. The only
    # non-editable status is SUBMITTED, covered by the test below.

    async def test_submitted_status_rejects_write(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_future: Fixture,
    ):
        await entries_service.submit_entry(
            session,
            entry=alice_entry,
            user=alice,
            competition=competition,
        )
        await session.commit()
        with pytest.raises(PredictionLockedError):
            await predictions_service.upsert_match_prediction(
                session,
                entry=alice_entry,
                user=alice,
                competition=competition,
                fixture_id=fixture_future.id,
                home_score=1,
                away_score=0,
            )


# ---------------------------------------------------------------------------
# Fixture-individual lock (5 min before kickoff)
# ---------------------------------------------------------------------------
class TestFixtureLock:
    async def test_fixture_within_lock_window_rejects(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_locked: Fixture,
    ):
        with pytest.raises(PredictionLockedError):
            await predictions_service.upsert_match_prediction(
                session,
                entry=alice_entry,
                user=alice,
                competition=competition,
                fixture_id=fixture_locked.id,
                home_score=1,
                away_score=0,
            )

    async def test_batch_skips_locked_fixtures(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_future: Fixture,
        fixture_locked: Fixture,
    ):
        # Mix one writable + one locked fixture. Batch should succeed,
        # writing the writable one and skipping the locked one.
        results = await predictions_service.batch_upsert_match_predictions(
            session,
            entry=alice_entry,
            user=alice,
            competition=competition,
            items=[
                (fixture_future.id, 1, 0),
                (fixture_locked.id, 2, 2),
            ],
        )
        await session.commit()
        # Only the future fixture got a prediction.
        assert len(results) == 1
        assert results[0].fixture_id == fixture_future.id


# ---------------------------------------------------------------------------
# Cross-entry access — user B can't write to user A's entry
# ---------------------------------------------------------------------------
class TestCrossEntryAccess:
    async def test_other_user_cannot_write(
        self,
        session: AsyncSession,
        alice: User,
        bob: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_future: Fixture,
    ):
        with pytest.raises(PredictionAccessDeniedError):
            await predictions_service.upsert_match_prediction(
                session,
                entry=alice_entry,
                user=bob,  # not the owner
                competition=competition,
                fixture_id=fixture_future.id,
                home_score=1,
                away_score=0,
            )


# ---------------------------------------------------------------------------
# Score range
# ---------------------------------------------------------------------------
class TestScoreRange:
    async def test_negative_score_rejected(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_future: Fixture,
    ):
        with pytest.raises(PredictionValidationError):
            await predictions_service.upsert_match_prediction(
                session,
                entry=alice_entry,
                user=alice,
                competition=competition,
                fixture_id=fixture_future.id,
                home_score=-1,
                away_score=0,
            )

    async def test_score_above_max_rejected(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_future: Fixture,
    ):
        with pytest.raises(PredictionValidationError):
            await predictions_service.upsert_match_prediction(
                session,
                entry=alice_entry,
                user=alice,
                competition=competition,
                fixture_id=fixture_future.id,
                home_score=16,
                away_score=0,
            )

    async def test_max_score_15_accepted(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_future: Fixture,
    ):
        # 15 is at the cap — must be accepted.
        await predictions_service.upsert_match_prediction(
            session,
            entry=alice_entry,
            user=alice,
            competition=competition,
            fixture_id=fixture_future.id,
            home_score=15,
            away_score=15,
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Phase deadline
# ---------------------------------------------------------------------------
class TestPhaseDeadline:
    async def test_past_phase1_deadline_rejects_write(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_future: Fixture,
    ):
        competition.phase1_deadline = datetime(2020, 1, 1, tzinfo=timezone.utc)
        await session.commit()
        with pytest.raises(PredictionLockedError):
            await predictions_service.upsert_match_prediction(
                session,
                entry=alice_entry,
                user=alice,
                competition=competition,
                fixture_id=fixture_future.id,
                home_score=1,
                away_score=0,
            )


# ---------------------------------------------------------------------------
# Withdrawn / disabled entries
# ---------------------------------------------------------------------------
class TestWithdrawnDisabled:
    async def test_withdrawn_entry_rejects_write(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_future: Fixture,
    ):
        await entries_service.admin_withdraw_entry(
            session, entry=alice_entry, admin=alice, reason="test"
        )
        await session.commit()
        with pytest.raises(PredictionValidationError):
            await predictions_service.upsert_match_prediction(
                session,
                entry=alice_entry,
                user=alice,
                competition=competition,
                fixture_id=fixture_future.id,
                home_score=1,
                away_score=0,
            )


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------
class TestAuditWrites:
    async def test_match_upsert_writes_audit(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_future: Fixture,
    ):
        await predictions_service.upsert_match_prediction(
            session,
            entry=alice_entry,
            user=alice,
            competition=competition,
            fixture_id=fixture_future.id,
            home_score=2,
            away_score=1,
        )
        await session.commit()
        events = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "prediction.match_upserted"
                )
            )
        ).scalars().all()
        assert len(events) == 1
        meta = events[0].event_metadata
        assert meta["entry_reference"] == alice_entry.reference
        assert meta["new_home"] == 2
        assert meta["new_away"] == 1
        assert meta["old_home"] is None  # fresh insert

    async def test_match_upsert_audit_records_diff_on_update(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
        fixture_future: Fixture,
    ):
        await predictions_service.upsert_match_prediction(
            session,
            entry=alice_entry,
            user=alice,
            competition=competition,
            fixture_id=fixture_future.id,
            home_score=2,
            away_score=1,
        )
        await session.commit()
        await predictions_service.upsert_match_prediction(
            session,
            entry=alice_entry,
            user=alice,
            competition=competition,
            fixture_id=fixture_future.id,
            home_score=3,
            away_score=0,
        )
        await session.commit()
        events = (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.event_type == "prediction.match_upserted")
                .order_by(AuditEvent.created_at)
            )
        ).scalars().all()
        assert len(events) == 2
        # Second event captures the previous values as old_*.
        assert events[1].event_metadata["old_home"] == 2
        assert events[1].event_metadata["old_away"] == 1
        assert events[1].event_metadata["new_home"] == 3
        assert events[1].event_metadata["new_away"] == 0

    async def test_bracket_replace_writes_single_audit(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
    ):
        picks = [
            {"team": "Brazil", "stage": "round_of_32", "group_position": None},
            {"team": "Germany", "stage": "round_of_32", "group_position": None},
            {"team": "Argentina", "stage": "winner", "group_position": None},
        ]
        await predictions_service.replace_bracket_predictions(
            session,
            entry=alice_entry,
            user=alice,
            competition=competition,
            picks=picks,
        )
        await session.commit()
        events = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "prediction.bracket_replaced"
                )
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].event_metadata["count"] == 3


# ---------------------------------------------------------------------------
# Bracket replace clears only current-phase picks
# ---------------------------------------------------------------------------
class TestBracketReplaceClearsByPhase:
    async def test_phase1_replace_does_not_touch_phase2_rows(
        self,
        session: AsyncSession,
        alice: User,
        competition: Competition,
        alice_entry: PredictionEntry,
    ):
        # Manually seed a phase_2 pick so we can verify it survives. The phase
        # MUST be set explicitly — TeamPrediction.phase defaults to PHASE_1, and
        # a phase-1 row would (correctly) be cleared by the phase-1 replace below.
        phase2_row = TeamPrediction(
            entry_id=alice_entry.id,
            team="France",
            stage="winner",
            phase=PredictionPhase.PHASE_2,
        )
        session.add(phase2_row)
        await session.commit()

        # competition.is_phase2_active is False by default → current phase is PHASE_1.
        await predictions_service.replace_bracket_predictions(
            session,
            entry=alice_entry,
            user=alice,
            competition=competition,
            picks=[
                {"team": "Brazil", "stage": "winner", "group_position": None},
            ],
        )
        await session.commit()

        # Phase 1 has just one pick (the new one). Phase 2 row is untouched.
        rows = (
            await session.execute(
                select(TeamPrediction).where(
                    TeamPrediction.entry_id == alice_entry.id
                )
            )
        ).scalars().all()
        by_phase = {(r.phase, r.team) for r in rows}
        assert (PredictionPhase.PHASE_1, "Brazil") in by_phase
        assert (PredictionPhase.PHASE_2, "France") in by_phase
        assert len(rows) == 2
