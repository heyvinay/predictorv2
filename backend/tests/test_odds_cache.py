"""Tests for the lazy server-side odds cache (plan §9, 2026-06-05).

Covers:
  - Happy path: missing cache → fetch + write + return.
  - Fresh cache: read + return without fetch (assert no httpx call).
  - Stale cache + valid refresh: fetch + merge + write + return new.
  - Merge contract: old fixtures missing from new response are preserved.
  - Upstream failure: keeps existing cache, fetchedAt unchanged.
  - Cold start with no key: returns {error: 'not_configured'}.
  - Atomic write contract (smoke-checked — no crash injection).

The cache module's behaviour is the durability guarantee: under no failure
mode does the API ever serve null/empty/corrupted data to the frontend.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import odds_cache


@pytest.fixture
def tmp_cache_path(tmp_path, monkeypatch):
    """Redirect CACHE_PATH to a per-test tempfile so tests can't collide."""
    p = tmp_path / "odds_cache.json"
    monkeypatch.setattr(odds_cache, "CACHE_PATH", p)
    return p


@pytest.fixture
def mock_settings_with_key(monkeypatch):
    """Force settings.odds_api_key to a non-empty value."""

    class FakeSettings:
        odds_api_key = "fake-test-key"

    monkeypatch.setattr(odds_cache, "get_settings", lambda: FakeSettings())


@pytest.fixture
def mock_settings_no_key(monkeypatch):
    """Force settings.odds_api_key to empty (graceful-degradation path)."""

    class FakeSettings:
        odds_api_key = ""

    monkeypatch.setattr(odds_cache, "get_settings", lambda: FakeSettings())


def _make_match(match_id: str, home: str, away: str) -> dict:
    """Minimal valid OddsApiMatch shape for test fixtures."""
    return {
        "id": match_id,
        "sport_key": "soccer_fifa_world_cup",
        "commence_time": "2026-06-15T12:00:00Z",
        "home_team": home,
        "away_team": away,
        "bookmakers": [],
    }


def _mock_httpx_get(matches: list[dict], remaining: int = 480, used: int = 20):
    """Patch httpx.AsyncClient.get to return a mock response with `matches`.

    httpx.Response.raise_for_status() requires the response to have a request
    attached — without it, `raise_for_status` itself raises a RuntimeError
    even on 200. We attach a dummy Request so the 200 path passes cleanly.
    """
    response = httpx.Response(
        200,
        json=matches,
        headers={
            "x-requests-remaining": str(remaining),
            "x-requests-used": str(used),
        },
        request=httpx.Request("GET", "https://example.test/odds"),
    )
    return patch.object(
        httpx.AsyncClient,
        "get",
        new=AsyncMock(return_value=response),
    )


@pytest.mark.asyncio
async def test_happy_path_no_existing_cache_fetches_and_writes(
    tmp_cache_path, mock_settings_with_key
):
    """First call with no cache → calls upstream + writes JSON."""
    matches = [_make_match("m1", "England", "Brazil")]
    with _mock_httpx_get(matches):
        result = await odds_cache.get_or_refresh_odds()

    assert "matches" in result
    assert len(result["matches"]) == 1
    assert result["matches"][0]["id"] == "m1"
    assert "fetchedAt" in result
    assert result["remainingRequests"] == 480
    # File was written
    assert tmp_cache_path.exists()
    persisted = json.loads(tmp_cache_path.read_text())
    assert persisted["matches"][0]["id"] == "m1"


@pytest.mark.asyncio
async def test_fresh_cache_skips_upstream_call(
    tmp_cache_path, mock_settings_with_key
):
    """Fresh cache (< TTL) → no upstream call, returns cached."""
    # Seed a fresh cache file
    fresh = {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "remainingRequests": 400,
        "usedRequests": 100,
        "matches": [_make_match("cached", "Spain", "France")],
    }
    tmp_cache_path.write_text(json.dumps(fresh))

    # Patch httpx to fail loudly if it's called — proving we didn't fetch
    with patch.object(
        httpx.AsyncClient,
        "get",
        new=AsyncMock(side_effect=AssertionError("Should not have hit upstream")),
    ):
        result = await odds_cache.get_or_refresh_odds()

    assert result["matches"][0]["id"] == "cached"
    assert result["remainingRequests"] == 400


@pytest.mark.asyncio
async def test_stale_cache_triggers_refresh(
    tmp_cache_path, mock_settings_with_key
):
    """Cache older than TTL → fetches + writes new."""
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    stale = {
        "fetchedAt": stale_ts,
        "remainingRequests": 100,
        "usedRequests": 400,
        "matches": [_make_match("old", "Argentina", "Saudi Arabia")],
    }
    tmp_cache_path.write_text(json.dumps(stale))

    new_matches = [_make_match("new", "Mexico", "South Africa")]
    with _mock_httpx_get(new_matches, remaining=475, used=25):
        result = await odds_cache.get_or_refresh_odds()

    # Refresh happened — fetchedAt advanced, new fixtures present.
    assert result["fetchedAt"] != stale_ts
    assert result["remainingRequests"] == 475
    # Critical: the old fixture was MERGED IN (durability — old fixtures
    # missing from new response are preserved per oddsCache.ts contract).
    ids = {m["id"] for m in result["matches"]}
    assert "new" in ids
    assert "old" in ids  # merge-on-refresh kept it


@pytest.mark.asyncio
async def test_upstream_http_error_keeps_existing_cache(
    tmp_cache_path, mock_settings_with_key
):
    """HTTP 500 from upstream → return existing cache unchanged."""
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    existing = {
        "fetchedAt": stale_ts,
        "remainingRequests": 100,
        "usedRequests": 400,
        "matches": [_make_match("preserved", "England", "Brazil")],
    }
    tmp_cache_path.write_text(json.dumps(existing))

    error_response = httpx.Response(
        500,
        json={"error": "Internal"},
        request=httpx.Request("GET", "https://example.test/odds"),
    )
    with patch.object(
        httpx.AsyncClient,
        "get",
        new=AsyncMock(return_value=error_response),
    ):
        result = await odds_cache.get_or_refresh_odds()

    # Existing cache returned unchanged
    assert result["matches"][0]["id"] == "preserved"
    assert result["fetchedAt"] == stale_ts  # fetchedAt NOT updated


@pytest.mark.asyncio
async def test_upstream_timeout_keeps_existing_cache(
    tmp_cache_path, mock_settings_with_key
):
    """Network timeout from upstream → return existing cache unchanged."""
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    existing = {
        "fetchedAt": stale_ts,
        "remainingRequests": 100,
        "usedRequests": 400,
        "matches": [_make_match("preserved", "England", "Brazil")],
    }
    tmp_cache_path.write_text(json.dumps(existing))

    with patch.object(
        httpx.AsyncClient,
        "get",
        new=AsyncMock(side_effect=httpx.TimeoutException("timed out")),
    ):
        result = await odds_cache.get_or_refresh_odds()

    assert result["matches"][0]["id"] == "preserved"
    assert result["fetchedAt"] == stale_ts


@pytest.mark.asyncio
async def test_no_api_key_returns_not_configured(
    tmp_cache_path, mock_settings_no_key
):
    """Empty API key + no existing cache → graceful 'not_configured' error."""
    # No cache file — cold-start with no key
    assert not tmp_cache_path.exists()
    result = await odds_cache.get_or_refresh_odds()
    assert result.get("error") == "not_configured"
    assert result["matches"] == []


@pytest.mark.asyncio
async def test_no_api_key_returns_existing_cache(
    tmp_cache_path, mock_settings_no_key
):
    """Empty key BUT existing cache → return the cache (still useful)."""
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    existing = {
        "fetchedAt": stale_ts,
        "remainingRequests": 100,
        "usedRequests": 400,
        "matches": [_make_match("preserved", "England", "Brazil")],
    }
    tmp_cache_path.write_text(json.dumps(existing))

    result = await odds_cache.get_or_refresh_odds()
    # Key unset, can't refresh — but existing cache is still served.
    assert result["matches"][0]["id"] == "preserved"


def test_merge_matches_preserves_old_not_in_new():
    """Pure function: old fixtures missing from new are kept."""
    old = [
        _make_match("a", "X", "Y"),
        _make_match("b", "P", "Q"),
    ]
    new = [_make_match("a", "X", "Y")]  # b missing from new
    merged = odds_cache._merge_matches(old, new)
    ids = {m["id"] for m in merged}
    assert ids == {"a", "b"}  # b preserved


def test_merge_matches_empty_new_keeps_all_old():
    """Catastrophic upstream returning [] — all old fixtures preserved."""
    old = [
        _make_match("a", "X", "Y"),
        _make_match("b", "P", "Q"),
    ]
    merged = odds_cache._merge_matches(old, [])
    ids = {m["id"] for m in merged}
    assert ids == {"a", "b"}


def test_merge_matches_no_old_returns_new():
    """No existing cache → just return the new matches."""
    new = [_make_match("a", "X", "Y")]
    merged = odds_cache._merge_matches(None, new)
    assert merged == new


def test_is_stale_recent_returns_false():
    fresh = datetime.now(timezone.utc).isoformat()
    assert odds_cache._is_stale(fresh) is False


def test_is_stale_old_returns_true():
    old = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    assert odds_cache._is_stale(old) is True


def test_is_stale_unparseable_returns_true():
    """Defensive: unparseable timestamp → treat as stale, trigger refresh."""
    assert odds_cache._is_stale("not-a-date") is True
    assert odds_cache._is_stale("") is True


@pytest.mark.asyncio
async def test_atomic_write_smoke(tmp_cache_path, mock_settings_with_key):
    """Smoke-check that _write_atomic produces a valid JSON file."""
    matches = [_make_match("a", "X", "Y")]
    with _mock_httpx_get(matches):
        await odds_cache.get_or_refresh_odds()

    assert tmp_cache_path.exists()
    # File contents must be valid JSON (no truncation, no partial write)
    parsed = json.loads(tmp_cache_path.read_text())
    assert "matches" in parsed
    assert "fetchedAt" in parsed
    # No leftover .tmp file
    tmp_sibling = tmp_cache_path.with_suffix(".json.tmp")
    assert not tmp_sibling.exists()
