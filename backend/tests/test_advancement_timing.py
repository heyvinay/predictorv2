"""Lineup-based advancement timing (v2.161.0).

`get_actual_advancement` credits a team with "reached stage X" the moment
it is seeded into a stage-X fixture — regardless of whether that match has
been played. The winner of a FINISHED match is additionally credited with
the next stage, which is the only way the `winner` (champion) credit can
fire: the final must be FINISHED and scored.

Uses in-memory SQLite per the project convention.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score, ScoreSource
from app.services.scoring import (
    calculate_advancement_points,
    get_actual_advancement,
)


KICKOFF = datetime(2026, 6, 28, 19, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fixed_scoring_config():
    """Canonical advancement ladder for deterministic point asserts."""
    config = {
        "mode": "fixed",
        "match": {"correct_outcome": 5, "exact_score": 10, "hybrid_cap": 10},
        "advancement": {
            "group_advance": 10,
            "group_position": 5,
            "round_of_32": 20,
            "round_of_16": 30,
            "quarter_final": 40,
            "semi_final": 50,
            "final": 75,
            "winner": 100,
        },
        "phase_multipliers": {"phase_1": 1.0, "phase_2": 0.7},
    }
    with patch("app.services.scoring.get_scoring_config", return_value=config):
        yield


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(
        name="Test WC 2026",
        external_id="WC",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _add_ko(
    session: AsyncSession,
    competition: Competition,
    *,
    stage: str,
    home: str | None,
    away: str | None,
    home_score: int | None = None,
    away_score: int | None = None,
    status: MatchStatus = MatchStatus.SCHEDULED,
) -> Fixture:
    """One knockout fixture; Score row only when a score is supplied."""
    fx = Fixture(
        competition_id=competition.id,
        home_team=home,
        away_team=away,
        kickoff=KICKOFF,
        stage=stage,
        group=None,
        status=status,
    )
    session.add(fx)
    await session.commit()
    await session.refresh(fx)
    if home_score is not None and away_score is not None:
        session.add(
            Score(
                fixture_id=fx.id,
                home_score=home_score,
                away_score=away_score,
                source=ScoreSource.MANUAL,
                verified=True,
            )
        )
        await session.commit()
    return fx


class TestLineupCredit:
    async def test_scheduled_fixture_credits_both_seeded_teams(
        self, session: AsyncSession, competition: Competition
    ):
        """An UNPLAYED R32 fixture already credits both teams with R32."""
        await _add_ko(
            session, competition, stage="round_of_32",
            home="Brazil", away="Korea Republic",
        )
        adv = await get_actual_advancement(session)
        assert adv["Brazil"] == "round_of_32"
        assert adv["Korea Republic"] == "round_of_32"

    async def test_lineup_credit_pays_predicted_points(
        self, session: AsyncSession, competition: Competition
    ):
        """A user who picked Brazil to reach R32 is paid as soon as Brazil
        is seeded into an R32 fixture — before kickoff."""
        await _add_ko(
            session, competition, stage="round_of_32",
            home="Brazil", away="Korea Republic",
        )
        adv = await get_actual_advancement(session)
        pred = TeamPrediction(
            team="Brazil", stage="round_of_32", phase=PredictionPhase.PHASE_1
        )
        assert calculate_advancement_points(pred, adv, PredictionPhase.PHASE_1) == 20

    async def test_winner_advance_still_requires_finished_match(
        self, session: AsyncSession, competition: Competition
    ):
        """Brazil wins a FINISHED R32 match → credited with reaching R16."""
        await _add_ko(
            session, competition, stage="round_of_32",
            home="Brazil", away="Korea Republic",
            home_score=2, away_score=0, status=MatchStatus.FINISHED,
        )
        adv = await get_actual_advancement(session)
        assert adv["Brazil"] == "round_of_16"
        # The loser keeps the "reached R32" credit only.
        assert adv["Korea Republic"] == "round_of_32"

    async def test_scheduled_final_credits_finalists_but_not_winner(
        self, session: AsyncSession, competition: Competition
    ):
        """Both finalists are credited with `final` once seeded; nobody is
        the `winner` until the final is FINISHED and scored."""
        await _add_ko(
            session, competition, stage="final",
            home="Brazil", away="France",
        )
        adv = await get_actual_advancement(session)
        assert adv["Brazil"] == "final"
        assert adv["France"] == "final"
        assert "winner" not in adv.values()

    async def test_finished_final_crowns_the_winner(
        self, session: AsyncSession, competition: Competition
    ):
        await _add_ko(
            session, competition, stage="final",
            home="Brazil", away="France",
            home_score=2, away_score=1, status=MatchStatus.FINISHED,
        )
        adv = await get_actual_advancement(session)
        assert adv["Brazil"] == "winner"
        assert adv["France"] == "final"

    async def test_placeholder_team_names_pay_no_points(
        self, session: AsyncSession, competition: Competition
    ):
        """Football-Data may seed fixtures with placeholder strings before
        the real team is known. They show up in the advancement dict but
        can never pay points — no user prediction matches a placeholder,
        and real teams not yet seeded earn nothing."""
        await _add_ko(
            session, competition, stage="round_of_16",
            home="Winner of Match 32", away="Winner of Match 33",
        )
        adv = await get_actual_advancement(session)
        assert adv["Winner of Match 32"] == "round_of_16"

        # Brazil isn't seeded anywhere yet → a Brazil pick pays 0.
        pred = TeamPrediction(
            team="Brazil", stage="round_of_16", phase=PredictionPhase.PHASE_1
        )
        assert calculate_advancement_points(pred, adv, PredictionPhase.PHASE_1) == 0

    async def test_higher_stage_wins_when_both_signals_present(
        self, session: AsyncSession, competition: Competition
    ):
        """A finished R32 (winner-advance → R16) plus a scheduled R16
        seeding (lineup → R16) agree; a later QF seeding upgrades it."""
        await _add_ko(
            session, competition, stage="round_of_32",
            home="Brazil", away="Korea Republic",
            home_score=1, away_score=0, status=MatchStatus.FINISHED,
        )
        await _add_ko(
            session, competition, stage="round_of_16",
            home="Brazil", away="Mexico",
        )
        adv = await get_actual_advancement(session)
        assert adv["Brazil"] == "round_of_16"

        # Brazil later seeded into a QF fixture → credit upgrades.
        await _add_ko(
            session, competition, stage="quarter_final",
            home="Brazil", away="Spain",
        )
        adv = await get_actual_advancement(session)
        assert adv["Brazil"] == "quarter_final"
