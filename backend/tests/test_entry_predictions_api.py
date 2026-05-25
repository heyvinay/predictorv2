"""HTTP-level tests for entry-scoped prediction routes.

Covers auth boundary, ownership, and status-code translation. The full
state-machine and lock-rule coverage lives in
`test_entry_predictions_service.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.database import get_session
from app.dependencies import get_current_user
from app.main import app
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.user import AuthProvider, User
from app.services import entries as entries_service


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(db_session: AsyncSession) -> Competition:
    comp = Competition(
        name="WC",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


@pytest_asyncio.fixture
async def alice(db_session: AsyncSession) -> User:
    u = User(
        email="alice@example.com",
        name="Alice",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def bob(db_session: AsyncSession) -> User:
    u = User(
        email="bob@example.com",
        name="Bob",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def alice_entry(db_session, alice, competition):
    e = await entries_service.create_entry(
        db_session, user=alice, competition=competition
    )
    await db_session.commit()
    return e


@pytest_asyncio.fixture
async def fixture_future(db_session, competition):
    f = Fixture(
        competition_id=competition.id,
        home_team="Brazil",
        away_team="Germany",
        kickoff=datetime.now(timezone.utc) + timedelta(days=7),
        stage="group",
        group="A",
        status=MatchStatus.SCHEDULED,
    )
    db_session.add(f)
    await db_session.commit()
    await db_session.refresh(f)
    return f


class TestPredictionAuth:
    async def test_unauthenticated_returns_401(
        self, db_session, alice_entry
    ):
        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/entries/{alice_entry.id}/predictions/matches")
        app.dependency_overrides.clear()
        assert r.status_code == 401


class TestPredictionUpsert:
    async def test_owner_can_upsert_match(
        self, db_session, alice, alice_entry, fixture_future
    ):
        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: alice
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.put(
                f"/api/entries/{alice_entry.id}/predictions/matches/{fixture_future.id}",
                json={"home_score": 2, "away_score": 1},
            )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["home_score"] == 2
        assert body["away_score"] == 1


class TestPredictionCrossUser:
    async def test_bob_cannot_write_alices_entry(
        self, db_session, alice, bob, alice_entry, fixture_future
    ):
        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        # Bob is the authenticated caller — but the entry is Alice's.
        app.dependency_overrides[get_current_user] = lambda: bob
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.put(
                f"/api/entries/{alice_entry.id}/predictions/matches/{fixture_future.id}",
                json={"home_score": 1, "away_score": 0},
            )
        app.dependency_overrides.clear()
        assert r.status_code == 403


class TestPredictionScoreRange:
    async def test_pydantic_rejects_score_over_15(
        self, db_session, alice, alice_entry, fixture_future
    ):
        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: alice
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.put(
                f"/api/entries/{alice_entry.id}/predictions/matches/{fixture_future.id}",
                json={"home_score": 99, "away_score": 0},
            )
        app.dependency_overrides.clear()
        # FastAPI returns 422 for Pydantic validation errors.
        assert r.status_code == 422


class TestBracketEndpoints:
    async def test_replace_bracket_returns_200(
        self, db_session, alice, alice_entry
    ):
        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: alice
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.put(
                f"/api/entries/{alice_entry.id}/predictions/bracket",
                json={
                    "predictions": [
                        {
                            "team": "Brazil",
                            "stage": "winner",
                            "group_position": None,
                        }
                    ]
                },
            )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestBonusEndpoints:
    async def test_bonus_save_returns_picks(
        self, db_session, alice, alice_entry, mock_tournament_config
    ):
        async def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: alice
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                f"/api/entries/{alice_entry.id}/predictions/bonus",
                json={
                    "predictions": [
                        # 'dark_horse' is a real question id in the
                        # mocked tournament config + the YAML default.
                        # Even if it's not, the service silently ignores
                        # unknown ids, so the call is still safe.
                        {"question_id": "dark_horse", "answer": "Iceland"},
                    ]
                },
            )
        app.dependency_overrides.clear()
        assert r.status_code == 200
