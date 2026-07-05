"""Tests for v2.176.0 broadcast cohorts: Pool Ghost + Lapsing.

The new cohorts use a hybrid engagement signal:
  - Primary: ``User.last_seen_at`` column
  - Fallback: PostHog ``$pageview`` MAX (via posthog_read.get_last_pageview...)

PostHog failures degrade silently — the predicates fall back to
column-only behaviour with no error propagating to the user. This
file pins all four cases.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register every model
from app.config import TOURNAMENT_START
from app.models.competition import Competition
from app.models.entry import (
    EntryStatus,
    PredictionEntry,
    PredictionEntryPhase,
)
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services.broadcast import (
    BroadcastSegment,
    count_audience,
    query_audience,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_user(
    s: AsyncSession,
    *,
    email: str,
    name: str = "Test User",
    last_seen_at: datetime | None = None,
) -> User:
    u = User(
        email=email,
        name=name,
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
        last_seen_at=last_seen_at,
    )
    s.add(u)
    await s.flush()
    return u


async def _get_or_create_competition(s: AsyncSession) -> Competition:
    """Return the session's Competition, creating one on demand.

    PredictionEntry.competition_id is NOT NULL (v2.x schema); every entry
    must attach to a Competition row. These tests only care about entry
    eligibility signals, not competition semantics, so a bare-minimum
    Competition row is sufficient.
    """
    from sqlalchemy import select
    existing = (await s.execute(select(Competition))).scalars().first()
    if existing is not None:
        return existing
    comp = Competition(name="Broadcast cohort tests")
    s.add(comp)
    await s.flush()
    return comp


_entry_seq = 0


async def _make_eligible_submitted_entry(s: AsyncSession, user_id) -> None:
    global _entry_seq
    _entry_seq += 1
    comp = await _get_or_create_competition(s)
    entry = PredictionEntry(
        competition_id=comp.id,
        user_id=user_id,
        reference=f"WC26-{_entry_seq:06d}",
        display_name=f"Entry {_entry_seq}",
        is_disabled=False,
        withdrawn_at=None,
        entry_number=1,
    )
    s.add(entry)
    await s.flush()
    phase = PredictionEntryPhase(
        entry_id=entry.id,
        phase=PredictionPhase.PHASE_1,
        status=EntryStatus.SUBMITTED,
    )
    s.add(phase)
    await s.flush()


# Empty PostHog stub — engagement signal degrades to column-only.
_EMPTY_PH = AsyncMock(return_value={})


# ---------------------------------------------------------------------------
# Pool Ghost — eligible + no engagement since TOURNAMENT_START
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pool_ghost_includes_only_users_with_no_post_kickoff_signal(
    db_session: AsyncSession,
):
    """Pool Ghost: submitted-eligible AND no engagement since kickoff."""
    pre_kickoff = TOURNAMENT_START - timedelta(days=2)
    post_kickoff = TOURNAMENT_START + timedelta(hours=4)

    # A: submitted, last_seen_at AFTER kickoff → NOT ghost.
    u_a = await _make_user(
        db_session,
        email="a@test.com",
        name="A Active",
        last_seen_at=post_kickoff,
    )
    await _make_eligible_submitted_entry(db_session, u_a.id)

    # B: submitted, last_seen_at BEFORE kickoff → IN ghost.
    u_b = await _make_user(
        db_session,
        email="b@test.com",
        name="B Ghost",
        last_seen_at=pre_kickoff,
    )
    await _make_eligible_submitted_entry(db_session, u_b.id)

    # C: submitted, last_seen_at NULL (never seen) → IN ghost.
    u_c = await _make_user(
        db_session,
        email="c@test.com",
        name="C Never",
        last_seen_at=None,
    )
    await _make_eligible_submitted_entry(db_session, u_c.id)

    # D: NEVER SUBMITTED → NOT ghost (eligibility filter).
    await _make_user(
        db_session,
        email="d@test.com",
        name="D Non-Participant",
        last_seen_at=pre_kickoff,
    )

    await db_session.commit()

    # PostHog stub returns empty — pure column-only behaviour.
    with patch(
        "app.services.posthog_read.get_last_pageview_for_users_since",
        _EMPTY_PH,
    ):
        rows = await query_audience(db_session, BroadcastSegment.POOL_GHOST)
        emails = {r.email for r in rows}

    assert emails == {"b@test.com", "c@test.com"}, (
        f"Pool Ghost should contain B (pre-kickoff last_seen) + C (NULL "
        f"last_seen), got {emails}"
    )


@pytest.mark.asyncio
async def test_pool_ghost_excluded_when_posthog_shows_activity(
    db_session: AsyncSession,
):
    """PostHog fallback rescues users whose column says ghost but who DID
    visit (e.g. persistent session, no audit-eligible action)."""
    pre_kickoff = TOURNAMENT_START - timedelta(days=2)
    post_kickoff = TOURNAMENT_START + timedelta(hours=4)

    # Submitted, column says pre-kickoff (would be ghost), but PostHog has them.
    u_x = await _make_user(
        db_session,
        email="x@test.com",
        name="X Has Posthog",
        last_seen_at=pre_kickoff,
    )
    await _make_eligible_submitted_entry(db_session, u_x.id)
    await db_session.commit()

    # PostHog stub: x@test.com active since kickoff → not a ghost.
    ph_stub = AsyncMock(return_value={u_x.id: post_kickoff})
    with patch(
        "app.services.posthog_read.get_last_pageview_for_users_since",
        ph_stub,
    ):
        rows = await query_audience(db_session, BroadcastSegment.POOL_GHOST)
        emails = {r.email for r in rows}

    assert emails == set(), (
        f"PostHog should rescue X from Pool Ghost; got {emails}"
    )


@pytest.mark.asyncio
async def test_pool_ghost_silent_failure_when_posthog_raises(
    db_session: AsyncSession,
):
    """ANY PostHog failure → empty dict + WARN log, predicate keeps working.

    Hard rule: no exception propagates into the request path.
    """
    pre_kickoff = TOURNAMENT_START - timedelta(days=2)

    u = await _make_user(
        db_session,
        email="silent@test.com",
        name="Silent Fail",
        last_seen_at=pre_kickoff,
    )
    await _make_eligible_submitted_entry(db_session, u.id)
    await db_session.commit()

    failing_ph = AsyncMock(side_effect=RuntimeError("PostHog down"))
    with patch(
        "app.services.posthog_read.get_last_pageview_for_users_since",
        failing_ph,
    ):
        # Must NOT raise — the engagement-input builder catches everything.
        count = await count_audience(db_session, BroadcastSegment.POOL_GHOST)

    assert count == 1, (
        "Expected silent degradation to column-only — user still classified "
        f"as ghost based on last_seen_at; got count={count}"
    )


# ---------------------------------------------------------------------------
# Lapsing — eligible + last signal in [3d, 7d) ago
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lapsing_window_3_to_7_days_ago(db_session: AsyncSession):
    """Lapsing: column or PostHog signal falls in [stale, fresh) window."""
    now = datetime.now(timezone.utc)
    one_day_ago = now - timedelta(days=1)
    five_days_ago = now - timedelta(days=5)
    ten_days_ago = now - timedelta(days=10)

    # A: 1d ago → fresh, NOT lapsing.
    u_a = await _make_user(
        db_session, email="la@test.com", name="A", last_seen_at=one_day_ago
    )
    await _make_eligible_submitted_entry(db_session, u_a.id)

    # B: 5d ago → IN lapsing.
    u_b = await _make_user(
        db_session, email="lb@test.com", name="B", last_seen_at=five_days_ago
    )
    await _make_eligible_submitted_entry(db_session, u_b.id)

    # C: 10d ago → NOT lapsing (graduates toward Pool Ghost zone).
    u_c = await _make_user(
        db_session, email="lc@test.com", name="C", last_seen_at=ten_days_ago
    )
    await _make_eligible_submitted_entry(db_session, u_c.id)

    # D: NULL last_seen → NOT lapsing (Pool Ghost candidate).
    u_d = await _make_user(
        db_session, email="ld@test.com", name="D", last_seen_at=None
    )
    await _make_eligible_submitted_entry(db_session, u_d.id)

    await db_session.commit()

    with patch(
        "app.services.posthog_read.get_last_pageview_for_users_since",
        _EMPTY_PH,
    ):
        rows = await query_audience(db_session, BroadcastSegment.LAPSING)
        emails = {r.email for r in rows}

    assert emails == {"lb@test.com"}, (
        f"Only B (5d ago) should be lapsing, got {emails}"
    )


@pytest.mark.asyncio
async def test_pool_ghost_and_lapsing_mutually_exclusive(
    db_session: AsyncSession,
):
    """Pool Ghost ∩ Lapsing = ∅ — same DB state, no user in both."""
    now = datetime.now(timezone.utc)
    pre_kickoff = TOURNAMENT_START - timedelta(days=2)
    one_day_ago = now - timedelta(days=1)
    five_days_ago = now - timedelta(days=5)

    for email, name, ls in [
        ("m1@test.com", "M1", one_day_ago),
        ("m2@test.com", "M2", five_days_ago),
        ("m3@test.com", "M3", pre_kickoff),
        ("m4@test.com", "M4", None),
    ]:
        u = await _make_user(db_session, email=email, name=name, last_seen_at=ls)
        await _make_eligible_submitted_entry(db_session, u.id)

    await db_session.commit()

    with patch(
        "app.services.posthog_read.get_last_pageview_for_users_since",
        _EMPTY_PH,
    ):
        ghosts = {r.email for r in await query_audience(db_session, BroadcastSegment.POOL_GHOST)}
        lapsing = {r.email for r in await query_audience(db_session, BroadcastSegment.LAPSING)}

    assert ghosts & lapsing == set(), (
        f"Pool Ghost and Lapsing must be disjoint, intersection: {ghosts & lapsing}"
    )
