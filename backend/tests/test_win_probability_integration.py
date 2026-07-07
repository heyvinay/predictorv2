"""DB-integration tests for the win-probability engine.

Builds a small, real, hand-verified slice of the FIFA 2026 bracket (two
R32 matches feeding one R16 match, per bracket_seeding.ROUND_OF_16_SOURCES)
against an in-memory SQLite DB, and checks the loader functions against
the live scoring primitives they must stay in lockstep with.
"""

from datetime import datetime, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score
from app.models.user import User
from app.services.scoring import calculate_entry_points, get_actual_advancement
from app.services.win_probability import (
    build_advancement,
    compute_win_probability,
    load_bracket_state,
    load_pool_predictions,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _seed_competition(session: AsyncSession) -> Competition:
    competition = Competition(name="Test WC 2026", is_active=True, knockout_scoring_enabled=True)
    session.add(competition)
    await session.commit()
    await session.refresh(competition)
    return competition


async def _seed_entry(
    session: AsyncSession, competition: Competition, email: str, display_name: str
) -> PredictionEntry:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    entry = PredictionEntry(
        user_id=user.id,
        competition_id=competition.id,
        reference=f"WC26-{display_name}",
        display_name=display_name,
        entry_number=1,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    session.add(
        PredictionEntryPhase(
            entry_id=entry.id, phase=PredictionPhase.PHASE_1, status=EntryStatus.SUBMITTED
        )
    )
    await session.commit()
    return entry


async def _seed_bracket_slice(session: AsyncSession, competition: Competition) -> None:
    """Two real R32 matches (M74 Germany-Paraguay, M77 France-Sweden) that
    feed the real R16 match M89, per ROUND_OF_16_SOURCES[89]. M74 is
    FINISHED (Germany won); M77 and M89 are still SCHEDULED — a
    genuinely unresolved 2-match slice (m=2, matching the pure-engine
    single-unresolved-match test's shape, one level deeper).
    """
    kickoff = datetime(2026, 6, 29, 20, 30, tzinfo=timezone.utc)

    m74 = Fixture(
        competition_id=competition.id,
        home_team="Germany",
        away_team="Paraguay",
        kickoff=kickoff,
        stage="round_of_32",
        status=MatchStatus.FINISHED,
        external_id="537415",
    )
    m77 = Fixture(
        competition_id=competition.id,
        home_team="France",
        away_team="Sweden",
        kickoff=kickoff,
        stage="round_of_32",
        status=MatchStatus.SCHEDULED,
        external_id="537416",
    )
    m89 = Fixture(
        competition_id=competition.id,
        home_team="slot:round_of_16:537375:home",
        away_team="slot:round_of_16:537375:away",
        kickoff=kickoff,
        stage="round_of_16",
        status=MatchStatus.SCHEDULED,
        external_id="537375",
    )
    session.add_all([m74, m77, m89])
    await session.commit()
    for fixture in (m74, m77, m89):
        await session.refresh(fixture)

    session.add(Score(fixture_id=m74.id, home_score=2, away_score=0))
    await session.commit()


async def test_load_bracket_state_matches_real_bracket_seeding_shape(db_session):
    competition = await _seed_competition(db_session)
    await _seed_bracket_slice(db_session, competition)

    matches, known_winners, unresolved = await load_bracket_state(db_session)

    assert matches[74].stage == "round_of_32"
    assert (matches[74].home_ref, matches[74].away_ref) == ("Germany", "Paraguay")
    assert matches[89].stage == "round_of_16"
    # R16's refs point at upstream match_numbers, per ROUND_OF_16_SOURCES[89].
    assert (matches[89].home_ref, matches[89].away_ref) == (74, 77)

    assert known_winners == {74: "Germany"}
    assert sorted(unresolved) == [77, 89]


async def test_load_pool_predictions_banked_base_matches_real_scoring_engine(db_session):
    """The banked-base invariant: base_points[entry] + this scenario's KO
    delta must equal exactly what calculate_entry_points() computes today,
    for the currently-known portion of the bracket. If this drifts, every
    downstream probability is silently wrong."""
    competition = await _seed_competition(db_session)
    await _seed_bracket_slice(db_session, competition)
    entry = await _seed_entry(db_session, competition, "a@test.com", "Entry A")

    # Predicts the already-decided M74 winner (Germany reaches R16) and an
    # as-yet-undecided pick (France to win it all).
    db_session.add_all(
        [
            TeamPrediction(entry_id=entry.id, team="Germany", stage="round_of_16"),
            TeamPrediction(entry_id=entry.id, team="France", stage="winner"),
        ]
    )
    await db_session.commit()

    actual_advancement = await get_actual_advancement(db_session)
    entries, base_points = await load_pool_predictions(db_session, actual_advancement)

    matches, known_winners, _unresolved = await load_bracket_state(db_session)
    known_only_matches = {mn: matches[mn] for mn in known_winners}
    banked_advancement = build_advancement(known_only_matches, known_winners)

    from app.services.win_probability import entry_ko_points
    from app.services.scoring import get_scoring_config

    points_by_stage = get_scoring_config()["advancement"]
    entry_key = str(entry.id)
    reconstructed_total = base_points[entry_key] + entry_ko_points(
        entries[entry_key], banked_advancement, points_by_stage
    )

    real_breakdown = await calculate_entry_points(
        db_session,
        entry.id,
        actual_advancement=actual_advancement,
        knockout_scoring_enabled=True,
    )

    assert reconstructed_total == real_breakdown.total


async def test_compute_win_probability_end_to_end_sums_to_one(db_session):
    competition = await _seed_competition(db_session)
    await _seed_bracket_slice(db_session, competition)
    entry_a = await _seed_entry(db_session, competition, "a@test.com", "Entry A")
    entry_b = await _seed_entry(db_session, competition, "b@test.com", "Entry B")

    db_session.add_all(
        [
            TeamPrediction(entry_id=entry_a.id, team="France", stage="winner"),
            TeamPrediction(entry_id=entry_b.id, team="Sweden", stage="winner"),
        ]
    )
    await db_session.commit()

    result = await compute_win_probability(db_session)

    assert set(result.entries) == {str(entry_a.id), str(entry_b.id)}
    total_p_win = sum(e.p_win for e in result.entries.values())
    assert round(total_p_win, 6) <= 1.0
    assert round(total_p_win, 6) > 0.0
