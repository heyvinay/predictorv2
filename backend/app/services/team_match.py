"""Team-name normaliser + odds extractor (backend mirror of `teamMatch.ts`).

The Odds API and our tournament config (`config/worldcup2026.yml`) don't
always agree on spelling — "USA" vs "United States", "Korea Republic" vs
"South Korea", etc. This module canonicalises both sides to a common form
before comparing, exactly mirroring
`frontend/src/lib/utils/teamMatch.ts`. Keep the two ALIASES maps in sync —
losing an entry here breaks the win-probability odds-weighting path
silently for that team, the same failure mode documented for the frontend
copy in CLAUDE.md's Alias preservation contract.
"""

from __future__ import annotations

import unicodedata

# API variation -> canonical (worldcup2026.yml) name. Mirrors
# frontend/src/lib/utils/teamMatch.ts:ALIASES exactly.
ALIASES: dict[str, str] = {
    "USA": "United States",
    "United States of America": "United States",
    "Korea Republic": "South Korea",
    "Cote d'Ivoire": "Ivory Coast",
    "Czech Republic": "Czechia",
    "Cape Verde Islands": "Cape Verde",
    "Cabo Verde": "Cape Verde",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "DR Congo": "Congo DR",
    "Democratic Republic of the Congo": "Congo DR",
    "Democratic Republic of Congo": "Congo DR",
    "CuraÃ§ao": "Curacao",
    "Türkiye": "Turkey",
    "IR Iran": "Iran",
}


def _normalize(name: str) -> str:
    decomposed = unicodedata.normalize("NFD", name)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(stripped.strip().lower().split())


def canonicalize(name: str) -> str:
    """Resolve a team name to its canonical form. Idempotent."""
    norm = _normalize(name)
    for variant, canonical in ALIASES.items():
        if _normalize(variant) == norm:
            return _normalize(canonical)
    return norm


def find_odds_for_fixture(
    home_team: str, away_team: str, api_matches: list[dict]
) -> dict | None:
    """Find the API match for a fixture by team-pair (order-sensitive:
    home must match home). Returns None if no match."""
    f_home = canonicalize(home_team)
    f_away = canonicalize(away_team)
    for match in api_matches:
        if canonicalize(match.get("home_team", "")) == f_home and canonicalize(
            match.get("away_team", "")
        ) == f_away:
            return match
    return None


def extract_h2h_odds(match: dict) -> dict[str, float] | None:
    """Averaged head-to-head decimal odds across all bookmakers for a
    match. Skips bookmakers missing the h2h market or any of the three
    outcomes. Returns {home, draw, away} or None if no bookmaker had a
    complete h2h market."""
    home_canon = canonicalize(match.get("home_team", ""))
    away_canon = canonicalize(match.get("away_team", ""))

    home_prices: list[float] = []
    draw_prices: list[float] = []
    away_prices: list[float] = []

    for bookmaker in match.get("bookmakers", []):
        h2h = next((m for m in bookmaker.get("markets", []) if m.get("key") == "h2h"), None)
        if h2h is None or len(h2h.get("outcomes", [])) < 3:
            continue

        home_price = draw_price = away_price = None
        for outcome in h2h["outcomes"]:
            name = canonicalize(outcome.get("name", ""))
            price = outcome.get("price")
            if name == "draw":
                draw_price = price
            elif name == home_canon:
                home_price = price
            elif name == away_canon:
                away_price = price

        if home_price is None or draw_price is None or away_price is None:
            continue
        home_prices.append(home_price)
        draw_prices.append(draw_price)
        away_prices.append(away_price)

    if not home_prices:
        return None

    def avg(values: list[float]) -> float:
        return sum(values) / len(values)

    return {"home": avg(home_prices), "draw": avg(draw_prices), "away": avg(away_prices)}


def derive_advance_probability(odds: dict[str, float]) -> float:
    """Convert averaged decimal h2h odds into P(home team advances).

    Knockout matches can't end in a draw — a 90-minute draw goes to ET
    and penalties — so there is no "draw" outcome in bracket terms. This
    devigs the bookmaker's implied probabilities (dividing out the
    overround) then redistributes the draw share proportionally to each
    side's relative strength, a standard treatment for pricing a
    moneyline-style advance probability off a 3-way match-result market.
    """
    implied_home = 1 / odds["home"]
    implied_draw = 1 / odds["draw"]
    implied_away = 1 / odds["away"]
    overround = implied_home + implied_draw + implied_away

    p_home = implied_home / overround
    p_draw = implied_draw / overround
    p_away = implied_away / overround

    if p_home + p_away == 0:
        return 0.5
    return p_home + p_draw * (p_home / (p_home + p_away))
