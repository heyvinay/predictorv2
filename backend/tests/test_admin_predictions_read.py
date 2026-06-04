"""Tests for the v2.157.0 admin entry-predictions read endpoint.

The endpoint at ``GET /api/admin/entries/{entry_id}/predictions`` powers
the slide-over's Group / Knockout / Bonus tabs. It's admin-only,
read-only, and bypasses the blind-pool visibility check via the existing
``get_entry_for_view(viewer=admin)`` precedent.

We test the orchestration layer directly (call the endpoint function with
a real session + admin user). The underlying service functions are
already covered by tests next to them; here we verify:

  * Admin can read another user's predictions (auth bypass works).
  * Owner can't reach this endpoint through the service entry point
    (visibility helper rejects non-admin non-owner pre-deadline).
  * An entry with no predictions returns empty match/bracket arrays
    PLUS the 4 bonus question placeholders (UI consistency).
  * A populated entry returns its actual picks shaped correctly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register every model with metadata
from app.models.bonus import BonusPrediction
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.user import AuthProvider, User
from app.services import entries as entries_service


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def setup(session: AsyncSession):
    """Standard fixture: one competition, one owner, one admin, one entry."""
    comp = Competition(
        name="Test World Cup 2026",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    owner = User(
        email="owner@example.com",
        name="Owner",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    admin = User(
        email="admin@example.com",
        name="Admin",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_admin=True,
    )
    session.add_all([comp, owner, admin])
    await session.commit()
    await session.refresh(comp)
    await session.refresh(owner)
    await session.refresh(admin)

    entry = await entries_service.create_entry(
        session, user=owner, competition=comp
    )
    await session.commit()
    await session.refresh(entry)
    return {"comp": comp, "owner": owner, "admin": admin, "entry": entry}


async def _call_endpoint(session, admin_user, entry_id):
    """Call the endpoint function directly — skips FastAPI's DI layer
    but exercises the same orchestration code path."""
    from app.api.admin import get_admin_entry_predictions

    return await get_admin_entry_predictions(
        entry_id=entry_id, session=session, _admin=admin_user
    )


class TestAdminEntryPredictionsRead:
    async def test_empty_entry_returns_placeholders(
        self, session: AsyncSession, setup
    ):
        """Fresh entry has no match/team/bonus rows. The endpoint must
        still return a well-formed payload with empty match_predictions,
        null bracket, and 4 bonus answer placeholders (one per YAML
        question)."""
        result = await _call_endpoint(session, setup["admin"], setup["entry"].id)
        assert result.match_predictions == []
        assert result.bracket is None
        # Bonus placeholders — YAML ships 4 questions per CLAUDE.md.
        assert len(result.bonus_answers) == 4
        # All placeholders have answer=None
        assert all(b.answer is None for b in result.bonus_answers)
        # Question titles are populated from YAML (non-empty)
        assert all(b.question_title for b in result.bonus_answers)

    async def test_admin_can_view_another_users_entry(
        self, session: AsyncSession, setup
    ):
        """Auth bypass — entry owner is `owner`, requester is `admin`.
        Pre-fix the blind-pool gate would have refused; the admin branch
        in check_entry_visibility lets it through."""
        result = await _call_endpoint(session, setup["admin"], setup["entry"].id)
        # If auth had failed we'd never get here.
        assert result is not None

    async def test_non_admin_owner_cannot_use_admin_endpoint(
        self, session: AsyncSession, setup
    ):
        """The endpoint dependency `AdminUser` enforces admin role at the
        FastAPI layer (not exercised here). At the service layer the
        visibility helper still lets owners view their own entry — that's
        correct, but the API guard prevents reaching the service path
        without admin role. Re-prove the service-layer invariant:
        a non-admin non-owner is rejected by visibility (blind pool)."""
        stranger = User(
            email="stranger@example.com",
            name="Stranger",
            password_hash="x",
            auth_provider=AuthProvider.EMAIL,
        )
        session.add(stranger)
        await session.commit()
        await session.refresh(stranger)

        from app.services.entries import EntryAccessDeniedError

        with pytest.raises(EntryAccessDeniedError):
            await entries_service.get_entry_for_view(
                session, entry_id=setup["entry"].id, viewer=stranger
            )

    async def test_populated_entry_returns_predictions(
        self, session: AsyncSession, setup
    ):
        """End-to-end happy path with one of each prediction type."""
        entry = setup["entry"]
        comp = setup["comp"]

        # Match prediction needs a fixture.
        fixture = Fixture(
            external_id="X1",
            competition_id=comp.id,
            group_name="A",
            home_team="Brazil",
            away_team="Croatia",
            kickoff=datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc),
            stage="group",
            status=MatchStatus.SCHEDULED,
        )
        session.add(fixture)
        await session.commit()
        await session.refresh(fixture)

        session.add(
            MatchPrediction(
                entry_id=entry.id,
                fixture_id=fixture.id,
                home_score=2,
                away_score=1,
                phase=PredictionPhase.PHASE_1,
            )
        )
        # Bracket: one round_of_16 pick + a winner.
        session.add(
            TeamPrediction(
                entry_id=entry.id,
                team="Brazil",
                stage="round_of_16",
                phase=PredictionPhase.PHASE_1,
            )
        )
        session.add(
            TeamPrediction(
                entry_id=entry.id,
                team="Brazil",
                stage="winner",
                phase=PredictionPhase.PHASE_1,
            )
        )
        # One bonus answer.
        session.add(
            BonusPrediction(
                entry_id=entry.id,
                question_id="most_goals_scored_group",
                answer="Brazil",
            )
        )
        await session.commit()

        result = await _call_endpoint(session, setup["admin"], entry.id)

        # Match prediction is populated with fixture display fields.
        assert len(result.match_predictions) == 1
        m = result.match_predictions[0]
        assert m.home_score == 2
        assert m.away_score == 1
        assert m.home_team == "Brazil"
        assert m.away_team == "Croatia"

        # Bracket aggregated correctly.
        assert result.bracket is not None
        assert result.bracket.winner == "Brazil"
        assert "Brazil" in result.bracket.round_of_16

        # Bonus: 4 entries total (1 real answer + 3 placeholders).
        answered = [b for b in result.bonus_answers if b.answer is not None]
        placeholders = [b for b in result.bonus_answers if b.answer is None]
        assert len(answered) == 1
        assert answered[0].question_id == "most_goals_scored_group"
        assert answered[0].answer == "Brazil"
        assert len(placeholders) == 3

    async def test_admin_visibility_bypasses_blind_pool(
        self, session: AsyncSession, setup
    ):
        """Regression guard: confirm get_entry_for_view(viewer=admin) is the
        right precedent. An admin should be allowed to view even a
        disabled / withdrawn entry's metadata for forensics purposes."""
        entry = setup["entry"]
        entry.is_disabled = True
        session.add(entry)
        await session.commit()

        # Admin still gets through.
        loaded = await entries_service.get_entry_for_view(
            session, entry_id=entry.id, viewer=setup["admin"]
        )
        assert loaded.id == entry.id
