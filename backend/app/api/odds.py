"""Odds cache HTTP endpoint.

Plan §9: GET /api/odds returns the current shared odds cache. Unauthenticated
(matches the SvelteKit /odds endpoint's posture) — the SvelteKit /odds is now
a thin proxy that calls this endpoint and returns the result to the client.

The cache itself lives at /data/odds_cache.json. See
backend/app/services/odds_cache.py for the read-through semantics and the
durability contract.
"""

from fastapi import APIRouter

from app.services.odds_cache import get_or_refresh_odds

router = APIRouter()


@router.get("/")
async def get_odds() -> dict:
    """Return the current odds cache, refreshing if stale.

    Always returns HTTP 200. The body contains either:
      - {fetchedAt, remainingRequests, usedRequests, matches}  — success path
      - {error: 'not_configured', matches: []}                  — key unset
      - {error: 'fetch_failed', matches: []}                    — cold-start + upstream failure

    The frontend inspects the body to decide how to react. This 200-always
    posture mirrors the existing SvelteKit /odds endpoint and keeps client
    branching simple.
    """
    return await get_or_refresh_odds()
