"""Tests for the admin entry-completeness service.

Expected-count ground truth (verified against the dev DB, 2026-06-10):
- 72 group-stage fixtures → 72 match predictions per complete entry.
- 63 bracket picks per complete entry: 32 R32 + 16 R16 + 8 QF + 4 SF
  + 2 Final + 1 Winner. There are NO "group"-stage TeamPrediction rows.
- Bonus completeness counts only CURRENT question ids — legacy entries
  carry rows for retired questions (the 10 → 4 trim) which must not
  inflate the count. BonusPrediction has no phase column.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — registers all SQLModel tables for metadata
from app.models.bonus import BonusPrediction
from app.models.competition import Competition
from app.models.entry import (
    EntryStatus,
    PredictionEntry,
    PredictionEntryPhase,
)
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import (
    MatchPrediction,
    PredictionPhase,
    TeamPrediction,
)
from app.models.user import AuthProvider, User
from app.services.bonus import get_questions as get_bonus_questions
from app.services.completeness import (
    EntryCompletenessResult,
    expected_bonus_count,
    expected_bracket_count,
    expected_match_count,
)


# ─── DB session fixture ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """In-memory SQLite session for one test. Tables created fresh."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


# ─── Schema / helper tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expected_match_count_uses_group_stage_fixtures(db_session):
    """expected_match_count returns the number of group-stage fixtures."""
    count = await expected_match_count(db_session)
    assert isinstance(count, int)
    assert count == 0  # empty test DB


def test_expected_bracket_count_sums_stage_quotas():
    """expected_bracket_count returns 63: 32+16+8+4+2+1. No group rows."""
    assert expected_bracket_count() == 32 + 16 + 8 + 4 + 2 + 1


def test_expected_bonus_count_matches_yaml_questions():
    """expected_bonus_count returns the number of YAML-configured questions."""
    count = expected_bonus_count()
    assert isinstance(count, int)
    assert count > 0  # currently 4 per CLAUDE.md


def test_entry_completeness_result_schema():
    """Schema accepts the required fields."""
    r = EntryCompletenessResult(
        entry_id=uuid4(),
        entry_name="Test",
        user_name="Tester",
        user_email="t@example.com",
        missing_match_picks=3,
        missing_bracket_picks=5,
        missing_bonus_picks=1,
        is_complete=False,
    )
    assert r.is_complete is False
    assert r.missing_match_picks == 3


def test_entry_completeness_result_detail_optional():
    """detail field is optional, defaults to None."""
    r = EntryCompletenessResult(
        entry_id=uuid4(),
        entry_name="Test",
        user_name="Tester",
        user_email="t@example.com",
        missing_match_picks=0,
        missing_bracket_picks=0,
        missing_bonus_picks=0,
        is_complete=True,
    )
    assert r.detail is None
