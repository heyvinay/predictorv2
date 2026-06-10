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


# ─── Factory helpers for the scenario fixture ──────────────────────────

from app.services.completeness import check_all_eligible_entries  # noqa: E402

_BRACKET_STAGES = {
    "round_of_32": 32,
    "round_of_16": 16,
    "quarter_final": 8,
    "semi_final": 4,
    "final": 2,
    "winner": 1,
}


async def _make_competition(session: AsyncSession) -> Competition:
    comp = Competition(
        name="WC2026",
        external_id="WC2026",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _make_user(session: AsyncSession, email: str, name: str) -> User:
    u = User(
        email=email,
        name=name,
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _make_group_fixture(
    session: AsyncSession,
    competition: Competition,
    match_number: int,
) -> Fixture:
    f = Fixture(
        competition_id=competition.id,
        home_team=f"Home{match_number}",
        away_team=f"Away{match_number}",
        kickoff=datetime(2026, 6, 11, 18, 0, tzinfo=timezone.utc)
        + timedelta(hours=match_number),
        stage="group",
        group="A",
        match_number=match_number,
        status=MatchStatus.SCHEDULED,
    )
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


async def _make_entry(
    session: AsyncSession,
    user: User,
    competition: Competition,
    entry_number: int,
    *,
    is_disabled: bool = False,
    withdrawn: bool = False,
) -> PredictionEntry:
    entry = PredictionEntry(
        user_id=user.id,
        competition_id=competition.id,
        display_name=f"{user.name}'s entry",
        reference=f"REF-{uuid4().hex[:8]}",
        entry_number=entry_number,
        is_disabled=is_disabled,
        withdrawn_at=datetime.now(timezone.utc) if withdrawn else None,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    session.add(
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.SUBMITTED,
        )
    )
    await session.commit()
    return entry


async def _add_match_picks(
    session: AsyncSession,
    entry: PredictionEntry,
    fixtures: list[Fixture],
) -> None:
    for f in fixtures:
        session.add(
            MatchPrediction(
                entry_id=entry.id,
                fixture_id=f.id,
                phase=PredictionPhase.PHASE_1,
                home_score=1,
                away_score=0,
            )
        )
    await session.commit()


async def _add_bracket_picks(
    session: AsyncSession,
    entry: PredictionEntry,
    *,
    full: bool = True,
) -> None:
    """full=True populates all 63 expected picks; full=False skips R32
    entirely (leaves 32 missing)."""
    for stage, count in _BRACKET_STAGES.items():
        if stage == "round_of_32" and not full:
            continue
        for i in range(count):
            session.add(
                TeamPrediction(
                    entry_id=entry.id,
                    team=f"Team-{stage}-{i}",
                    stage=stage,
                    phase=PredictionPhase.PHASE_1,
                )
            )
    await session.commit()


async def _add_bonus_picks(
    session: AsyncSession,
    entry: PredictionEntry,
) -> None:
    for q in get_bonus_questions():
        session.add(
            BonusPrediction(
                entry_id=entry.id,
                question_id=q.id,
                answer="placeholder",
            )
        )
    await session.commit()


# ─── Scenario fixture — one DB state covering every branch ─────────────


@pytest_asyncio.fixture
async def completeness_scenario(db_session: AsyncSession):
    """Build a DB containing one of each entry shape we test against:

    - complete: all picks present, eligible. is_complete=True.
    - missing_match: missing 3 of 10 group picks.
    - missing_bracket: missing all 32 R32 picks.
    - legacy_bonus: complete + an extra row for a RETIRED question id —
      must still be complete (retired rows don't count either way).
    - disabled: complete but is_disabled=True. Excluded.
    - withdrawn: complete but withdrawn_at set. Excluded.

    Group-stage fixture count is 10 (proxy for 72 — the math is the same).
    """
    comp = await _make_competition(db_session)
    fixtures = [
        await _make_group_fixture(db_session, comp, i) for i in range(1, 11)
    ]

    users = {}
    entries = {}
    for i, slug in enumerate(
        ["complete", "missing_match", "missing_bracket", "legacy_bonus",
         "disabled", "withdrawn"],
        start=1,
    ):
        users[slug] = await _make_user(db_session, f"{slug}@test", slug.title())
        entries[slug] = await _make_entry(
            db_session,
            users[slug],
            comp,
            i,
            is_disabled=(slug == "disabled"),
            withdrawn=(slug == "withdrawn"),
        )

    # complete — everything present
    await _add_match_picks(db_session, entries["complete"], fixtures)
    await _add_bracket_picks(db_session, entries["complete"], full=True)
    await _add_bonus_picks(db_session, entries["complete"])

    # missing_match — 3 group picks short
    await _add_match_picks(db_session, entries["missing_match"], fixtures[:7])
    await _add_bracket_picks(db_session, entries["missing_match"], full=True)
    await _add_bonus_picks(db_session, entries["missing_match"])

    # missing_bracket — no R32 picks
    await _add_match_picks(db_session, entries["missing_bracket"], fixtures)
    await _add_bracket_picks(db_session, entries["missing_bracket"], full=False)
    await _add_bonus_picks(db_session, entries["missing_bracket"])

    # legacy_bonus — complete + a retired-question row
    await _add_match_picks(db_session, entries["legacy_bonus"], fixtures)
    await _add_bracket_picks(db_session, entries["legacy_bonus"], full=True)
    await _add_bonus_picks(db_session, entries["legacy_bonus"])
    db_session.add(
        BonusPrediction(
            entry_id=entries["legacy_bonus"].id,
            question_id="retired_question_from_v1",
            answer="stale",
        )
    )
    await db_session.commit()

    # disabled + withdrawn — fully complete data, excluded by eligibility
    for slug in ("disabled", "withdrawn"):
        await _add_match_picks(db_session, entries[slug], fixtures)
        await _add_bracket_picks(db_session, entries[slug], full=True)
        await _add_bonus_picks(db_session, entries[slug])

    return entries


# ─── DB-level tests for check_all_eligible_entries ─────────────────────


@pytest.mark.asyncio
async def test_check_all_eligible_entries_categorizes_correctly(
    db_session, completeness_scenario
):
    """Single rich scenario hits every branch in one go."""
    results = await check_all_eligible_entries(db_session)
    by_id = {r.entry_id: r for r in results}

    # Disabled + withdrawn → excluded entirely.
    assert completeness_scenario["disabled"].id not in by_id
    assert completeness_scenario["withdrawn"].id not in by_id

    # Complete entry → all zeros, is_complete=True.
    complete = by_id[completeness_scenario["complete"].id]
    assert complete.missing_match_picks == 0
    assert complete.missing_bracket_picks == 0
    assert complete.missing_bonus_picks == 0
    assert complete.is_complete is True

    # Missing 3 of 10 group picks.
    mm = by_id[completeness_scenario["missing_match"].id]
    assert mm.missing_match_picks == 3
    assert mm.is_complete is False

    # Missing 32 R32 picks → bracket gap 32.
    mb = by_id[completeness_scenario["missing_bracket"].id]
    assert mb.missing_bracket_picks == 32
    assert mb.is_complete is False

    # Legacy-bonus entry: the retired-question row neither helps nor hurts.
    lb = by_id[completeness_scenario["legacy_bonus"].id]
    assert lb.missing_bonus_picks == 0
    assert lb.is_complete is True


@pytest.mark.asyncio
async def test_check_all_eligible_entries_detail_breakdown(
    db_session, completeness_scenario
):
    """detail=True populates per-fixture / per-stage drill-down."""
    results = await check_all_eligible_entries(db_session, detail=True)
    by_id = {r.entry_id: r for r in results}

    mm = by_id[completeness_scenario["missing_match"].id]
    assert mm.detail is not None
    assert len(mm.detail.missing_fixture_ids) == 3

    mb = by_id[completeness_scenario["missing_bracket"].id]
    assert mb.detail is not None
    assert mb.detail.missing_bracket.get("round_of_32") == 32

    complete = by_id[completeness_scenario["complete"].id]
    assert complete.detail is not None
    assert complete.detail.missing_fixture_ids == []
    assert complete.detail.missing_bracket == {}
    assert complete.detail.missing_bonus_ids == []


@pytest.mark.asyncio
async def test_check_all_eligible_entries_empty_db(db_session):
    """No eligible entries → empty list, no crash."""
    results = await check_all_eligible_entries(db_session)
    assert results == []
