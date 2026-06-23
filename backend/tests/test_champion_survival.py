"""Tests for the /api/leaderboard/champion-survival endpoint.

These are service-level tests — they call the endpoint function directly
against an in-memory aiosqlite DB, matching the pattern used in
test_leaderboard_v4.py (no HTTP client needed).

Project-truth model names (adapted from plan):
- TeamPrediction.team  (NOT .team_code — the plan's stale field name)
- PredictionEntry.display_name, .is_disabled, .withdrawn_at
- PredictionEntryPhase.status = EntryStatus.SUBMITTED
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import app.models  # noqa: F401 — registers all models
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score
from app.models.user import AuthProvider, User
from app.api.leaderboard import champion_survival, ChampionSurvivalResponse

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared DB fixture (aiosqlite in-memory — same pattern as test_leaderboard_v4)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_eligible_entry(
    session: AsyncSession,
    competition: Competition,
    *,
    email: str,
) -> PredictionEntry:
    """Seed a User + SUBMITTED PredictionEntry."""
    user = User(
        email=email,
        name=email.split("@")[0].title(),
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(user)
    await session.flush()

    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6]}",
        display_name=f"{user.name}'s Entry",
        entry_number=1,
    )
    session.add(entry)
    await session.flush()

    session.add(
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.SUBMITTED,
        )
    )
    await session.flush()
    return entry


async def _seed_winners(
    session: AsyncSession,
    picks: dict[str, int],
    *,
    deadline_passed: bool = True,
) -> Competition:
    """Seed N entries each picking the given team as winner.

    picks = {team_name: count}
    """
    deadline = (
        datetime.now(tz=timezone.utc) - timedelta(hours=1)
        if deadline_passed
        else datetime.now(tz=timezone.utc) + timedelta(days=1)
    )
    comp = Competition(
        name="WC26",
        external_id="WC2026",
        is_active=True,
        phase1_deadline=deadline,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.flush()

    for team_name, count in picks.items():
        for i in range(count):
            entry = await _make_eligible_entry(
                session,
                comp,
                email=f"{team_name.lower()}-{i}@test.com",
            )
            session.add(
                TeamPrediction(
                    entry_id=entry.id,
                    phase=PredictionPhase.PHASE_1,
                    stage="winner",
                    team=team_name,
                )
            )
    await session.commit()
    return comp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_returns_empty_pre_deadline(session: AsyncSession):
    """Pre-deadline blind-pool gate returns alive_count=0, total_count=0, teams=[]."""
    await _seed_winners(session, {"Brazil": 3, "France": 2}, deadline_passed=False)
    result = await champion_survival(session=session, user=_dummy_user())
    assert isinstance(result, ChampionSurvivalResponse)
    assert result.alive_count == 0
    assert result.total_count == 0
    assert result.teams == []


async def test_counts_alive_and_eliminated(session: AsyncSession):
    """3 entries pick Brazil (alive), 2 pick England (eliminated via KO loss)."""
    comp = await _seed_winners(session, {"Brazil": 3, "England": 2})

    # Mark England as eliminated: FINISHED KO fixture with a linked Score row.
    # get_eliminated_teams() requires `score` to be non-None (it outer-joins Score)
    # and checks score.outcome — so we need both a Fixture and a Score row.
    fixture = Fixture(
        competition_id=comp.id,
        home_team="England",
        away_team="Germany",
        kickoff=datetime.now(tz=timezone.utc) - timedelta(days=1),
        stage="round_of_16",
        status=MatchStatus.FINISHED,
    )
    session.add(fixture)
    await session.flush()
    # Score: England(home) 1-2 Germany(away) → outcome "2" → home team (England) eliminated
    session.add(Score(fixture_id=fixture.id, home_score=1, away_score=2))
    await session.commit()

    result = await champion_survival(session=session, user=_dummy_user())
    assert result.total_count == 5
    assert result.alive_count == 3  # only Brazil-backers alive

    teams_by_name = {t.team_code: t for t in result.teams}
    assert teams_by_name["Brazil"].count == 3
    assert teams_by_name["Brazil"].alive is True
    assert teams_by_name["England"].count == 2
    assert teams_by_name["England"].alive is False


async def test_only_phase1_picks_counted(session: AsyncSession):
    """Phase-2 TeamPrediction rows are ignored (CLAUDE.md phase invariant)."""
    comp = await _seed_winners(session, {"Brazil": 1})

    # Grab the seeded entry and add a Phase-2 pick for Argentina — must be ignored
    entries = (await session.execute(select(PredictionEntry))).scalars().all()
    assert len(entries) == 1
    session.add(
        TeamPrediction(
            entry_id=entries[0].id,
            phase=PredictionPhase.PHASE_2,
            stage="winner",
            team="Argentina",
        )
    )
    await session.commit()

    result = await champion_survival(session=session, user=_dummy_user())
    team_codes = {t.team_code for t in result.teams}
    assert "Argentina" not in team_codes  # phase-2 row ignored
    assert "Brazil" in team_codes
    brazil = next(t for t in result.teams if t.team_code == "Brazil")
    assert brazil.count == 1


async def test_generated_at_is_aware_utc(session: AsyncSession):
    """generated_at must be timezone-aware (explicit UTC offset per CLAUDE.md)."""
    await _seed_winners(session, {"Brazil": 1})
    result = await champion_survival(session=session, user=_dummy_user())
    assert result.generated_at.tzinfo is not None
    # Serialised form must carry an explicit offset
    serialised = result.generated_at.isoformat()
    assert "T" in serialised
    assert serialised.endswith("+00:00") or serialised.endswith("Z") or "+" in serialised[10:]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dummy_user() -> User:
    """Return a minimal User instance for the endpoint's `user` parameter."""
    return User(
        id=uuid.uuid4(),
        email="dummy@test.com",
        name="Dummy",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
