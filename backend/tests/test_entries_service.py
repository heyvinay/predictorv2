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
    EntryValidationError,
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
    # paid_to is pre-populated so existing submit tests pass; the new R3
    # gate in submit_entry rejects submissions where paid_to is empty.
    # A dedicated test exercises the blocked path with a user lacking it.
    u = User(
        email="alice@example.com",
        name="Alice",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        paid_to="Pool Treasurer",
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
        paid_to="Pool Treasurer",
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
        await entries_service.admin_withdraw_entry(
            session, entry=e1, admin=user, reason="test"
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
# Lifecycle — new 3-status model: DRAFT, SUBMITTED, WITHDRAWN.
# Tests for the 5 transitions added in the simplification (see plan
# i-want-to-simplify-bright-wolf.md).
# ---------------------------------------------------------------------------
class TestLifecycle:
    async def test_submit_flips_draft_to_submitted(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        phase = await entries_service.submit_entry(
            session,
            entry=entry,
            user=user,
            competition=competition,
            validate_complete=False,
        )
        await session.commit()
        assert phase.status == EntryStatus.SUBMITTED
        assert phase.submitted_at is not None

    async def test_submit_blocked_without_paid_to(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        """R3 gate: a user must record paid_to before submitting."""
        # Clear paid_to to simulate a user who hasn't filled it in yet.
        user.paid_to = None
        await session.commit()

        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()

        with pytest.raises(EntryValidationError, match=r"(?i)paid"):
            await entries_service.submit_entry(
                session,
                entry=entry,
                user=user,
                competition=competition,
                validate_complete=False,
            )

    async def test_submit_blocked_when_paid_to_is_whitespace(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        """Empty-string and whitespace-only paid_to are equally blocked."""
        user.paid_to = "   "
        await session.commit()

        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()

        with pytest.raises(EntryValidationError, match=r"(?i)paid"):
            await entries_service.submit_entry(
                session,
                entry=entry,
                user=user,
                competition=competition,
                validate_complete=False,
            )

    async def test_edit_reverts_submitted_to_draft(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.submit_entry(
            session,
            entry=entry,
            user=user,
            competition=competition,
            validate_complete=False,
        )
        await session.commit()
        phase = await entries_service.edit_entry(
            session, entry=entry, user=user, competition=competition
        )
        await session.commit()
        assert phase.status == EntryStatus.DRAFT
        assert phase.submitted_at is None

    async def test_edit_blocked_after_deadline(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        from datetime import datetime, timedelta, timezone

        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.submit_entry(
            session,
            entry=entry,
            user=user,
            competition=competition,
            validate_complete=False,
        )
        await session.commit()
        competition.phase1_deadline = datetime.now(timezone.utc) - timedelta(minutes=5)
        session.add(competition)
        await session.commit()
        with pytest.raises(entries_service.EntryStateError):
            await entries_service.edit_entry(
                session, entry=entry, user=user, competition=competition
            )

    async def test_admin_reinstate_flips_withdrawn_to_submitted(
        self, session: AsyncSession, user: User, admin: User, competition: Competition
    ):
        """The 'forgot to click Submit' rescue path."""
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.admin_withdraw_entry(
            session, entry=entry, admin=admin, reason="auto"
        )
        await session.commit()
        await entries_service.admin_reinstate_entry(
            session,
            entry=entry,
            admin=admin,
            reason="user filled everything, missed submit by 4 min",
        )
        await session.commit()
        assert entry.withdrawn_at is None
        phase_row = next(p for p in entry.phases if p.phase == PredictionPhase.PHASE_1)
        assert phase_row.status == EntryStatus.SUBMITTED

    async def test_admin_reinstate_requires_reason(
        self, session: AsyncSession, user: User, admin: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.admin_withdraw_entry(
            session, entry=entry, admin=admin, reason="x"
        )
        await session.commit()
        with pytest.raises(entries_service.EntryValidationError):
            await entries_service.admin_reinstate_entry(
                session, entry=entry, admin=admin, reason=""
            )

    async def test_admin_reinstate_audit_links_to_prior_withdrawal_event(
        self, session: AsyncSession, user: User, admin: User, competition: Competition
    ):
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.admin_withdraw_entry(
            session, entry=entry, admin=admin, reason="original reason"
        )
        await session.commit()
        await entries_service.admin_reinstate_entry(
            session, entry=entry, admin=admin, reason="reinstate evidence"
        )
        await session.commit()
        reinstate_audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "entry.admin_reinstated"
                )
            )
        ).scalar_one()
        assert "previous_withdrawal_event_id" in reinstate_audit.event_metadata
        assert reinstate_audit.event_metadata["previous_withdrawal_reason"] == "original reason"

    async def test_flip_drafts_past_deadline_idempotent(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        from datetime import datetime, timedelta, timezone

        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        competition.phase1_deadline = datetime.now(timezone.utc) - timedelta(minutes=5)
        session.add(competition)
        await session.commit()
        flipped = await entries_service.flip_drafts_past_deadline(session)
        await session.commit()
        assert flipped == 1
        assert entry.withdrawn_at is not None
        flipped_again = await entries_service.flip_drafts_past_deadline(session)
        assert flipped_again == 0


# ---------------------------------------------------------------------------
# Submit-time completeness validation (added 2026-05-31)
#
# Defense-in-depth against the frontend submitting an incomplete entry.
# The validator runs by default; transition-mechanic tests opt out via
# `validate_complete=False` (see TestLifecycle).
# ---------------------------------------------------------------------------
class TestSubmitCompleteness:
    async def test_submit_rejects_empty_entry(
        self,
        session: AsyncSession,
        user: User,
        competition: Competition,
    ):
        """Empty entry (no predictions at all) should be rejected with a
        message that names the missing pieces — bracket, bonus, etc."""
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()

        with pytest.raises(EntryValidationError) as exc_info:
            await entries_service.submit_entry(
                session, entry=entry, user=user, competition=competition
            )
        msg = str(exc_info.value).lower()
        # Bracket gaps must be surfaced (the user's stated critical risk).
        assert "round of 16" in msg
        assert "winner" in msg
        # Bonus gaps too (aggregated into the same message).
        assert "bonus" in msg

    async def test_submit_rejects_stale_winner_chain(
        self,
        session: AsyncSession,
        user: User,
        competition: Competition,
    ):
        """The hard case: bracket has all the expected counts per stage,
        but a team at a later stage doesn't appear at the prior stage —
        a stale row left behind when the user changed an upstream pick.
        The frontend's `bracketIsComplete` catches this via
        `predictionToBracketState`; the backend's equivalent walks the
        flat stage rows and rejects when the chain is broken."""
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()

        # 16 round_of_16 teams.
        r16_teams = [f"T{i:02d}" for i in range(1, 17)]
        # 8 quarter_finals — 7 are a valid subset of R16; ONE is stale
        # (not in R16). This is the bug pattern the validator must catch.
        qf_teams = r16_teams[:7] + ["STALE_TEAM"]

        for team in r16_teams:
            session.add(
                TeamPrediction(
                    entry_id=entry.id,
                    phase=PredictionPhase.PHASE_1,
                    team=team,
                    stage="round_of_16",
                )
            )
        for team in qf_teams:
            session.add(
                TeamPrediction(
                    entry_id=entry.id,
                    phase=PredictionPhase.PHASE_1,
                    team=team,
                    stage="quarter_finals",
                )
            )
        await session.commit()

        with pytest.raises(EntryValidationError) as exc_info:
            await entries_service.submit_entry(
                session, entry=entry, user=user, competition=competition
            )
        msg = str(exc_info.value).lower()
        assert "chain broken" in msg
        assert "stale_team" in msg

    async def test_submit_skips_validation_when_opted_out(
        self,
        session: AsyncSession,
        user: User,
        competition: Competition,
    ):
        """Sanity check: the `validate_complete=False` opt-out keeps
        transition-mechanic tests working. With the kwarg disabled,
        even an empty entry submits successfully."""
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()

        phase = await entries_service.submit_entry(
            session,
            entry=entry,
            user=user,
            competition=competition,
            validate_complete=False,
        )
        await session.commit()
        assert phase.status == EntryStatus.SUBMITTED


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
        await entries_service.admin_withdraw_entry(
            session, entry=entry, admin=user, reason="changed my mind"
        )
        await session.commit()
        assert entry.withdrawn_at is not None
        assert entry.withdrawn_reason == "changed my mind"

    async def test_withdraw_sets_withdrawn_at_and_marks_phase_1(
        self, session: AsyncSession, user: User, competition: Competition
    ):
        """Withdrawal sets entry.withdrawn_at and flips PHASE 1 to WITHDRAWN.

        Phase 2 is dormant, so withdrawal is scoped to the active phase (phase 1)
        rather than cascading to every phase — the 6→3 lifecycle simplification
        narrowed this from the old 'mark all phases' behaviour.
        """
        entry = await entries_service.create_entry(
            session, user=user, competition=competition
        )
        await session.commit()
        await entries_service.admin_withdraw_entry(session, entry=entry, admin=user, reason="test")
        await session.commit()

        assert entry.withdrawn_at is not None
        phase1 = next(p for p in entry.phases if p.phase == PredictionPhase.PHASE_1)
        assert phase1.status == EntryStatus.WITHDRAWN


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
        await entries_service.submit_entry(
            session,
            entry=e1,
            user=user,
            competition=competition,
            validate_complete=False,
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
            await entries_service.submit_entry(
                session,
                entry=e2,
                user=user,
                competition=competition,
                validate_complete=False,
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
        await entries_service.submit_entry(
            session,
            entry=e1,
            user=user,
            competition=competition,
            validate_complete=False,
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
            )
        )
        await session.commit()

        # Ready should not raise — predictions differ.
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
        phase1.status = EntryStatus.SUBMITTED
        await session.commit()

        await entries_service.admin_disable_entry(
            session, entry=entry, admin=admin, reason="suspicious activity"
        )
        await session.commit()
        assert entry.is_disabled is True
        assert entry.disabled_reason == "suspicious activity"
        # Locked phase status unchanged.
        await session.refresh(phase1)
        assert phase1.status == EntryStatus.SUBMITTED

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
        await entries_service.admin_withdraw_entry(session, entry=withdrawn, admin=user, reason="test")
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
