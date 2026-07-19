"""Pool retrospective aggregates (Plan A §8)."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register all tables
from app.services.pool_retrospective import (
    outcome_of,
    rank_misses_and_bankers,
)


def test_outcome_of():
    assert outcome_of(2, 1) == "1"
    assert outcome_of(0, 0) == "X"
    assert outcome_of(0, 3) == "2"


def test_rank_misses_and_bankers():
    # (fixture_label, correct_pct, exact_count)
    stats = [
        ("M23 · Morocco 2–0 Belgium", 0.04, 0),
        ("M11 · England 2–0 Iran", 0.91, 24),
        ("M57 · Australia 1–0 Denmark", 0.07, 0),
        ("M44 · France 2–0 New Zealand", 0.87, 19),
        ("M31 · Argentina 3–0 Curacao", 0.89, 31),
        ("M78 · Japan 2–1 Germany", 0.11, 2),
    ]
    misses, bankers = rank_misses_and_bankers(stats, top_n=3)
    assert [m[0] for m in misses] == [
        "M23 · Morocco 2–0 Belgium",
        "M57 · Australia 1–0 Denmark",
        "M78 · Japan 2–1 Germany",
    ]
    assert bankers[0][0] == "M11 · England 2–0 Iran"
    assert len(bankers) == 3


def test_superlatives_always_three_with_fallbacks():
    from app.services.pool_retrospective import _pick_superlatives

    weak = _pick_superlatives({"exact_hits": [], "exact_count": 2,
                               "exact_percentile": 80, "champion_hit": False,
                               "champion_pick": "Brazil",
                               "low_consensus_points": 0})
    assert len(weak) == 3

    strong = _pick_superlatives({
        "exact_hits": [("Japan 1–1 Poland", 1, 14.1)],
        "exact_count": 14, "exact_percentile": 8,
        "champion_hit": True, "champion_pick": "Argentina",
        "low_consensus_points": 22, "ko_hit_percentile": 12,
    })
    assert strong[0]["title"] == "Only you called it"
    assert len(strong) == 3


# ---------------------------------------------------------------------------
# Seeded-DB smoke test for compute_pool_retrospective (Step 5 of the plan).
# Deliberately minimal: one finished group fixture, three eligible entries,
# no TeamPrediction / BonusAnswer rows at all — enough to pin
# group_called_right / group_total / exact_total against a real DB without
# needing to seed the full bracket + bonus-question machinery. `for_user_id`
# is omitted (personal=None) so this doesn't also require exercising
# calculate_leaderboard's cache/rebuild path — that's covered by
# leaderboard's own test suite.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_eligible_entry(session, *, competition_id, user_email, ref):
    from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
    from app.models.prediction import PredictionPhase
    from app.models.user import AuthProvider, User

    user = User(
        email=user_email,
        name=user_email.split("@")[0],
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    entry = PredictionEntry(
        competition_id=competition_id,
        user_id=user.id,
        reference=ref,
        display_name=ref,
        entry_number=1,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    phase = PredictionEntryPhase(
        entry_id=entry.id,
        phase=PredictionPhase.PHASE_1,
        status=EntryStatus.SUBMITTED,
    )
    session.add(phase)
    await session.commit()

    return entry


@pytest.mark.asyncio
async def test_compute_pool_retrospective_group_called_right(db_session: AsyncSession):
    from app.models.competition import Competition
    from app.models.fixture import Fixture, MatchStatus
    from app.models.prediction import MatchPrediction
    from app.models.score import Score
    from app.services.pool_retrospective import compute_pool_retrospective

    comp = Competition(name="WC26", is_active=True)
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)

    entry_a = await _make_eligible_entry(
        db_session, competition_id=comp.id, user_email="a@example.com", ref="WC26-A"
    )
    entry_b = await _make_eligible_entry(
        db_session, competition_id=comp.id, user_email="b@example.com", ref="WC26-B"
    )
    entry_c = await _make_eligible_entry(
        db_session, competition_id=comp.id, user_email="c@example.com", ref="WC26-C"
    )

    fixture = Fixture(
        competition_id=comp.id,
        home_team="France",
        away_team="Poland",
        kickoff=datetime.now(timezone.utc),
        stage="group",
        group="A",
        status=MatchStatus.FINISHED,
    )
    db_session.add(fixture)
    await db_session.commit()
    await db_session.refresh(fixture)

    score = Score(fixture_id=fixture.id, home_score=2, away_score=1)
    db_session.add(score)
    await db_session.commit()

    # a, b: exact + correct outcome ("1"). c: wrong outcome ("2").
    # Majority outcome across the pool is "1" == actual → called right.
    db_session.add(MatchPrediction(entry_id=entry_a.id, fixture_id=fixture.id, home_score=2, away_score=1))
    db_session.add(MatchPrediction(entry_id=entry_b.id, fixture_id=fixture.id, home_score=2, away_score=1))
    db_session.add(MatchPrediction(entry_id=entry_c.id, fixture_id=fixture.id, home_score=0, away_score=2))
    await db_session.commit()

    data = await compute_pool_retrospective(db_session, for_user_id=None)

    assert data["group_total"] == 1
    assert data["group_called_right"] == 1
    assert data["exact_total"] == 2
    assert data["personal"] is None
    # No TeamPrediction rows seeded → no actual final winner resolvable yet.
    assert data["final_winner_team"] is None
    assert data["ko_ladder"] == [
        {"stage": s, "consensus_had": 0, "of": 0, "fallen_teams": []}
        for s in ["round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "winner"]
    ]
