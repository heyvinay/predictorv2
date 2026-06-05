"""Lazy server-side cache for The Odds API responses.

Plan §9 (2026-06-05): moves the odds cache off per-user-localStorage onto a
single shared JSON file at /data/odds_cache.json. First user to open Smart
Fill after the 4h TTL expires triggers the refresh; subsequent users within
the window reuse the cached file with zero upstream API cost.

Architecture:

    SvelteKit /odds endpoint
        ↓ GET /api/odds
    FastAPI /api/odds endpoint
        ↓ get_or_refresh_odds()
    /data/odds_cache.json
        ↑ refresh from api.the-odds-api.com if stale

Durability contract (mirrors the original client-side oddsCache.ts merge):

    - On upstream failure of ANY kind (HTTP error, timeout, parse error,
      validation failure), keep the existing JSON file untouched and return
      it. Never serve null / empty / corrupted.
    - Merge-on-refresh: a fixture missing from the new API response is
      preserved from the old cache. This matches the existing client-side
      mergeCaches() contract and prevents transient API drops from wiping
      known-good odds for fixtures that bookmakers temporarily stop pricing.

Concurrency: an asyncio.Lock prevents two simultaneous first-users from both
triggering a refresh within a single worker. For multi-worker setups, two
workers could theoretically race at the TTL boundary — accepted as a rare
edge case at our scale (the most you'd waste is 1-2 extra API requests per
refresh window, far below the budget).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

# Cache file lives on the existing ./backend/data:/app/data bind mount —
# persists across container rebuilds without any docker-compose change.
CACHE_PATH = Path("/app/data/odds_cache.json")
TTL = timedelta(hours=4)
ODDS_URL = (
    "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds"
    "?regions=eu&markets=h2h&oddsFormat=decimal"
)

_lock = asyncio.Lock()
log = logging.getLogger(__name__)


def _read_cache() -> dict[str, Any] | None:
    """Return the persisted cache contents, or None if missing/unreadable."""
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text())
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Failed to read odds cache file: %s", e)
        return None


def _is_stale(fetched_at: str) -> bool:
    """True if the cache is older than TTL, OR if the timestamp is unparseable."""
    try:
        parsed = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - parsed
    return age > TTL


def _merge_matches(
    old: list[dict[str, Any]] | None, new: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge a fresh API response into existing cached matches.

    Mirrors the contract from frontend/src/lib/utils/oddsCache.ts:mergeCaches:
      - For each fixture in `new` → use the new version.
      - For each fixture in `old` whose id is NOT in `new` → keep the old.
      - Empty `new` does NOT wipe — catastrophic upstream returning [] still
        leaves us serving last-good data.
    """
    if not old:
        return list(new)
    new_ids = {m.get("id") for m in new if isinstance(m, dict) and m.get("id")}
    preserved_old = [
        m for m in old if isinstance(m, dict) and m.get("id") and m["id"] not in new_ids
    ]
    return list(new) + preserved_old


def _write_atomic(data: dict[str, Any]) -> None:
    """Atomic write via tmp + rename — crash-safe even mid-write."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.rename(tmp, CACHE_PATH)


async def _fetch_from_odds_api(api_key: str) -> dict[str, Any]:
    """Hit The Odds API and return {matches, remainingRequests}.

    Raises on any failure mode. The caller catches everything and falls back
    to the existing cache to honour the durability guarantee.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        url = f"{ODDS_URL}&apiKey={api_key}"
        r = await client.get(url)
        r.raise_for_status()
        matches = r.json()
    if not isinstance(matches, list):
        raise ValueError("Odds API response is not a list")
    remaining = int(r.headers.get("x-requests-remaining", 0))
    used = int(r.headers.get("x-requests-used", 0))
    return {
        "matches": matches,
        "remainingRequests": remaining,
        "usedRequests": used,
    }


async def get_or_refresh_odds() -> dict[str, Any]:
    """Read-through cache. Returns {fetchedAt, remainingRequests, matches}.

    Concurrent first-users at the TTL boundary serialize on `_lock`; the
    second user re-reads the freshly-written cache instead of firing a
    parallel refresh.

    On any upstream failure: returns the existing cache (or `{error: ...}`
    if there's no cache at all yet — the cold-start unfortunately-empty case).
    """
    async with _lock:
        current = _read_cache()
        if current and not _is_stale(current.get("fetchedAt", "")):
            return current

        settings = get_settings()
        api_key = settings.odds_api_key
        if not api_key:
            log.warning("ODDS_API_KEY not configured")
            return current or {"error": "not_configured", "matches": []}

        try:
            fresh = await _fetch_from_odds_api(api_key)
        except Exception as e:  # noqa: BLE001 — durability: catch everything
            log.warning("Odds API refresh failed: %s — keeping existing cache", e)
            return current or {"error": "fetch_failed", "matches": []}

        merged_matches = _merge_matches(
            current.get("matches") if current else None,
            fresh["matches"],
        )
        result = {
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "remainingRequests": fresh["remainingRequests"],
            "usedRequests": fresh["usedRequests"],
            "matches": merged_matches,
        }
        try:
            _write_atomic(result)
        except OSError as e:
            # If we can't write the cache, log + still serve the fresh
            # in-memory result this request. Next request will try again.
            log.warning("Failed to write odds cache file: %s", e)
        return result
