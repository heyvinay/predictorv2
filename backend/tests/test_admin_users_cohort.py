"""Service-level tests for the cohort service (v2.156.0).

The cohort SQL is the most subtle part of the redesign — bug here
would either hide real users from the admin (false-negatives in
"signed up only" / "verified only") OR create phantom rows that
appear in no cohort at all. These tests pin the auth-provider-aware
logic.

In particular: a Google OAuth user with ``name=NULL`` has no
``MagicLinkToken`` (OAuth doesn't use magic links). Without the
``auth_provider = GOOGLE`` OR clause, they'd fall outside cohort 1
AND cohort 2 — a phantom. The "no phantom users" test below pins
that exactly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register every model with metadata
from app.models.magic_link_token import MagicLinkToken
from app.models.user import AuthProvider, User
from app.schemas.admin import UserCohort
from app.services.users import list_inactive_emails, list_users_with_cohort


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


def _utc_now():
    return datetime.now(tz=timezone.utc)


@pytest_asyncio.fixture
async def four_cohort_archetypes(session: AsyncSession) -> dict[str, User]:
    """One user per cohort archetype:
      * ``joined_email`` — completed onboarding via email/password.
      * ``signed_up_only`` — EMAIL provider, name=None, no verified token.
      * ``verified_only_email`` — EMAIL provider, name=None, verified token.
      * ``verified_only_google`` — GOOGLE provider, name=None, no token.
    """
    joined_email = User(
        email="alice@example.com",
        name="Alice",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
    )
    signed_up_only = User(
        email="curious.sam@example.com",
        name=None,
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
    )
    verified_only_email = User(
        email="joel.brown@example.com",
        name=None,
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
    )
    verified_only_google = User(
        email="oauth.ghost@example.com",
        name=None,
        auth_provider=AuthProvider.GOOGLE,
        is_active=True,
    )
    for u in (
        joined_email,
        signed_up_only,
        verified_only_email,
        verified_only_google,
    ):
        session.add(u)
    await session.commit()
    for u in (
        joined_email,
        signed_up_only,
        verified_only_email,
        verified_only_google,
    ):
        await session.refresh(u)

    # Verified token for verified_only_email — pivots their cohort.
    now = _utc_now()
    used_token = MagicLinkToken(
        user_id=verified_only_email.id,
        token_hash="hash-1",
        expires_at=now + timedelta(minutes=15),
        used_at=now - timedelta(hours=1),  # already verified
    )
    # Unused (still-pending) token for signed_up_only — used_at IS NULL
    # so they stay in cohort 1.
    pending_token = MagicLinkToken(
        user_id=signed_up_only.id,
        token_hash="hash-2",
        expires_at=now + timedelta(minutes=15),
        used_at=None,
    )
    session.add(used_token)
    session.add(pending_token)
    await session.commit()

    return {
        "joined_email": joined_email,
        "signed_up_only": signed_up_only,
        "verified_only_email": verified_only_email,
        "verified_only_google": verified_only_google,
    }


# ---------------------------------------------------------------------------
# list_users_with_cohort — cohort filter SQL
# ---------------------------------------------------------------------------
class TestListUsersWithCohort:
    @pytest.mark.asyncio
    async def test_active_cohort_excludes_unjoined(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        page = await list_users_with_cohort(session, cohort=UserCohort.ACTIVE)
        emails = {r.email for r in page.rows}
        assert emails == {"alice@example.com"}
        assert page.total == 1

    @pytest.mark.asyncio
    async def test_all_cohort_returns_everyone(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        page = await list_users_with_cohort(session, cohort=UserCohort.ALL)
        assert page.total == 4
        assert {r.email for r in page.rows} == {
            "alice@example.com",
            "curious.sam@example.com",
            "joel.brown@example.com",
            "oauth.ghost@example.com",
        }

    @pytest.mark.asyncio
    async def test_signed_up_only_cohort(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        page = await list_users_with_cohort(
            session, cohort=UserCohort.SIGNED_UP_ONLY
        )
        # Only Sam — Joel has a verified token, the Google user has
        # auth_provider=GOOGLE.
        assert {r.email for r in page.rows} == {"curious.sam@example.com"}
        assert page.total == 1
        # And the row-level cohort tag matches.
        assert page.rows[0].cohort == UserCohort.SIGNED_UP_ONLY

    @pytest.mark.asyncio
    async def test_verified_only_cohort_includes_oauth(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        page = await list_users_with_cohort(
            session, cohort=UserCohort.VERIFIED_ONLY
        )
        # BOTH Joel (magic-link-verified) AND the Google OAuth ghost.
        assert {r.email for r in page.rows} == {
            "joel.brown@example.com",
            "oauth.ghost@example.com",
        }
        assert page.total == 2
        for row in page.rows:
            assert row.cohort == UserCohort.VERIFIED_ONLY

    @pytest.mark.asyncio
    async def test_no_phantom_users(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        """Every user with ``name=NULL`` lands in exactly one of cohort 1
        or cohort 2. Phantom-user detection.
        """
        cohort1 = await list_users_with_cohort(
            session, cohort=UserCohort.SIGNED_UP_ONLY
        )
        cohort2 = await list_users_with_cohort(
            session, cohort=UserCohort.VERIFIED_ONLY
        )
        emails_in_cohorts = {r.email for r in cohort1.rows} | {
            r.email for r in cohort2.rows
        }
        # All 3 name-NULL users should be accounted for (Sam, Joel, ghost).
        # Alice is joined so doesn't belong to either cohort.
        assert emails_in_cohorts == {
            "curious.sam@example.com",
            "joel.brown@example.com",
            "oauth.ghost@example.com",
        }
        # No overlap — a user can't be in both cohorts simultaneously.
        c1_emails = {r.email for r in cohort1.rows}
        c2_emails = {r.email for r in cohort2.rows}
        assert c1_emails.isdisjoint(c2_emails)

    @pytest.mark.asyncio
    async def test_search_filter(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        # Search ignores cohort default and finds across all matching rows.
        page = await list_users_with_cohort(
            session, cohort=UserCohort.ALL, search="oauth"
        )
        assert page.total == 1
        assert page.rows[0].email == "oauth.ghost@example.com"

    @pytest.mark.asyncio
    async def test_pagination(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        # 4 users; page size 2 should yield 2 rows + total=4.
        page = await list_users_with_cohort(
            session, cohort=UserCohort.ALL, limit=2, offset=0
        )
        assert len(page.rows) == 2
        assert page.total == 4
        page2 = await list_users_with_cohort(
            session, cohort=UserCohort.ALL, limit=2, offset=2
        )
        assert len(page2.rows) == 2
        # No overlap between pages.
        page_ids = {r.id for r in page.rows}
        page2_ids = {r.id for r in page2.rows}
        assert page_ids.isdisjoint(page2_ids)


# ---------------------------------------------------------------------------
# list_inactive_emails — CSV export
# ---------------------------------------------------------------------------
class TestListInactiveEmails:
    @pytest.mark.asyncio
    async def test_both_returns_union(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        rows = await list_inactive_emails(session, cohort="both")
        assert {r.email for r in rows} == {
            "curious.sam@example.com",
            "joel.brown@example.com",
            "oauth.ghost@example.com",
        }
        # Cohorts correctly tagged on the row.
        cohorts_by_email = {r.email: r.cohort for r in rows}
        assert cohorts_by_email["curious.sam@example.com"] == UserCohort.SIGNED_UP_ONLY
        assert cohorts_by_email["joel.brown@example.com"] == UserCohort.VERIFIED_ONLY
        assert cohorts_by_email["oauth.ghost@example.com"] == UserCohort.VERIFIED_ONLY

    @pytest.mark.asyncio
    async def test_signed_up_only_filters_correctly(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        rows = await list_inactive_emails(session, cohort="signed_up_only")
        assert {r.email for r in rows} == {"curious.sam@example.com"}

    @pytest.mark.asyncio
    async def test_verified_only_filters_correctly(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        rows = await list_inactive_emails(session, cohort="verified_only")
        assert {r.email for r in rows} == {
            "joel.brown@example.com",
            "oauth.ghost@example.com",
        }

    @pytest.mark.asyncio
    async def test_excludes_joined_users(
        self, session: AsyncSession, four_cohort_archetypes
    ):
        rows = await list_inactive_emails(session, cohort="both")
        assert "alice@example.com" not in {r.email for r in rows}
