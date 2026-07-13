"""Tests for the Usage & Adoption dashboard's PostHog read helpers
(v2.212.0), added to app.services.posthog_read.

Same pattern as test_posthog_read.py: patch the low-level ``_hogql``
transport (or ``_config`` for the disabled case) so tests run without
hitting PostHog. Covers happy-path parsing and the silent-failure
contract for each new helper.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.services import posthog_read

SINCE = datetime(2026, 6, 11, tzinfo=timezone.utc)
UNTIL = datetime(2026, 6, 18, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clear_cache():
    posthog_read._clear_cache()
    yield
    posthog_read._clear_cache()


@pytest.fixture
def enable_posthog(monkeypatch):
    monkeypatch.setattr(
        posthog_read,
        "_config",
        lambda: ("https://eu.i.posthog.com", "12345", "phx_fake"),
    )


@pytest.fixture
def disable_posthog(monkeypatch):
    monkeypatch.setattr(posthog_read, "_config", lambda: None)


class TestIsConfigured:
    def test_true_when_config_present(self, enable_posthog):
        assert posthog_read.is_configured() is True

    def test_false_when_config_absent(self, disable_posthog):
        assert posthog_read.is_configured() is False


class TestGetActiveUsersSeries:
    @pytest.mark.asyncio
    async def test_parses_buckets(self, enable_posthog):
        async def fake_hogql(query):
            return [["2026-06-11", 5], ["2026-06-12", 8]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_active_users_series(SINCE, UNTIL, "day")

        assert [p.count for p in result] == [5, 8]

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, disable_posthog):
        result = await posthog_read.get_active_users_series(SINCE, UNTIL, "day")
        assert result == []


class TestGetUniqueActiveUsers:
    @pytest.mark.asyncio
    async def test_happy_path(self, enable_posthog):
        with patch.object(
            posthog_read, "_hogql", side_effect=lambda q: [[42]]
        ):
            result = await posthog_read.get_unique_active_users(SINCE, UNTIL)
        assert result == 42

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, disable_posthog):
        assert await posthog_read.get_unique_active_users(SINCE, UNTIL) is None


class TestGetStickiness:
    @pytest.mark.asyncio
    async def test_short_window_returns_none_without_querying(self, enable_posthog):
        called = {"n": 0}

        async def fake_hogql(q):
            called["n"] += 1
            return [[1]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_stickiness(
                SINCE, SINCE + timedelta(hours=1)
            )
        assert result is None
        assert called["n"] == 0  # short-circuited before any HTTP call

    @pytest.mark.asyncio
    async def test_computes_percentage(self, enable_posthog):
        # avg_dau query first, then mau query (order in source).
        responses = iter([[[10.0]], [[25]]])

        async def fake_hogql(q):
            return next(responses)

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_stickiness(SINCE, UNTIL)
        assert result == 40.0  # 10 / 25 * 100

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, disable_posthog):
        assert await posthog_read.get_stickiness(SINCE, UNTIL) is None


class TestGetSessionsPerUser:
    @pytest.mark.asyncio
    async def test_happy_path(self, enable_posthog):
        with patch.object(posthog_read, "_hogql", side_effect=lambda q: [[30, 10]]):
            result = await posthog_read.get_sessions_per_user(SINCE, UNTIL)
        assert result == 3.0

    @pytest.mark.asyncio
    async def test_zero_users_returns_none(self, enable_posthog):
        with patch.object(posthog_read, "_hogql", side_effect=lambda q: [[0, 0]]):
            result = await posthog_read.get_sessions_per_user(SINCE, UNTIL)
        assert result is None


class TestGetNewVsReturning:
    @pytest.mark.asyncio
    async def test_happy_path(self, enable_posthog):
        with patch.object(posthog_read, "_hogql", side_effect=lambda q: [[3, 12]]):
            result = await posthog_read.get_new_vs_returning(SINCE, UNTIL)
        assert result == (3, 12)

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, disable_posthog):
        assert await posthog_read.get_new_vs_returning(SINCE, UNTIL) is None


class TestGetActivityByHour:
    @pytest.mark.asyncio
    async def test_zero_fills_24_buckets(self, enable_posthog):
        async def fake_hogql(q):
            return [[9, 5], [20, 40]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_activity_by_hour(SINCE, UNTIL)
        assert len(result) == 24
        assert result[9] == 5
        assert result[20] == 40
        assert result[0] == 0

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, disable_posthog):
        assert await posthog_read.get_activity_by_hour(SINCE, UNTIL) == []


class TestGetWeeklyRetentionCohorts:
    @pytest.mark.asyncio
    async def test_builds_pct_by_offset(self, enable_posthog):
        # Cohort week 2026-06-08: 10 users week0, 8 week1 (offset 1), 6 week2.
        async def fake_hogql(q):
            return [
                ["2026-06-08", "2026-06-08", 10],
                ["2026-06-08", "2026-06-15", 8],
                ["2026-06-08", "2026-06-22", 6],
            ]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_weekly_retention_cohorts()

        assert len(result) == 1
        row = result[0]
        assert row["cohort_week"] == "2026-06-08"
        assert row["pct_by_offset"][0] == 100
        assert row["pct_by_offset"][1] == 80
        assert row["pct_by_offset"][2] == 60
        assert row["pct_by_offset"][3] is None

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, disable_posthog):
        assert await posthog_read.get_weekly_retention_cohorts() == []


class TestGetEngagementFrequency:
    @pytest.mark.asyncio
    async def test_parses_distribution(self, enable_posthog):
        async def fake_hogql(q):
            return [[1, 5], [3, 2], [10, 1]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_engagement_frequency(SINCE, UNTIL)
        assert result == {1: 5, 3: 2, 10: 1}

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, disable_posthog):
        assert await posthog_read.get_engagement_frequency(SINCE, UNTIL) == {}


class TestGetUniqueUsersByEvent:
    @pytest.mark.asyncio
    async def test_happy_path(self, enable_posthog):
        async def fake_hogql(q):
            return [["smartfill_opened", 7], ["bracket_tab_opened", 3]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_unique_users_by_event(
                ["smartfill_opened", "bracket_tab_opened"], SINCE, UNTIL
            )
        assert result == {"smartfill_opened": 7, "bracket_tab_opened": 3}

    @pytest.mark.asyncio
    async def test_empty_events_returns_empty_no_http(self, enable_posthog):
        called = {"n": 0}

        async def fake_hogql(q):
            called["n"] += 1
            return []

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_unique_users_by_event([], SINCE, UNTIL)
        assert result == {}
        assert called["n"] == 0


class TestGetAllEventsLastSeen:
    @pytest.mark.asyncio
    async def test_parses_count_and_last_seen(self, enable_posthog):
        # ★ Regression (2026-07-13): PostHog's HogQL JSON API returns
        # timestamp columns as ISO 8601 STRINGS, never Python datetime
        # objects — the previous version of this test used a real
        # `datetime(...)` here, which masked a real bug (a raw string
        # passed straight to `aware_utc()`, which only normalises
        # tzinfo on an already-a-datetime value and raises
        # AttributeError on a string) that 500'd the Usage & Adoption
        # dashboard in production. Always mock HogQL timestamp columns
        # as strings, matching the real wire format.
        async def fake_hogql(q):
            return [["smartfill_opened", 217, "2026-07-01T00:00:00+00:00"]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_all_events_last_seen()
        count, last_seen = result["smartfill_opened"]
        assert count == 217
        assert last_seen == datetime(2026, 7, 1, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, disable_posthog):
        assert await posthog_read.get_all_events_last_seen() == {}


class TestGetActiveDaysAndSessionsForUsers:
    @pytest.mark.asyncio
    async def test_happy_path(self, enable_posthog):
        uid = uuid4()

        async def fake_hogql(q):
            return [[str(uid), 12, 15]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_active_days_and_sessions_for_users(
                [uid], SINCE
            )
        assert result[uid].active_days == 12
        assert result[uid].sessions == 15

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_no_http(self, enable_posthog):
        called = {"n": 0}

        async def fake_hogql(q):
            called["n"] += 1
            return []

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_active_days_and_sessions_for_users(
                [], SINCE
            )
        assert result == {}
        assert called["n"] == 0


class TestGetAdoptersForEvents:
    @pytest.mark.asyncio
    async def test_happy_path_orders_newest_first(self, enable_posthog):
        # String timestamps, matching PostHog's real HogQL JSON wire
        # format — see the regression note on TestGetAllEventsLastSeen.
        uid1, uid2 = uuid4(), uuid4()

        async def fake_hogql(q):
            return [
                [str(uid1), "2026-07-10T00:00:00+00:00"],
                [str(uid2), "2026-07-01T00:00:00+00:00"],
            ]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_adopters_for_events(
                ["smartfill_opened"], SINCE, UNTIL
            )
        assert result[0][0] == uid1
        assert result[0][1] == datetime(2026, 7, 10, tzinfo=timezone.utc)
        assert result[1][0] == uid2

    @pytest.mark.asyncio
    async def test_empty_events_returns_empty(self, enable_posthog):
        result = await posthog_read.get_adopters_for_events([], SINCE, UNTIL)
        assert result == []


class TestPropFilter:
    """get_unique_users_by_event / get_adopters_for_events with
    prop_filter — powers property-narrowed features (e.g. "Insights
    tab" = leaderboard_view_changed WHERE view='insights')."""

    @pytest.mark.asyncio
    async def test_unique_users_by_event_includes_property_clause(self, enable_posthog):
        captured = {}

        async def fake_hogql(q):
            captured["query"] = q
            return [["leaderboard_view_changed", 3]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_unique_users_by_event(
                ["leaderboard_view_changed"],
                SINCE,
                UNTIL,
                prop_filter=("view", "insights"),
            )
        assert result == {"leaderboard_view_changed": 3}
        assert "properties.view = 'insights'" in captured["query"]

    @pytest.mark.asyncio
    async def test_no_prop_filter_omits_property_clause(self, enable_posthog):
        captured = {}

        async def fake_hogql(q):
            captured["query"] = q
            return [["leaderboard_view_changed", 5]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            await posthog_read.get_unique_users_by_event(
                ["leaderboard_view_changed"], SINCE, UNTIL
            )
        assert "properties." not in captured["query"]

    @pytest.mark.asyncio
    async def test_adopters_for_events_includes_property_clause(self, enable_posthog):
        captured = {}
        uid = uuid4()

        async def fake_hogql(q):
            captured["query"] = q
            return [[str(uid), "2026-07-10T00:00:00+00:00"]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_adopters_for_events(
                ["leaderboard_view_changed"],
                SINCE,
                UNTIL,
                prop_filter=("view", "insights"),
            )
        assert result[0][0] == uid
        assert "properties.view = 'insights'" in captured["query"]


class TestGetUsersActiveInBucket:
    @pytest.mark.asyncio
    async def test_happy_path(self, enable_posthog):
        uid = uuid4()

        async def fake_hogql(q):
            return [[str(uid), "2026-06-11T09:30:00+00:00"]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_users_active_in_bucket(SINCE, UNTIL)
        assert result == [(uid, datetime(2026, 6, 11, 9, 30, tzinfo=timezone.utc))]

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, disable_posthog):
        assert await posthog_read.get_users_active_in_bucket(SINCE, UNTIL) == []


class TestGetUsersActiveAtHour:
    @pytest.mark.asyncio
    async def test_happy_path_filters_by_hour(self, enable_posthog):
        captured = {}
        uid = uuid4()

        async def fake_hogql(q):
            captured["query"] = q
            return [[str(uid), "2026-06-15T14:22:00+00:00"]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_users_active_at_hour(14, SINCE, UNTIL)
        assert result == [(uid, datetime(2026, 6, 15, 14, 22, tzinfo=timezone.utc))]
        assert "toHour(timestamp) = 14" in captured["query"]

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, disable_posthog):
        assert await posthog_read.get_users_active_at_hour(14, SINCE, UNTIL) == []


class TestGetUsersByActiveDays:
    @pytest.mark.asyncio
    async def test_happy_path(self, enable_posthog):
        uid = uuid4()

        async def fake_hogql(q):
            return [[str(uid), 5]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_users_by_active_days(SINCE, UNTIL, 4, 7)
        assert result == [(uid, 5)]

    @pytest.mark.asyncio
    async def test_lo_zero_or_negative_returns_empty_no_http(self, enable_posthog):
        called = {"n": 0}

        async def fake_hogql(q):
            called["n"] += 1
            return []

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_users_by_active_days(SINCE, UNTIL, 0, 0)
        assert result == []
        assert called["n"] == 0

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, disable_posthog):
        assert await posthog_read.get_users_by_active_days(SINCE, UNTIL, 1, 3) == []


class TestGetUserFeatureUsage:
    @pytest.mark.asyncio
    async def test_happy_path(self, enable_posthog):
        uid = uuid4()

        async def fake_hogql(q):
            return [["smartfill_opened", 4, "2026-06-15T10:00:00+00:00"]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_user_feature_usage(
                uid, ["smartfill_opened"], SINCE, UNTIL
            )
        count, last_used = result["smartfill_opened"]
        assert count == 4
        assert last_used == datetime(2026, 6, 15, 10, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_prop_filter_narrows_query(self, enable_posthog):
        captured = {}

        async def fake_hogql(q):
            captured["query"] = q
            return [["leaderboard_view_changed", 2, "2026-06-15T10:00:00+00:00"]]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            await posthog_read.get_user_feature_usage(
                uuid4(),
                ["leaderboard_view_changed"],
                SINCE,
                UNTIL,
                prop_filter=("view", "insights"),
            )
        assert "properties.view = 'insights'" in captured["query"]

    @pytest.mark.asyncio
    async def test_empty_events_returns_empty_no_http(self, enable_posthog):
        called = {"n": 0}

        async def fake_hogql(q):
            called["n"] += 1
            return []

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_user_feature_usage(uuid4(), [], SINCE, UNTIL)
        assert result == {}
        assert called["n"] == 0

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, disable_posthog):
        assert await posthog_read.get_user_feature_usage(uuid4(), ["x"], SINCE, UNTIL) == {}
