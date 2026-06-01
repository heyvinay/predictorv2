"""HTTP-level tests for the public bonus endpoints.

`/api/predictions/bonus/questions` and `/api/predictions/bonus/meta` are
both auth-optional (the /rules page lists questions to prospective
joiners before they sign up). These tests pin the wire shape so frontend
type unions stay valid.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
class TestBonusQuestionsEndpoint:
    async def test_returns_four_questions(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/predictions/bonus/questions")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 4

    async def test_includes_filtered_input_types(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/predictions/bonus/questions")
        body = response.json()
        by_id = {q["id"]: q for q in body}
        assert by_id["dark_horse"]["input_type"] == "team_outside_top_n"
        assert by_id["flop"]["input_type"] == "team_in_top_n"

    async def test_endpoint_is_public(self):
        """No Authorization header — should still 200."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/predictions/bonus/questions")
        assert response.status_code == 200

    async def test_points_per_category(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/predictions/bonus/questions")
        body = response.json()
        for q in body:
            if q["category"] == "group_stage":
                assert q["points"] == 15, q
            elif q["category"] == "top_flop":
                assert q["points"] == 20, q


@pytest.mark.asyncio
class TestBonusMetaEndpoint:
    async def test_returns_top_n_and_team_list(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/predictions/bonus/meta")
        assert response.status_code == 200
        body = response.json()
        assert body["top_n"] == 10
        assert isinstance(body["fifa_top_teams"], list)
        assert len(body["fifa_top_teams"]) == 10

    async def test_morocco_present_italy_absent(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/predictions/bonus/meta")
        teams = response.json()["fifa_top_teams"]
        assert "Morocco" in teams
        assert "Italy" not in teams

    async def test_team_order_is_fifa_rank(self):
        """France #1 etc. — the frontend may display the list as a
        seeding hint; order is contractual."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/predictions/bonus/meta")
        teams = response.json()["fifa_top_teams"]
        assert teams[:5] == ["France", "Spain", "Argentina", "England", "Portugal"]

    async def test_endpoint_is_public(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/predictions/bonus/meta")
        assert response.status_code == 200
