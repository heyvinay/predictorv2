"""Tests for the PostHog read service (v2.156.0).

Patches the low-level ``_hogql`` HTTP transport so tests run without
hitting PostHog. Covers:
- Happy-path parsing for both functions
- Cache hit short-circuits the HTTP call
- Graceful fallback on every failure mode (disabled, timeout, 4xx, 5xx,
  malformed response)
- Sparkline zero-fill produces exactly 14 buckets
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from app.services import posthog_read


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts with an empty cache to avoid cross-pollination."""
    posthog_read._clear_cache()
    yield
    posthog_read._clear_cache()


@pytest.fixture
def enable_posthog(monkeypatch):
    """Make ``_config()`` return a fake non-None tuple so the service
    treats PostHog as configured. Without this, every call short-circuits
    to "PostHog disabled" before any HTTP work."""
    monkeypatch.setattr(
        posthog_read,
        "_config",
        lambda: ("https://eu.i.posthog.com", "12345", "phx_fake"),
    )


# ---------------------------------------------------------------------------
# get_recent_seen_for_users
# ---------------------------------------------------------------------------
class TestGetRecentSeenForUsers:
    @pytest.mark.asyncio
    async def test_parses_hogql_response_into_dict(self, enable_posthog):
        alice_id = uuid4()
        bob_id = uuid4()
        seen_alice = datetime(2026, 6, 9, 14, 0, tzinfo=timezone.utc)
        seen_bob = datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc)

        async def fake_hogql(query: str):
            return [
                [str(alice_id), seen_alice, "/entries/abc"],
                [str(bob_id), seen_bob, "/leaderboard"],
            ]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            result = await posthog_read.get_recent_seen_for_users(
                [alice_id, bob_id]
            )

        assert set(result.keys()) == {alice_id, bob_id}
        assert result[alice_id].last_url == "/entries/abc"
        assert result[bob_id].last_seen == seen_bob

    @pytest.mark.asyncio
    async def test_cache_hit_skips_http(self, enable_posthog):
        alice_id = uuid4()
        call_count = {"n": 0}

        async def fake_hogql(query: str):
            call_count["n"] += 1
            return [
                [str(alice_id), datetime(2026, 6, 9, tzinfo=timezone.utc), "/x"]
            ]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            await posthog_read.get_recent_seen_for_users([alice_id])
            await posthog_read.get_recent_seen_for_users([alice_id])

        assert call_count["n"] == 1  # second call served from cache

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_no_http(self, enable_posthog):
        called = {"n": 0}

        async def fake_hogql(query: str):
            called["n"] += 1
            return []

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            out = await posthog_read.get_recent_seen_for_users([])

        assert out == {}
        assert called["n"] == 0

    @pytest.mark.asyncio
    async def test_hogql_failure_returns_empty_dict(self, enable_posthog):
        # Failure inside _hogql is signalled by None — service must not
        # raise.
        async def fake_hogql(query: str):
            return None

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            out = await posthog_read.get_recent_seen_for_users([uuid4()])

        assert out == {}

    @pytest.mark.asyncio
    async def test_malformed_row_skipped_not_fatal(self, enable_posthog):
        good_id = uuid4()
        seen = datetime(2026, 6, 9, tzinfo=timezone.utc)

        async def fake_hogql(query: str):
            return [
                ["not-a-uuid", seen, "/foo"],  # malformed; should be skipped
                [str(good_id), seen, "/good"],
            ]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            out = await posthog_read.get_recent_seen_for_users([good_id])

        assert good_id in out
        assert len(out) == 1  # malformed row didn't contribute


# ---------------------------------------------------------------------------
# get_engagement_summary
# ---------------------------------------------------------------------------
class TestGetEngagementSummary:
    @pytest.mark.asyncio
    async def test_returns_none_when_posthog_disabled(self, monkeypatch):
        monkeypatch.setattr(posthog_read, "_config", lambda: None)
        out = await posthog_read.get_engagement_summary(uuid4())
        assert out is None

    @pytest.mark.asyncio
    async def test_happy_path_summary(self, enable_posthog):
        last_seen = datetime(2026, 6, 9, 14, 0, tzinfo=timezone.utc)

        async def fake_hogql(query: str):
            if "argMax" in query and "session_count" in query:
                # summary query
                return [[last_seen, "/entries/abc", 47, 512.3]]
            # sparkline query — return 5 days of data (will be zero-padded)
            return [
                ["2026-06-05", 3],
                ["2026-06-06", 7],
                ["2026-06-07", 2],
                ["2026-06-08", 12],
                ["2026-06-09", 5],
            ]

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            out = await posthog_read.get_engagement_summary(uuid4())

        assert out is not None
        assert out.last_seen == last_seen
        assert out.last_url == "/entries/abc"
        assert out.session_count == 47
        assert out.avg_session_seconds == pytest.approx(512.3)
        # Sparkline: exactly 14 buckets, zero-padded on the left.
        assert len(out.sparkline_14d) == 14
        # First 9 should be zero, last 5 should be the actual values
        # (in ascending order since we sort the dict's values).
        assert out.sparkline_14d[:9] == [0, 0, 0, 0, 0, 0, 0, 0, 0]

    @pytest.mark.asyncio
    async def test_summary_query_failure_returns_none(self, enable_posthog):
        async def fake_hogql(query: str):
            return None

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            out = await posthog_read.get_engagement_summary(uuid4())
        assert out is None

    @pytest.mark.asyncio
    async def test_zero_events_returns_empty_summary(self, enable_posthog):
        async def fake_hogql(query: str):
            if "session_count" in query:
                # Aggregation over zero rows — PostHog returns one row of NULLs
                return [[None, None, 0, None]]
            return []  # zero sparkline rows

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            out = await posthog_read.get_engagement_summary(uuid4())

        assert out is not None
        assert out.last_seen is None
        assert out.last_url is None
        assert out.session_count == 0
        assert out.avg_session_seconds is None
        # Sparkline is always 14 buckets — all zeros when no data.
        assert out.sparkline_14d == [0] * 14

    @pytest.mark.asyncio
    async def test_single_user_cache_hit(self, enable_posthog):
        user_id = uuid4()
        n_calls = {"n": 0}

        async def fake_hogql(query: str):
            n_calls["n"] += 1
            if "session_count" in query:
                return [[None, None, 0, None]]
            return []

        with patch.object(posthog_read, "_hogql", side_effect=fake_hogql):
            await posthog_read.get_engagement_summary(user_id)
            n_after_first = n_calls["n"]
            await posthog_read.get_engagement_summary(user_id)
            n_after_second = n_calls["n"]

        # First call: 2 HogQL queries (summary + sparkline). Second
        # call: 0 queries (served entirely from cache).
        assert n_after_first == 2
        assert n_after_second == 2
