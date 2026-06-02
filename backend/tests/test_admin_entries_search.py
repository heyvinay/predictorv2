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
