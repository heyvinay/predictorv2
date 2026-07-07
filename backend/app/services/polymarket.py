"""Polymarket team-to-reach-stage probabilities.

Polymarket runs a separate binary Yes/No market per team for "will this
team reach round X" at every knockout stage (round_of_16 through the
final), plus a "World Cup Winner" outright market. Unlike The Odds
API's per-fixture h2h odds (team_match.py), these markets are keyed by
team + target stage rather than by a specific fixture — they price a
team's chances several rounds before it has a real, scheduled opponent,
which is exactly the gap load_ko_match_win_probabilities's h2h path
structurally can't cover (there's no odds line for "TBD vs TBD").

No API key needed — Polymarket's Gamma API (gamma-api.polymarket.com)
is public, unauthenticated read access.

For an unresolved match whose two teams are already real (the same
priceable set load_ko_match_win_probabilities's h2h path uses), a
team's price in the "reach {next_stage}" market IS its probability of
winning that specific match — no further derivation needed, because
being seeded into the match already means the team has reached the
match's OWN stage as a certain fact (P=1), not a market estimate. See
win_probability.compute_match_win_probabilities for how this is used.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

import httpx

from app.models._datetime import utc_now
from app.services.team_match import canonicalize

log = logging.getLogger(__name__)

GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"

# Target stage (the stage a team is trying to REACH — i.e. the values of
# win_probability.ADVANCEMENT_MAP) -> Polymarket event slug. Covers every
# knockout target stage that map produces, so any stage win_probability
# asks about has a matching slug here.
STAGE_EVENT_SLUGS: dict[str, str] = {
    "round_of_16": "world-cup-nation-to-reach-round-of-16",
    "quarter_final": "world-cup-nation-to-reach-quarterfinals",
    "semi_final": "world-cup-nation-to-reach-semifinals",
    "final": "world-cup-nation-to-reach-final",
    "winner": "world-cup-winner",
}

TTL = timedelta(minutes=10)

_cache: dict[str, tuple[dict[str, float], datetime]] = {}
_lock = asyncio.Lock()


def parse_event_prices(event: dict) -> dict[str, float]:
    """Pure: one Gamma API event -> {canonicalized team: P(Yes)}.

    Each of the event's per-team binary markets carries `groupItemTitle`
    (the team name) and JSON-encoded `outcomes` / `outcomePrices`
    string fields (Polymarket's Gamma API quirk — prices are strings
    inside a JSON-encoded list, not a native array). A market missing
    any of these, or without a "Yes" outcome, is skipped rather than
    guessed at.
    """
    prices: dict[str, float] = {}
    for market in event.get("markets", []):
        team = market.get("groupItemTitle")
        if not team:
            continue
        try:
            outcomes = json.loads(market["outcomes"])
            outcome_prices = json.loads(market["outcomePrices"])
            yes_price = float(outcome_prices[outcomes.index("Yes")])
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        prices[canonicalize(team)] = yes_price
    return prices


async def _fetch_event(slug: str) -> dict | None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(GAMMA_EVENTS_URL, params={"slug": slug})
        r.raise_for_status()
        events = r.json()
    if not isinstance(events, list) or not events:
        return None
    return events[0]


async def get_stage_reach_probabilities(target_stage: str) -> dict[str, float]:
    """{canonicalized team: P(reaches target_stage)}, from Polymarket's
    cached event for that stage.

    Never raises — any fetch/parse failure serves the last-good cached
    value (or {} on a cold cache), same durability contract as
    odds_cache.get_or_refresh_odds: an outage here must degrade to "no
    Polymarket signal," never a broken simulation. A target_stage with
    no known slug (shouldn't happen — STAGE_EVENT_SLUGS covers every
    value ADVANCEMENT_MAP produces) also returns {}.
    """
    slug = STAGE_EVENT_SLUGS.get(target_stage)
    if slug is None:
        return {}

    async with _lock:
        cached = _cache.get(slug)
        now = utc_now()
        if cached is not None and (now - cached[1]) < TTL:
            return cached[0]

        try:
            event = await _fetch_event(slug)
        except Exception as e:  # noqa: BLE001 — durability, see docstring
            log.warning("Polymarket fetch for %r failed: %s", slug, e)
            return cached[0] if cached is not None else {}

        prices = parse_event_prices(event) if event else {}
        _cache[slug] = (prices, now)
        return prices
