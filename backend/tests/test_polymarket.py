"""Tests for the Polymarket team-to-reach-stage probability source."""

import pytest

import app.services.polymarket as polymarket_service
from app.services.polymarket import get_stage_reach_probabilities, parse_event_prices


def _market(team: str, yes_price: float) -> dict:
    return {
        "groupItemTitle": team,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": f'["{yes_price}", "{1 - yes_price}"]',
    }


class TestParseEventPrices:
    def test_extracts_yes_price_per_team(self):
        event = {"markets": [_market("Argentina", 0.86), _market("Colombia", 0.605)]}
        prices = parse_event_prices(event)
        assert prices["argentina"] == 0.86
        assert prices["colombia"] == 0.605

    def test_canonicalizes_team_names(self):
        event = {"markets": [_market("USA", 0.5)]}
        prices = parse_event_prices(event)
        assert "united states" in prices

    def test_skips_market_missing_group_item_title(self):
        market = _market("Argentina", 0.86)
        del market["groupItemTitle"]
        event = {"markets": [market]}
        assert parse_event_prices(event) == {}

    def test_skips_market_with_malformed_outcomes_json(self):
        event = {"markets": [{"groupItemTitle": "Argentina", "outcomes": "not json", "outcomePrices": "[]"}]}
        assert parse_event_prices(event) == {}

    def test_skips_market_missing_yes_outcome(self):
        market = {
            "groupItemTitle": "Argentina",
            "outcomes": '["No"]',
            "outcomePrices": '["1.0"]',
        }
        assert parse_event_prices({"markets": [market]}) == {}

    def test_empty_markets_list_returns_empty(self):
        assert parse_event_prices({"markets": []}) == {}


@pytest.fixture(autouse=True)
def _clean_polymarket_cache():
    polymarket_service._cache.clear()
    yield
    polymarket_service._cache.clear()


class TestGetStageReachProbabilities:
    async def test_unknown_target_stage_returns_empty_without_fetching(self, monkeypatch):
        async def _boom(slug):
            raise AssertionError("should never fetch for an unmapped stage")

        monkeypatch.setattr(polymarket_service, "_fetch_event", _boom)
        assert await get_stage_reach_probabilities("group") == {}

    async def test_fetches_and_caches_a_known_stage(self, monkeypatch):
        calls = []

        async def fake_fetch(slug):
            calls.append(slug)
            return {"markets": [_market("Argentina", 0.86)]}

        monkeypatch.setattr(polymarket_service, "_fetch_event", fake_fetch)

        first = await get_stage_reach_probabilities("quarter_final")
        second = await get_stage_reach_probabilities("quarter_final")

        assert first == {"argentina": 0.86}
        assert second == {"argentina": 0.86}
        assert calls == ["world-cup-nation-to-reach-quarterfinals"], "second call must hit cache, not refetch"

    async def test_fetch_failure_falls_back_to_last_good_cache(self, monkeypatch):
        async def fake_fetch_ok(slug):
            return {"markets": [_market("Argentina", 0.86)]}

        monkeypatch.setattr(polymarket_service, "_fetch_event", fake_fetch_ok)
        await get_stage_reach_probabilities("quarter_final")

        polymarket_service._cache["world-cup-nation-to-reach-quarterfinals"] = (
            {"argentina": 0.86},
            polymarket_service.utc_now() - polymarket_service.TTL * 2,
        )

        async def fake_fetch_fails(slug):
            raise httpx_error()

        def httpx_error():
            import httpx

            return httpx.ConnectError("boom")

        monkeypatch.setattr(polymarket_service, "_fetch_event", fake_fetch_fails)

        result = await get_stage_reach_probabilities("quarter_final")
        assert result == {"argentina": 0.86}, "an outage must serve the last-good cache, never raise"

    async def test_cold_cache_and_fetch_failure_returns_empty(self, monkeypatch):
        async def fake_fetch_fails(slug):
            raise RuntimeError("boom")

        monkeypatch.setattr(polymarket_service, "_fetch_event", fake_fetch_fails)
        assert await get_stage_reach_probabilities("quarter_final") == {}
