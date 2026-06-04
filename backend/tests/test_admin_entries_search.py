"""Tests for the admin entries-list smart search.

Pins the contract added in v2.154.3 (Tweak 6 in
stay-in-plan-mode-dynamic-adleman.md): a single ``search`` parameter
that OR-matches ``User.email`` and ``PredictionEntry.reference`` as a
case-insensitive substring. Admins type whatever fragment they
remember — email piece, reference number, etc. — and the right rows
come back.

Mirrors the in-memory-SQLite fixture setup from `test_entries_service.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register every model with metadata
from app.models.competition import Competition
from app.models.user import AuthProvider, User
from app.services import entries as entries_service


# ---------------------------------------------------------------------------
# Fixtures (mirror test_entries_service.py's setup)
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
async def two_users_with_entries(
    session: AsyncSession, competition: Competition
) -> tuple[User, User]:
    """Two distinct users, one entry each. Emails chosen so substring
    matches don't accidentally overlap (no shared letters in the
    discriminating fragment)."""
    vinay = User(
        email="vinay@example.com",
        name="Vinay",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        paid_to="Pool Treasurer",
    )
    bob = User(
        email="bob@other.test",
        name="Bob",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        paid_to="Pool Treasurer",
    )
    session.add(vinay)
    session.add(bob)
    await session.commit()
    await session.refresh(vinay)
    await session.refresh(bob)

    await entries_service.create_entry(session, user=vinay, competition=competition)
    await entries_service.create_entry(session, user=bob, competition=competition)
    await session.commit()
    return vinay, bob


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestAdminListEntriesSearch:
    """The new `search` kwarg on admin_list_entries."""

    async def test_no_search_returns_all(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition
        )
        assert total == 2
        assert len(rows) == 2

    async def test_search_by_email_fragment_returns_only_matching_user(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        vinay, _bob = two_users_with_entries
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, search="vin"
        )
        assert total == 1
        assert len(rows) == 1
        assert rows[0].user_id == vinay.id

    async def test_search_by_reference_number_fragment(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # The first entry created gets reference WC26-000001; second 000002.
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, search="000001"
        )
        assert total == 1
        assert rows[0].reference.endswith("000001")

    async def test_search_is_case_insensitive(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # ilike — typing "VIN" should still find Vinay.
        rows, _ = await entries_service.admin_list_entries(
            session, competition=competition, search="VIN"
        )
        assert len(rows) == 1
        # And "WC26" matches both entries' references.
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, search="wc26"
        )
        assert total == 2

    async def test_search_with_no_matches_returns_empty(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, search="nonexistent-fragment-zz"
        )
        assert total == 0
        assert rows == []

    async def test_empty_string_search_treated_as_no_filter(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # Whitespace-only search shouldn't artificially shrink the result set —
        # the implementation strips and checks for truthiness before joining.
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, search="   "
        )
        assert total == 2

    async def test_search_combines_with_existing_filters(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # `search` should AND with other filters. Both entries are unpaid
        # by default, so filtering paid=True with any search should return
        # nothing — proves the AND semantics.
        _rows, total = await entries_service.admin_list_entries(
            session,
            competition=competition,
            search="vin",
            paid=True,
        )
        assert total == 0


class TestAdminListEntriesNameSearch:
    """v2.156.0 — search now ALSO matches User.name (was email + reference)."""

    async def test_search_by_name_substring(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        vinay, _bob = two_users_with_entries
        # "Vin" matches Vinay's name (not just email — exercising the
        # User.name branch of the search OR).
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, search="Vin"
        )
        assert total == 1
        assert rows[0].user_id == vinay.id

    async def test_search_by_name_is_case_insensitive(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, search="BOB"
        )
        assert total == 1


class TestAdminListEntriesModifiedWithin:
    """v2.156.0 — `modified_within` filter on PredictionEntry.updated_at."""

    async def test_modified_within_24h_returns_entries_inside_window(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # The fixture-created entries have updated_at = now (default
        # factory), so they're well inside any reasonable window.
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, modified_within="24h"
        )
        assert total == 2

    async def test_modified_within_excludes_older_entries(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # Push one entry's updated_at far into the past — outside any
        # of the named windows.
        from datetime import datetime, timezone, timedelta

        vinay, _bob = two_users_with_entries
        entries_all, _ = await entries_service.admin_list_entries(
            session, competition=competition
        )
        # Find vinay's entry and back-date it
        vinay_entry = next(e for e in entries_all if e.user_id == vinay.id)
        vinay_entry.updated_at = datetime.now(tz=timezone.utc) - timedelta(
            days=60
        )
        session.add(vinay_entry)
        await session.commit()

        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, modified_within="30d"
        )
        # Only bob's entry is within the 30-day window now.
        assert total == 1
        assert rows[0].user_id != vinay.id

    async def test_modified_within_combines_with_search(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # AND semantics — name search + time window both applied.
        rows, total = await entries_service.admin_list_entries(
            session,
            competition=competition,
            search="bob",
            modified_within="24h",
        )
        assert total == 1

    async def test_unknown_modified_within_value_is_ignored(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # Defensive forgiveness — unknown tokens silently become no-filter
        # so stale URLs / typos don't ghost-empty the results.
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, modified_within="not-a-window"
        )
        assert total == 2  # both entries returned, filter ignored


class TestAdminListEntriesStatusFilter:
    """v2.157.0 — status filter bug fixes:

    Bug 0a: every entry is created with BOTH phase_1 and phase_2 rows in
    DRAFT (Phase 2 is dormant but the rows exist). The pre-fix code joined
    PredictionEntryPhase without scoping phase=PHASE_1, so `status=draft`
    matched every entry via its dormant phase_2=DRAFT row.

    Bug 0b: withdrawn is an entry-level overlay (entry.withdrawn_at), not
    a phase status — phase rows never transition to WITHDRAWN in the
    lifecycle code.
    """

    async def test_status_draft_does_not_match_submitted_entries(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # Submit one entry (transition its phase_1 row → SUBMITTED).
        # The phase_2 row stays in DRAFT — that's the bait the bug bit on.
        from app.models.entry import EntryStatus
        from app.models.prediction import PredictionPhase

        all_entries, _ = await entries_service.admin_list_entries(
            session, competition=competition
        )
        target = all_entries[0]
        # Reload with phases to mutate
        from sqlmodel import select
        from sqlalchemy.orm import selectinload
        from app.models.entry import PredictionEntry, PredictionEntryPhase

        target = (
            await session.execute(
                select(PredictionEntry)
                .options(selectinload(PredictionEntry.phases))
                .where(PredictionEntry.id == target.id)
            )
        ).scalar_one()
        phase_1 = next(
            p for p in target.phases if p.phase == PredictionPhase.PHASE_1
        )
        phase_1.status = EntryStatus.SUBMITTED
        session.add(phase_1)
        await session.commit()

        # status=draft must now return ONLY the un-submitted entry —
        # not BOTH entries via their dormant phase_2=DRAFT rows.
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, status=EntryStatus.DRAFT
        )
        assert total == 1, "Pre-fix bug: would return 2 via phase_2=DRAFT"
        assert rows[0].id != target.id

        # status=submitted returns only the submitted one.
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, status=EntryStatus.SUBMITTED
        )
        assert total == 1
        assert rows[0].id == target.id

    async def test_status_filter_total_count_not_inflated_by_join(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # Both entries are draft (phase_1 + phase_2 both DRAFT). Pre-fix
        # the count would have inflated to 4 because each entry matched
        # via two phase rows. With phase=PHASE_1 scope it stays at 2.
        from app.models.entry import EntryStatus

        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, status=EntryStatus.DRAFT
        )
        assert total == len(rows) == 2

    async def test_status_withdrawn_filters_on_entry_withdrawn_at(
        self,
        session: AsyncSession,
        competition: Competition,
        two_users_with_entries: tuple[User, User],
    ):
        # Withdraw one entry by setting withdrawn_at directly (avoids the
        # full admin_withdraw_entry path which has additional deps).
        from app.models.entry import EntryStatus
        from app.models._datetime import utc_now

        all_entries, _ = await entries_service.admin_list_entries(
            session, competition=competition
        )
        target = all_entries[0]
        target.withdrawn_at = utc_now()
        target.withdrawn_reason = "test"
        session.add(target)
        await session.commit()

        # status=withdrawn returns exactly the withdrawn entry.
        rows, total = await entries_service.admin_list_entries(
            session, competition=competition, status=EntryStatus.WITHDRAWN
        )
        assert total == 1
        assert rows[0].id == target.id
        assert rows[0].withdrawn_at is not None

        # status=draft excludes the withdrawn entry.
        rows, _ = await entries_service.admin_list_entries(
            session, competition=competition, status=EntryStatus.DRAFT
        )
        assert all(r.id != target.id for r in rows)
