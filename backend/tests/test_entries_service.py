"""Tests for the entry-management service.

Covers the state machine, ownership checks, max-entries enforcement,
duplicate-submission detection, audit-event writes, and admin actions.

Uses in-memory SQLite per the project convention (see test_standings.py).
The `_PORTABLE_JSON` variant on `AuditEvent.event_metadata` keeps the
model compatible with SQLite.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

# Ensure every model is registered with SQLModel.metadata so SQLite's
# create_all materializes them. Importing the model package is enough.
import app.models  # noqa: F401
from app.models.audit import AuditEvent
from app.models.competition import Competition
from app.models.entry import (
    ActorRole,
    EntryStatus,
    PredictionEntry,
    PredictionEntryEvent,
    PredictionEntryPhase,
)
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.user import AuthProvider, User
from app.services import entries as entries_service
from app.services.entries import (
    EntryAccessDeniedError,
    EntryDuplicateError,
    EntryLimitExceededError,
    EntryStateError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Fresh in-memory SQLite DB per test — full isolation."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    """A single active competition with default entry settings."""
    comp = Competition(
        name="Test World Cup 2026",
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
async def user(session: AsyncSession) -> User:
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
async def other_user(session: AsyncSession) -> User:
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
async def admin(session: AsyncSession) -> User:
    u = User(
        email="admin@example.com",
        name="Admin",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_admin=True,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


@pytest_asyncio.fixture
async def fixture_a(session: AsyncSession, competition: Competition) -> Fixture:
    f = Fixture(
        competition_id=competition.id,
        home_team="Brazil",
        away_team="Germany",
        kickoff=datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
        stage="group",
        group="A",
        status=MatchStatus.SCHEDULED,
    )
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


# ---------------------------------------------------------------------------
# Entry creation
# ---------------------------------------------------------------------------
class TestCreateEntry:
    """Entry creation: reference allocation, phase bootstrap, audit log."""

    async def test_first_entry_assigns_sequence_1(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        assert entry.entry_number == 1
        assert entry.reference.startswith("WC26-")
        assert entry.reference.endswith("000001")

    async def test_second_entry_increments_sequence(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        e1 = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        e2 = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        assert e1.entry_number == 1
        assert e2.entry_number == 2
        assert e1.reference != e2.reference

    async def test_creates_both_phase_rows_as_draft(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        statuses_by_phase = {p.phase: p.status for p in entry.phases}
        assert statuses_by_phase[PredictionPhase.PHASE_1] == EntryStatus.DRAFT
        assert statuses_by_phase[PredictionPhase.PHASE_2] == EntryStatus.DRAFT

    async def test_default_display_name_uses_entry_number(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        assert entry.display_name == "Entry 1"

    async def test_writes_audit_event(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        events = (await session.execute(select(AuditEvent))).scalars().all()
        types = [e.event_type for e in events]
        assert "entry.created" in types


# ---------------------------------------------------------------------------
# Max-entries enforcement
# ---------------------------------------------------------------------------
class TestMaxEntriesLimit:
    async def test_blocks_when_at_limit(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        competition.max_entries_per_user = 2
        for _ in range(2):
            await entries_service.create_entry(
                session, user=user, competition=competition
            )
        await session.commit()
        with pytest.raises(EntryLimitExceededError):
            await entries_service.create_entry(
                session, user=user, competition=competition
            )

    async def test_withdrawn_entries_dont_count(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        competition.max_entries_per_user = 2
        e1 = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        # Withdraw e1 — the limit should now allow a new entry.
        await entries_service.withdraw_entry(
            session, entry=e1, user=user, competition=competition
        )
        await session.commit()
        # Should succeed — withdrawn entries are excluded from the count.
        new_entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        assert new_entry.entry_number == 3


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------
class TestRename:
    async def test_rename_changes_display_name(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        result = await entries_service.rename_entry(
            session,
            entry=entry,
            user=user,
            new_name="My Best Picks",
            competition=competition,
        )
        await session.commit()
        assert result.display_name == "My Best Picks"

    async def test_rename_writes_audit_with_old_and_new(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.rename_entry(
            session,
            entry=entry,
            user=user,
            new_name="New Name",
            competition=competition,
        )
        await session.commit()
        events = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.event_type == "entry.renamed")
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].event_metadata["old_name"] == "Entry 1"
        assert events[0].event_metadata["new_name"] == "New Name"


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------
class TestStateTransitions:
    async def test_mark_phase_ready_writes_event(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        phase = await entries_service.mark_phase_ready(
            session,
            entry=entry,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )
        await session.commit()
        assert phase.status == EntryStatus.READY
        assert phase.ready_at is not None

        # Both event tables should have one row each for this transition.
        entry_events = (
            await session.execute(
                select(PredictionEntryEvent).where(
                    PredictionEntryEvent.entry_id == entry.id
                )
            )
        ).scalars().all()
        assert any(
            ev.from_status == "draft" and ev.to_status == "ready"
            for ev in entry_events
        )
        audit_events = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "entry.phase_ready"
                )
            )
        ).scalars().all()
        assert len(audit_events) == 1

    async def test_submit_requires_ready(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        # require_ready_before_submit defaults to True.
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        with pytest.raises(EntryStateError):
            await entries_service.submit_phase(
                session,
                entry=entry,
                user=user,
                phase=PredictionPhase.PHASE_1,
                competition=competition,
            )

    async def test_submit_succeeds_after_ready(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.mark_phase_ready(
            session,
            entry=entry,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )
        await session.commit()
        phase = await entries_service.submit_phase(
            session,
            entry=entry,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )
        await session.commit()
        assert phase.status == EntryStatus.SUBMITTED
        assert phase.submitted_at is not None

    async def test_reopen_returns_to_draft(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.mark_phase_ready(
            session,
            entry=entry,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )
        await session.commit()
        await entries_service.submit_phase(
            session,
            entry=entry,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )
        await session.commit()
        phase = await entries_service.reopen_phase(
            session,
            entry=entry,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )
        await session.commit()
        assert phase.status == EntryStatus.DRAFT
        assert phase.submitted_at is None

    async def test_reopen_blocked_after_phase_deadline(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        # Set phase 1 deadline in the past — the phase is now considered locked.
        competition.phase1_deadline = datetime(2020, 1, 1, tzinfo=timezone.utc)
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        with pytest.raises(EntryStateError):
            await entries_service.reopen_phase(
                session,
                entry=entry,
                user=user,
                phase=PredictionPhase.PHASE_1,
                competition=competition,
            )


# ---------------------------------------------------------------------------
# Withdraw
# ---------------------------------------------------------------------------
class TestWithdraw:
    async def test_withdraw_sets_timestamp(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.withdraw_entry(
            session,
            entry=entry,
            user=user,
            competition=competition,
            reason="changed my mind",
        )
        await session.commit()
        assert entry.withdrawn_at is not None
        assert entry.withdrawn_reason == "changed my mind"

    async def test_withdraw_marks_all_phases(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.withdraw_entry(
            session, entry=entry, user=user, competition=competition
        )
        await session.commit()
        for p in entry.phases:
            assert p.status == EntryStatus.WITHDRAWN


# ---------------------------------------------------------------------------
# Duplicate-submission detection
# ---------------------------------------------------------------------------
class TestDuplicateSubmissionCheck:
    """The flagship rule: identical predictions can't both be submitted."""

    async def _set_match_pred(
        self, session: AsyncSession, entry: PredictionEntry, fixture_id: uuid.UUID
    ) -> None:
        session.add(
            MatchPrediction(
                entry_id=entry.id,
                fixture_id=fixture_id,
                home_score=2,
                away_score=1,
                phase=PredictionPhase.PHASE_1,
            )
        )
        await session.commit()

    async def test_identical_predictions_blocked(
        self,
        session: AsyncSession,
        user: User,
        competition: Competition,
        fixture_a: Fixture,
    ):
        # Build two entries with identical match predictions.
        e1 = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await self._set_match_pred(session, e1, fixture_a.id)
        await entries_service.mark_phase_ready(
            session,
            entry=e1,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )
        await entries_service.submit_phase(
            session,
            entry=e1,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )
        await session.commit()

        # Second entry, identical predictions.
        e2 = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await self._set_match_pred(session, e2, fixture_a.id)

        # Submission must be rejected, naming e1's reference.
        with pytest.raises(EntryDuplicateError) as exc_info:
            await entries_service.mark_phase_ready(
                session,
                entry=e2,
                user=user,
                phase=PredictionPhase.PHASE_1,
                competition=competition,
            )
        assert exc_info.value.conflict_reference == e1.reference

    async def test_different_predictions_allowed(
        self,
        session: AsyncSession,
        user: User,
        competition: Competition,
        fixture_a: Fixture,
    ):
        e1 = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await self._set_match_pred(session, e1, fixture_a.id)  # 2-1
        await entries_service.mark_phase_ready(
            session,
            entry=e1,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )
        await entries_service.submit_phase(
            session,
            entry=e1,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )
        await session.commit()

        e2 = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        # Different score: 3-0 instead of 2-1.
        session.add(
            MatchPrediction(
                entry_id=e2.id,
                fixture_id=fixture_a.id,
                home_score=3,
                away_score=0,
                phase=PredictionPhase.PHASE_1,
            )
        )
        await session.commit()

        # Ready should not raise — predictions differ.
        await entries_service.mark_phase_ready(
            session,
            entry=e2,
            user=user,
            phase=PredictionPhase.PHASE_1,
            competition=competition,
        )


# ---------------------------------------------------------------------------
# Cross-user access
# ---------------------------------------------------------------------------
class TestCrossUserAccess:
    async def test_other_user_cannot_get_entry(
        self,
        session: AsyncSession,
        user: User,
        other_user: User,
        competition: Competition,
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        with pytest.raises(EntryAccessDeniedError):
            await entries_service.get_entry(
                session, entry_id=entry.id, requesting_user=other_user
            )

    async def test_admin_can_get_any_entry(
        self,
        session: AsyncSession,
        user: User,
        admin: User,
        competition: Competition,
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        # With allow_admin=True, admin can read.
        fetched = await entries_service.get_entry(
            session,
            entry_id=entry.id,
            requesting_user=admin,
            allow_admin=True,
        )
        assert fetched.id == entry.id


# ---------------------------------------------------------------------------
# Admin actions
# ---------------------------------------------------------------------------
class TestAdminActions:
    async def test_disable_sets_overlay_without_changing_status(
        self,
        session: AsyncSession,
        user: User,
        admin: User,
        competition: Competition,
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        # Force phase 1 to "locked" — admin disable must NOT mutate it.
        phase1 = next(
            p for p in entry.phases if p.phase == PredictionPhase.PHASE_1
        )
        phase1.status = EntryStatus.LOCKED
        await session.commit()

        await entries_service.admin_disable_entry(
            session, entry=entry, admin=admin, reason="suspicious activity"
        )
        await session.commit()
        assert entry.is_disabled is True
        assert entry.disabled_reason == "suspicious activity"
        # Locked phase status unchanged.
        await session.refresh(phase1)
        assert phase1.status == EntryStatus.LOCKED

    async def test_phase2_open_skips_withdrawn_and_disabled(
        self,
        session: AsyncSession,
        user: User,
        other_user: User,
        admin: User,
        competition: Competition,
    ):
        # Three entries: one normal, one withdrawn, one disabled.
        normal = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        withdrawn = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        disabled = await entries_service.create_entry(
            session, user=other_user, competition=competition
        )
        await session.commit()
        await entries_service.withdraw_entry(
            session, entry=withdrawn, user=user, competition=competition
        )
        await entries_service.admin_disable_entry(
            session, entry=disabled, admin=admin, reason="test"
        )
        await session.commit()

        # phase_2 rows already exist (created by create_entry) — the
        # open action should count them as already_open since they're
        # already in draft.
        summary = await entries_service.admin_open_phase2(
            session, admin=admin, competition=competition
        )
        await session.commit()
        assert summary.entries_skipped_withdrawn == 1
        assert summary.entries_skipped_disabled == 1
        # `normal` was already in draft.
        assert summary.entries_already_open == 1
        # Competition flag is now set.
        assert competition.is_phase2_active is True


# ---------------------------------------------------------------------------
# Duplicate entry
# ---------------------------------------------------------------------------
class TestDuplicateEntry:
    async def test_duplicate_copies_match_predictions(
        self,
        session: AsyncSession,
        user: User,
        competition: Competition,
        fixture_a: Fixture,
    ):
        source = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        session.add(
            MatchPrediction(
                entry_id=source.id,
                fixture_id=fixture_a.id,
                home_score=4,
                away_score=2,
                phase=PredictionPhase.PHASE_1,
            )
        )
        await session.commit()

        new_entry = await entries_service.duplicate_entry(
            session, source=source, user=user, competition=competition
        )
        await session.commit()
        # The new entry should have the same match prediction values.
        copies = (
            await session.execute(
                select(MatchPrediction).where(
                    MatchPrediction.entry_id == new_entry.id
                )
            )
        ).scalars().all()
        assert len(copies) == 1
        assert copies[0].home_score == 4
        assert copies[0].away_score == 2
        # And the source is unaffected.
        assert source.id != new_entry.id
        assert new_entry.display_name.endswith("(copy)")
