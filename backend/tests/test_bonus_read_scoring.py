"""Read-side bonus scoring fields (v2.164.0).

GET /api/entries/{id}/predictions/bonus now ships `category`, `points`,
and `hit` per row so the V4 leaderboard drawer can render settled bonus
answers without re-deriving correctness client-side. `hit` is None until
the question has at least one recorded correct answer.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
from app.models._datetime import utc_now
from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.competition import Competition
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
async def alice_entry(db_session, alice, competition):
    e = await entries_service.create_entry(
        db_session, user=alice, competition=competition
    )
    await db_session.commit()
    return e


async def _get_bonus(db_session, viewer, entry_id):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: viewer
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/entries/{entry_id}/predictions/bonus")
    app.dependency_overrides.clear()
    return r


class TestBonusReadScoring:
    async def test_unsettled_question_hit_is_none(
        self, db_session, alice, alice_entry
    ):
        db_session.add(
            BonusPrediction(
                entry_id=alice_entry.id,
                question_id="most_goals_scored_group",
                answer="France",
            )
        )
        await db_session.commit()

        r = await _get_bonus(db_session, alice, alice_entry.id)
        assert r.status_code == 200
        (row,) = r.json()
        assert row["question_id"] == "most_goals_scored_group"
        assert row["category"] == "group_stage"
        # Unresolved (no correct answer recorded yet) — points is what
        # THIS entry earned, which can't be known until settlement, so
        # it stays None rather than leaking the question's max value.
        assert row["points"] is None
        assert row["hit"] is None

    async def test_settled_hit_and_miss(self, db_session, alice, alice_entry):
        db_session.add_all(
            [
                BonusPrediction(
                    entry_id=alice_entry.id,
                    question_id="most_goals_scored_group",
                    answer="france",  # case-insensitive match expected
                ),
                BonusPrediction(
                    entry_id=alice_entry.id,
                    question_id="dark_horse",
                    answer="Morocco",
                ),
                # Two tied correct answers for the group-goals question.
                BonusAnswer(
                    competition_id=alice_entry.competition_id,
                    question_id="most_goals_scored_group",
                    correct_answer="France",
                    resolved_at=utc_now(),
                ),
                BonusAnswer(
                    competition_id=alice_entry.competition_id,
                    question_id="most_goals_scored_group",
                    correct_answer="Brazil",
                    resolved_at=utc_now(),
                ),
                BonusAnswer(
                    competition_id=alice_entry.competition_id,
                    question_id="dark_horse",
                    correct_answer="Japan",
                    resolved_at=utc_now(),
                ),
            ]
        )
        await db_session.commit()

        r = await _get_bonus(db_session, alice, alice_entry.id)
        assert r.status_code == 200
        by_qid = {row["question_id"]: row for row in r.json()}

        goals = by_qid["most_goals_scored_group"]
        assert goals["hit"] is True
        assert goals["points"] == 15

        horse = by_qid["dark_horse"]
        assert horse["hit"] is False
        assert horse["category"] == "top_flop"
        # ★ Regression pin: a miss earns 0, never the question's max
        # value (20) — this endpoint used to return question.points
        # unconditionally regardless of hit/miss, which made every
        # entry's bonus points look identical and broke /compare's
        # bonus delta silently (buildBonusRows read this field
        # directly; only leaderboardV4.ts's foldBonus() happened to
        # dodge it by gating on `hit` itself).
        assert horse["points"] == 0
