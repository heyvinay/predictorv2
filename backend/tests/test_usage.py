"""Tests for the Usage & Adoption dashboard assembler (v2.212.0).

Pins two contracts:
1. Partial PostHog failure degrades gracefully — DB-sourced sections
   (funnel, feature-adoption row *presence*) still render with
   zeroed/empty PostHog-sourced fields; the endpoint never raises.
2. The wiring is correct end-to-end: adoption % uses the DB submitter
   count as denominator, features sort by adopter count descending,
   and an event outside FEATURE_GROUPS + AMBIENT_EVENTS surfaces under
   uncategorized_events.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register every model
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services import usage
from app.services.usage import (
    _bucket_bounds,
    _bucket_frequency,
    _delta_pct,
    _delta_points,
    _previous_window,
    _range_for_bucket_label,
    _resolve_range,
    get_day_bucket_users,
    get_frequency_bucket_users,
    get_funnel_cohort_users,
    get_hour_bucket_users,
    get_usage_report,
    get_user_features,
)


# ---------------------------------------------------------------------------
# Pure-function unit tests — no DB, no mocks.
# ---------------------------------------------------------------------------
class TestResolveRange:
    def test_7d_default(self):
        now = datetime(2026, 7, 13, tzinfo=timezone.utc)
        since, until, gran = _resolve_range("7d", now)
        assert until == now
        assert since == now - timedelta(days=7)
        assert gran == "day"

    def test_1h(self):
        now = datetime(2026, 7, 13, tzinfo=timezone.utc)
        since, until, gran = _resolve_range("1h", now)
        assert since == now - timedelta(hours=1)
        assert gran == "hour"

    def test_all_anchors_to_tournament_start(self):
        from app.config import TOURNAMENT_START

        now = datetime(2026, 7, 13, tzinfo=timezone.utc)
        since, until, gran = _resolve_range("all", now)
        assert since == TOURNAMENT_START
        assert gran == "week"

    def test_unknown_key_falls_back_to_7d(self):
        now = datetime(2026, 7, 13, tzinfo=timezone.utc)
        since, until, gran = _resolve_range("bogus", now)
        assert since == now - timedelta(days=7)


class TestPreviousWindow:
    def test_same_length_immediately_before(self):
        since = datetime(2026, 7, 6, tzinfo=timezone.utc)
        until = datetime(2026, 7, 13, tzinfo=timezone.utc)
        prev_since, prev_until = _previous_window(since, until)
        assert prev_until == since
        assert prev_since == since - timedelta(days=7)


class TestDeltaHelpers:
    def test_delta_pct_normal(self):
        assert _delta_pct(110, 100) == 10.0

    def test_delta_pct_none_when_prev_zero(self):
        assert _delta_pct(10, 0) is None

    def test_delta_pct_none_when_either_none(self):
        assert _delta_pct(None, 100) is None
        assert _delta_pct(10, None) is None

    def test_delta_points(self):
        assert _delta_points(41.0, 38.0) == 3.0


class TestBucketFrequency:
    def test_zero_bucket_is_population_minus_seen(self):
        freq_map = {1: 5, 3: 2}  # 7 users with >=1 active day
        buckets = _bucket_frequency(freq_map, total_population=10)
        zero = next(b for b in buckets if b.label == "0 days")
        assert zero.count == 3  # 10 - 7
        assert zero.is_dormant is True

    def test_power_bucket_flagged(self):
        buckets = _bucket_frequency({}, total_population=0)
        power_labels = [b.label for b in buckets if b.is_power]
        assert power_labels == ["8-14", "15+"]

    def test_never_goes_negative(self):
        # More "seen" than the DB population (shouldn't happen, but
        # must not crash or return a negative dormant count).
        buckets = _bucket_frequency({1: 100}, total_population=5)
        zero = next(b for b in buckets if b.label == "0 days")
        assert zero.count == 0


# ---------------------------------------------------------------------------
# Assembler integration tests
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_user(s: AsyncSession, email: str, name: str) -> User:
    u = User(email=email, name=name, auth_provider=AuthProvider.EMAIL, is_active=True)
    s.add(u)
    await s.flush()
    return u


_entry_seq = 0


async def _make_submitted_entry(s: AsyncSession, user_id) -> None:
    global _entry_seq
    _entry_seq += 1
    comp = (await s.execute(select(Competition))).scalars().first()
    if comp is None:
        comp = Competition(name="Usage dashboard tests")
        s.add(comp)
        await s.flush()
    entry = PredictionEntry(
        competition_id=comp.id,
        user_id=user_id,
        reference=f"WC26-U{_entry_seq:06d}",
        display_name=f"Entry {_entry_seq}",
        is_disabled=False,
        withdrawn_at=None,
        entry_number=1,
    )
    s.add(entry)
    await s.flush()
    s.add(
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.SUBMITTED,
        )
    )
    await s.flush()


@pytest.mark.asyncio
async def test_partial_posthog_failure_degrades_gracefully(db_session: AsyncSession):
    alice = await _make_user(db_session, "alice@test.com", "Alice")
    await _make_submitted_entry(db_session, alice.id)
    await db_session.commit()

    with patch.object(usage.posthog_read, "_config", lambda: None):
        report = await get_usage_report(db_session)

    assert report.posthog_available is False
    # DB-sourced funnel still renders (count_all_audiences is DB-only
    # for the base counts; its engagement fallback silently no-ops).
    assert report.funnel.submitters == 1
    # Every feature still appears (server-defined catalog — 9 entries,
    # including the property-filtered "Insights tab"), just at zero
    # adoption rather than vanishing.
    assert len(report.feature_adoption) == 9
    assert all(f.users == 0 for f in report.feature_adoption)
    assert all(f.last_used is None for f in report.feature_adoption)
    # PostHog-only tables degrade to empty, not to a misleading
    # "everyone is dormant" claim.
    assert report.power_users_most_active == []
    assert report.power_users_never_engaged == []
    assert report.uncategorized_events == []
    assert report.frequency_buckets == []


@pytest.mark.asyncio
async def test_feature_adoption_and_uncategorized_wiring(db_session: AsyncSession):
    alice = await _make_user(db_session, "alice3@test.com", "Alice")
    bob = await _make_user(db_session, "bob3@test.com", "Bob")
    await _make_submitted_entry(db_session, alice.id)
    await _make_submitted_entry(db_session, bob.id)
    await db_session.commit()

    now = datetime.now(timezone.utc)
    adoption_counts = {
        "leaderboard_view_changed": 2,  # 2/2 submitters -> 100%
        "smartfill_opened": 1,
        "smartfill_applied": 1,  # max(1,1) -> 50%
    }
    all_events_seen = {
        "leaderboard_view_changed": (50, now),
        "smartfill_opened": (10, now - timedelta(days=40)),
        "a_forgotten_new_feature_event": (3, now),  # not in FEATURE_GROUPS
        "$pageview": (9999, now),  # ambient — must stay excluded
    }

    # "Insights tab" (prop_filter=("view", "insights")) shares
    # leaderboard_view_changed with the plain "leaderboard" feature but
    # must get its OWN, narrower count — a flat AsyncMock return_value
    # would give it the same 2/2=100% as "leaderboard" and break the
    # sort-order assertion below for the wrong reason.
    async def fake_unique_users_by_event(events, since, until, uids=None, prop_filter=None):
        if prop_filter:
            return {"leaderboard_view_changed": 1}  # insights_tab -> 1/2 = 50%
        return adoption_counts

    with patch.object(usage.posthog_read, "is_configured", return_value=True), \
         patch.object(
             usage.posthog_read,
             "get_unique_users_by_event",
             AsyncMock(side_effect=fake_unique_users_by_event),
         ), \
         patch.object(
             usage.posthog_read,
             "get_all_events_last_seen",
             AsyncMock(return_value=all_events_seen),
         ), \
         patch.object(
             usage.posthog_read, "get_active_users_series", AsyncMock(return_value=[])
         ), \
         patch.object(
             usage.posthog_read, "get_unique_active_users", AsyncMock(return_value=2)
         ), \
         patch.object(
             usage.posthog_read, "get_sessions_per_user", AsyncMock(return_value=1.5)
         ), \
         patch.object(
             usage.posthog_read,
             "get_new_vs_returning",
             AsyncMock(return_value=(1, 1)),
         ), \
         patch.object(
             usage.posthog_read, "get_stickiness", AsyncMock(return_value=40.0)
         ), \
         patch.object(
             usage.posthog_read, "get_activity_by_hour", AsyncMock(return_value=[0] * 24)
         ), \
         patch.object(
             usage.posthog_read,
             "get_weekly_retention_cohorts",
             AsyncMock(return_value=[]),
         ), \
         patch.object(
             usage.posthog_read,
             "get_engagement_frequency",
             AsyncMock(return_value={}),
         ), \
         patch.object(
             usage.posthog_read,
             "get_active_days_and_sessions_for_users",
             AsyncMock(return_value={}),
         ):
        report = await get_usage_report(db_session)

    by_key = {f.key: f for f in report.feature_adoption}
    assert by_key["leaderboard"].pct == 100
    assert by_key["smartfill"].pct == 50
    assert by_key["smartfill"].frozen is True
    assert by_key["leaderboard"].frozen is False
    # Property-filtered feature gets its OWN narrower count (50%), not
    # the unfiltered "leaderboard" count it shares an event with (100%).
    assert by_key["insights_tab"].pct == 50

    # Sorted descending by adopter count.
    assert report.feature_adoption[0].key == "leaderboard"

    # The forgotten event surfaces; the ambient one and the mapped
    # ones do not.
    uncategorized_names = {u.name for u in report.uncategorized_events}
    assert uncategorized_names == {"a_forgotten_new_feature_event"}


# ---------------------------------------------------------------------------
# Click-through drill-down pure-function unit tests
# ---------------------------------------------------------------------------
class TestBucketBounds:
    def test_day_granularity_date_only_string(self):
        since, until = _bucket_bounds("2026-07-07", "day")
        assert since == datetime(2026, 7, 7, tzinfo=timezone.utc)
        assert until == datetime(2026, 7, 8, tzinfo=timezone.utc)

    def test_hour_granularity_space_separated_string(self):
        # PostHog's toStartOfHour commonly renders "YYYY-MM-DD HH:MM:SS".
        since, until = _bucket_bounds("2026-07-07 14:00:00", "hour")
        assert since == datetime(2026, 7, 7, 14, tzinfo=timezone.utc)
        assert until == datetime(2026, 7, 7, 15, tzinfo=timezone.utc)

    def test_week_granularity(self):
        since, until = _bucket_bounds("2026-07-06", "week")
        assert since == datetime(2026, 7, 6, tzinfo=timezone.utc)
        assert until == datetime(2026, 7, 13, tzinfo=timezone.utc)


class TestRangeForBucketLabel:
    def test_known_labels(self):
        assert _range_for_bucket_label("0 days") == (0, 0)
        assert _range_for_bucket_label("2-3") == (2, 3)
        assert _range_for_bucket_label("15+") == (15, 10_000)

    def test_unknown_label_returns_none(self):
        assert _range_for_bucket_label("bogus") is None


# ---------------------------------------------------------------------------
# Click-through drill-down integration tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_day_bucket_users_maps_ids_to_names(db_session: AsyncSession):
    alice = await _make_user(db_session, "alice4@test.com", "Alice Four")
    await db_session.commit()

    with patch.object(
        usage.posthog_read,
        "get_users_active_in_bucket",
        AsyncMock(
            return_value=[(alice.id, datetime(2026, 7, 7, 9, tzinfo=timezone.utc))]
        ),
    ):
        rows = await get_day_bucket_users(db_session, "2026-07-07", "day", "all")

    assert len(rows) == 1
    assert rows[0].user_id == alice.id
    assert rows[0].name == "Alice Four"
    assert rows[0].last_used == datetime(2026, 7, 7, 9, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_get_day_bucket_users_unparseable_bucket_returns_empty(
    db_session: AsyncSession,
):
    rows = await get_day_bucket_users(db_session, "not-a-date", "day", "all")
    assert rows == []


@pytest.mark.asyncio
async def test_get_hour_bucket_users_maps_ids_to_names(db_session: AsyncSession):
    bob = await _make_user(db_session, "bob4@test.com", "Bob Four")
    await db_session.commit()

    with patch.object(
        usage.posthog_read,
        "get_users_active_at_hour",
        AsyncMock(
            return_value=[(bob.id, datetime(2026, 7, 10, 14, tzinfo=timezone.utc))]
        ),
    ):
        rows = await get_hour_bucket_users(db_session, 14, "7d", "all")

    assert len(rows) == 1
    assert rows[0].user_id == bob.id
    assert rows[0].name == "Bob Four"


@pytest.mark.asyncio
async def test_get_frequency_bucket_users_nonzero_bucket(db_session: AsyncSession):
    alice = await _make_user(db_session, "alice5@test.com", "Alice Five")
    await _make_submitted_entry(db_session, alice.id)
    await db_session.commit()

    with patch.object(
        usage.posthog_read,
        "get_users_by_active_days",
        AsyncMock(return_value=[(alice.id, 3)]),
    ):
        rows = await get_frequency_bucket_users(db_session, "2-3", "7d", "all")

    assert len(rows) == 1
    assert rows[0].user_id == alice.id
    assert rows[0].detail == "3 active days"
    assert rows[0].last_used is None


@pytest.mark.asyncio
async def test_get_frequency_bucket_users_dormant_bucket_is_population_minus_active(
    db_session: AsyncSession,
):
    """The "0 days" bucket can't be queried directly from PostHog — it's
    derived by diffing the full submitter population against whoever
    PostHog says WAS active."""
    active_user = await _make_user(db_session, "active@test.com", "Active User")
    dormant_user = await _make_user(db_session, "dormant@test.com", "Dormant User")
    await _make_submitted_entry(db_session, active_user.id)
    await _make_submitted_entry(db_session, dormant_user.id)
    await db_session.commit()

    with patch.object(
        usage.posthog_read,
        "get_users_by_active_days",
        AsyncMock(return_value=[(active_user.id, 5)]),
    ):
        rows = await get_frequency_bucket_users(db_session, "0 days", "7d", "all")

    assert len(rows) == 1
    assert rows[0].user_id == dormant_user.id
    assert rows[0].detail == "0 active days"


@pytest.mark.asyncio
async def test_get_frequency_bucket_users_unknown_label_returns_empty(
    db_session: AsyncSession,
):
    rows = await get_frequency_bucket_users(db_session, "not-a-bucket", "7d", "all")
    assert rows == []


@pytest.mark.asyncio
async def test_get_funnel_cohort_users_wraps_query_audience(db_session: AsyncSession):
    from app.services.broadcast import AudienceRow

    fake_rows = [AudienceRow(user_id=uuid4(), email="x@test.com", name="X Y")]
    with patch.object(
        usage, "query_audience", AsyncMock(return_value=fake_rows)
    ):
        rows = await get_funnel_cohort_users(db_session, "submitters")

    assert len(rows) == 1
    assert rows[0].name == "X Y"
    assert rows[0].detail == "x@test.com"


@pytest.mark.asyncio
async def test_get_funnel_cohort_users_unknown_cohort_returns_empty(
    db_session: AsyncSession,
):
    rows = await get_funnel_cohort_users(db_session, "not-a-cohort")
    assert rows == []


@pytest.mark.asyncio
async def test_get_user_features_splits_plain_and_property_filtered(
    db_session: AsyncSession,
):
    """"Insights tab" and "Leaderboard views" share an event
    (leaderboard_view_changed) but must get independently-correct
    counts for the SAME user."""
    uid = uuid4()

    plain_usage = {"leaderboard_view_changed": (10, datetime(2026, 7, 1, tzinfo=timezone.utc))}
    insights_usage = {"leaderboard_view_changed": (4, datetime(2026, 7, 2, tzinfo=timezone.utc))}

    async def fake_get_user_feature_usage(user_id, events, since, until, prop_filter=None):
        return insights_usage if prop_filter else plain_usage

    with patch.object(
        usage.posthog_read,
        "get_user_feature_usage",
        AsyncMock(side_effect=fake_get_user_feature_usage),
    ):
        rows = await get_user_features(db_session, uid, "all")

    by_key = {r.key: r for r in rows}
    assert by_key["leaderboard"].count == 10
    assert by_key["insights_tab"].count == 4
    assert by_key["insights_tab"].count != by_key["leaderboard"].count
