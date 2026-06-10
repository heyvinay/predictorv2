"""Bracket-exposure service — team-stage-slot semantics (v2.161.0).

A full FIFA 2026 bracket stores 63 TeamPrediction rows (32 R32 teams +
16 R16 + 8 QF + 4 SF + 2 finalists + 1 winner), which is what the
frontend's bracketToPredictions submits. Under the canonical advancement
ladder (20/30/40/50/75/100) a full bracket has 1890 points on the line:
32·20 + 16·30 + 8·40 + 4·50 + 2·75 + 1·100.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.user import AuthProvider, User
from app.services.bracket_exposure import (
    PICKS_PER_STAGE_PHASE_1,
    TOTAL_PHASE_1_BRACKET_PICKS,
    compute_bracket_exposure,
)


_SCORING_CONFIG = {
    "advancement": {
        "round_of_32": 20,
        "round_of_16": 30,
        "quarter_final": 40,
        "semi_final": 50,
        "final": 75,
        "winner": 100,
    },
    "phase_multipliers": {"phase_1": 1.0, "phase_2": 0.7},
}


@pytest.fixture(autouse=True)
def _patched_config():
    with patch(
        "app.services.bracket_exposure.get_scoring_config",
        return_value=_SCORING_CONFIG,
    ):
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
async def entry(session: AsyncSession) -> PredictionEntry:
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
    user = User(
        email="t@example.com",
        name="Tester",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    e = PredictionEntry(
        competition_id=comp.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6].upper()}",
        display_name="Entry",
        entry_number=1,
    )
    session.add(e)
    await session.commit()
    await session.refresh(e)
    session.add(
        PredictionEntryPhase(
            entry_id=e.id,
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.SUBMITTED,
        )
    )
    await session.commit()
    return e


def test_slot_counts_total_63():
    assert PICKS_PER_STAGE_PHASE_1 == {
        "round_of_32": 32,
        "round_of_16": 16,
        "quarter_final": 8,
        "semi_final": 4,
        "final": 2,
        "winner": 1,
    }
    assert TOTAL_PHASE_1_BRACKET_PICKS == 63


async def test_full_bracket_exposure(
    session: AsyncSession, entry: PredictionEntry
):
    """63 singular rows → picks 63/63 and 1890 points on the line; the
    final pair resolves to (winner, other finalist)."""
    teams = [f"Team{i:02d}" for i in range(32)]
    plan: list[tuple[str, list[str]]] = [
        ("round_of_32", teams),
        ("round_of_16", teams[:16]),
        ("quarter_final", teams[:8]),
        ("semi_final", teams[:4]),
        ("final", teams[:2]),
        ("winner", teams[:1]),
    ]
    for stage, stage_teams in plan:
        for team in stage_teams:
            session.add(
                TeamPrediction(
                    entry_id=entry.id,
                    team=team,
                    stage=stage,
                    phase=PredictionPhase.PHASE_1,
                )
            )
    await session.commit()

    result = await compute_bracket_exposure(session, entry.id)
    assert result.picks_total == 63
    assert result.picks_locked == 63
    assert result.points_available == 1890
    assert result.final_winner == "Team00"
    assert result.final_opponent == "Team01"


async def test_partial_bracket_counts_only_locked(
    session: AsyncSession, entry: PredictionEntry
):
    """A bracket with only the R32 row set shows 32/63 locked and only
    R32 points on the line."""
    for i in range(32):
        session.add(
            TeamPrediction(
                entry_id=entry.id,
                team=f"Team{i:02d}",
                stage="round_of_32",
                phase=PredictionPhase.PHASE_1,
            )
        )
    await session.commit()

    result = await compute_bracket_exposure(session, entry.id)
    assert result.picks_total == 63
    assert result.picks_locked == 32
    assert result.points_available == 32 * 20
    assert result.final_winner is None
