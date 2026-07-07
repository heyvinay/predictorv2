"""Tests for the Python port of teamMatch.ts (odds-API team-name matching)."""

from app.services.team_match import (
    canonicalize,
    derive_advance_probability,
    extract_h2h_odds,
    find_odds_for_fixture,
)


class TestCanonicalize:
    def test_alias_resolves_to_canonical_form(self):
        assert canonicalize("USA") == canonicalize("United States")

    def test_case_and_whitespace_insensitive(self):
        assert canonicalize("  united STATES  ") == canonicalize("United States")

    def test_accent_stripping(self):
        assert canonicalize("Türkiye") == canonicalize("Turkey")

    def test_mojibake_curacao_alias(self):
        assert canonicalize("CuraÃ§ao") == canonicalize("Curacao")

    def test_idempotent_on_already_canonical_name(self):
        assert canonicalize(canonicalize("South Korea")) == canonicalize("South Korea")

    def test_unmapped_name_passes_through_normalized(self):
        assert canonicalize("Brazil") == "brazil"


class TestFindOddsForFixture:
    def test_matches_by_home_away_pair(self):
        api_matches = [
            {"home_team": "France", "away_team": "Sweden", "bookmakers": []},
            {"home_team": "Germany", "away_team": "Paraguay", "bookmakers": []},
        ]
        found = find_odds_for_fixture("France", "Sweden", api_matches)
        assert found is not None
        assert found["home_team"] == "France"

    def test_resolves_aliases_on_both_sides(self):
        api_matches = [{"home_team": "USA", "away_team": "Korea Republic", "bookmakers": []}]
        found = find_odds_for_fixture("United States", "South Korea", api_matches)
        assert found is not None

    def test_returns_none_when_no_match(self):
        api_matches = [{"home_team": "France", "away_team": "Sweden", "bookmakers": []}]
        assert find_odds_for_fixture("Brazil", "Argentina", api_matches) is None

    def test_order_sensitive(self):
        api_matches = [{"home_team": "Sweden", "away_team": "France", "bookmakers": []}]
        assert find_odds_for_fixture("France", "Sweden", api_matches) is None


class TestExtractH2HOdds:
    def _match(self, bookmakers):
        return {"home_team": "France", "away_team": "Sweden", "bookmakers": bookmakers}

    def test_averages_across_bookmakers(self):
        match = self._match(
            [
                {
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "France", "price": 1.5},
                                {"name": "Draw", "price": 4.0},
                                {"name": "Sweden", "price": 6.0},
                            ],
                        }
                    ]
                },
                {
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "France", "price": 1.7},
                                {"name": "Draw", "price": 3.8},
                                {"name": "Sweden", "price": 5.5},
                            ],
                        }
                    ]
                },
            ]
        )
        odds = extract_h2h_odds(match)
        assert odds == {"home": 1.6, "draw": 3.9, "away": 5.75}

    def test_skips_bookmaker_missing_h2h_market(self):
        match = self._match(
            [
                {"markets": [{"key": "totals", "outcomes": []}]},
                {
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "France", "price": 1.5},
                                {"name": "Draw", "price": 4.0},
                                {"name": "Sweden", "price": 6.0},
                            ],
                        }
                    ]
                },
            ]
        )
        odds = extract_h2h_odds(match)
        assert odds == {"home": 1.5, "draw": 4.0, "away": 6.0}

    def test_no_bookmakers_returns_none(self):
        assert extract_h2h_odds(self._match([])) is None

    def test_incomplete_outcome_set_skipped(self):
        match = self._match(
            [
                {
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "France", "price": 1.5},
                                {"name": "Sweden", "price": 6.0},
                            ],
                        }
                    ]
                }
            ]
        )
        assert extract_h2h_odds(match) is None


class TestDeriveAdvanceProbability:
    def test_heavy_favourite_gets_high_advance_probability(self):
        # Favourite at 1.2, longshot at 12.0 — favourite should clear 0.85.
        p = derive_advance_probability({"home": 1.2, "draw": 6.0, "away": 12.0})
        assert p > 0.85

    def test_symmetric_odds_split_evenly(self):
        p = derive_advance_probability({"home": 2.0, "draw": 3.5, "away": 2.0})
        assert round(p, 6) == 0.5

    def test_probability_is_bounded(self):
        p = derive_advance_probability({"home": 1.01, "draw": 50.0, "away": 50.0})
        assert 0.0 <= p <= 1.0
