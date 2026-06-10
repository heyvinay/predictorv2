"""Entry-completeness service.

All SUBMITTED + eligible entries MUST have every required pick before the
tournament starts (product invariant, 2026-06-10). This module computes
per-entry missing counts so an admin can chase gaps. Report-only — no
enforcement, no auto-disable.

Expected-count ground truth:
- Match picks: one per group-stage fixture (72 for WC2026), PHASE_1.
- Bracket picks: 63 = 32 R32 + 16 R16 + 8 QF + 4 SF + 2 Final + 1 Winner.
  There are no "group"-stage TeamPrediction rows — group standings are
  implied by the R32 selection, not stored separately.
- Bonus picks: one per CURRENT YAML question (4 today). Legacy entries
  carry rows for retired question ids (the 10 → 4 trim); those must not
  count toward completeness. BonusPrediction has no phase column.

Eligibility reuses `eligible_entry_ids_select()` from the scoring service
so "who must be complete" stays identical to "who scoring pays".
"""

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from app.models.bonus import BonusPrediction
from app.models.entry import PredictionEntry
from app.models.fixture import Fixture
from app.models.prediction import (
    MatchPrediction,
    PredictionPhase,
    TeamPrediction,
)
from app.models.user import User
from app.services.bonus import get_questions as get_bonus_questions
from app.services.scoring import eligible_entry_ids_select


class EntryCompletenessDetail(BaseModel):
    """Drill-down detail returned only when ?detail=true."""

    missing_fixture_ids: list[uuid.UUID] = []
    missing_bracket: dict[str, int] = {}  # stage → missing count
    missing_bonus_ids: list[str] = []


class EntryCompletenessResult(BaseModel):
    """One row per eligible entry."""

    entry_id: uuid.UUID
    entry_name: str
    user_name: str
    user_email: str
    missing_match_picks: int
    missing_bracket_picks: int
    missing_bonus_picks: int
    is_complete: bool
    detail: EntryCompletenessDetail | None = None


# Per-stage expected pick counts — bracket geometry for a 48-team World Cup.
# No "group" entry: group-standings picks aren't stored as TeamPrediction rows.
_BRACKET_EXPECTED: dict[str, int] = {
    "round_of_32": 32,
    "round_of_16": 16,
    "quarter_final": 8,
    "semi_final": 4,
    "final": 2,
    "winner": 1,
}


async def expected_match_count(session: AsyncSession) -> int:
    """Number of group-stage fixtures the entry must predict on."""
    result = await session.execute(
        select(func.count(Fixture.id)).where(Fixture.stage == "group")
    )
    return int(result.scalar_one())


def expected_bracket_count() -> int:
    """Sum of stage-expected counts (63 for WC2026)."""
    return sum(_BRACKET_EXPECTED.values())


def expected_bonus_count() -> int:
    """Number of bonus questions defined in the YAML."""
    return len(get_bonus_questions())


async def check_all_eligible_entries(
    session: AsyncSession,
    *,
    detail: bool = False,
) -> list[EntryCompletenessResult]:
    """For every eligible entry (SUBMITTED, not disabled, not withdrawn),
    count missing picks across match / bracket / bonus categories.
    Single query per category; returns one row per entry.
    """
    # 1. Eligible entries with owner info. Eligibility predicate is shared
    # with scoring via eligible_entry_ids_select().
    eligible_rows = (
        await session.execute(
            select(PredictionEntry, User.name, User.email)
            .join(User, PredictionEntry.user_id == User.id)
            .where(PredictionEntry.id.in_(eligible_entry_ids_select()))
        )
    ).all()
    if not eligible_rows:
        return []

    entry_ids = [e.id for (e, _name, _email) in eligible_rows]
    by_entry_owner = {
        e.id: (e, name or email.split("@")[0], email)
        for (e, name, email) in eligible_rows
    }

    # 2. Match-pick counts per entry (one query, PHASE_1 only).
    match_counts = {
        eid: int(c)
        for eid, c in (
            await session.execute(
                select(MatchPrediction.entry_id, func.count(MatchPrediction.id))
                .where(MatchPrediction.entry_id.in_(entry_ids))
                .where(MatchPrediction.phase == PredictionPhase.PHASE_1)
                .group_by(MatchPrediction.entry_id)
            )
        ).all()
    }

    # 3. Bracket-pick counts per entry per stage (one query). Only stages
    # in _BRACKET_EXPECTED count — legacy/aux stages are ignored.
    bracket_counts_by_entry: dict[uuid.UUID, dict[str, int]] = {}
    for eid, stage, c in (
        await session.execute(
            select(
                TeamPrediction.entry_id,
                TeamPrediction.stage,
                func.count(TeamPrediction.id),
            )
            .where(TeamPrediction.entry_id.in_(entry_ids))
            .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
            .where(TeamPrediction.stage.in_(list(_BRACKET_EXPECTED.keys())))
            .group_by(TeamPrediction.entry_id, TeamPrediction.stage)
        )
    ).all():
        bracket_counts_by_entry.setdefault(eid, {})[stage] = int(c)

    # 4. Bonus-pick counts per entry (one query) — CURRENT question ids
    # only, so retired-question rows from the 10 → 4 trim don't inflate
    # the count. BonusPrediction has no phase column.
    current_bonus_ids = [q.id for q in get_bonus_questions()]
    bonus_counts: dict[uuid.UUID, int] = {}
    if current_bonus_ids:
        bonus_counts = {
            eid: int(c)
            for eid, c in (
                await session.execute(
                    select(BonusPrediction.entry_id, func.count(BonusPrediction.id))
                    .where(BonusPrediction.entry_id.in_(entry_ids))
                    .where(BonusPrediction.question_id.in_(current_bonus_ids))
                    .group_by(BonusPrediction.entry_id)
                )
            ).all()
        }

    # 5. Expected counts.
    expected_matches = await expected_match_count(session)
    expected_bracket = expected_bracket_count()
    expected_bonus = expected_bonus_count()

    # 6. Optional drill-down — computed only when requested.
    detail_by_entry: dict[uuid.UUID, EntryCompletenessDetail] = {}
    if detail:
        group_fixture_ids = {
            f
            for (f,) in (
                await session.execute(
                    select(Fixture.id).where(Fixture.stage == "group")
                )
            ).all()
        }
        picked_fixtures_by_entry: dict[uuid.UUID, set] = {}
        for eid, fid in (
            await session.execute(
                select(MatchPrediction.entry_id, MatchPrediction.fixture_id)
                .where(MatchPrediction.entry_id.in_(entry_ids))
                .where(MatchPrediction.phase == PredictionPhase.PHASE_1)
            )
        ).all():
            picked_fixtures_by_entry.setdefault(eid, set()).add(fid)

        all_bonus_ids = set(current_bonus_ids)
        picked_bonus_by_entry: dict[uuid.UUID, set] = {}
        for eid, qid in (
            await session.execute(
                select(BonusPrediction.entry_id, BonusPrediction.question_id)
                .where(BonusPrediction.entry_id.in_(entry_ids))
                .where(BonusPrediction.question_id.in_(current_bonus_ids))
            )
        ).all():
            picked_bonus_by_entry.setdefault(eid, set()).add(qid)

        for eid in entry_ids:
            missing_fixtures = sorted(
                group_fixture_ids - picked_fixtures_by_entry.get(eid, set()),
                key=str,
            )
            stage_actual = bracket_counts_by_entry.get(eid, {})
            missing_bracket_by_stage = {
                stage: expected - stage_actual.get(stage, 0)
                for stage, expected in _BRACKET_EXPECTED.items()
                if expected - stage_actual.get(stage, 0) > 0
            }
            missing_bonus = sorted(
                all_bonus_ids - picked_bonus_by_entry.get(eid, set())
            )
            detail_by_entry[eid] = EntryCompletenessDetail(
                missing_fixture_ids=missing_fixtures,
                missing_bracket=missing_bracket_by_stage,
                missing_bonus_ids=missing_bonus,
            )

    # 7. Compose results.
    out: list[EntryCompletenessResult] = []
    for eid in entry_ids:
        entry, name, email = by_entry_owner[eid]
        missing_match = max(0, expected_matches - match_counts.get(eid, 0))
        actual_bracket = sum(bracket_counts_by_entry.get(eid, {}).values())
        missing_bracket = max(0, expected_bracket - actual_bracket)
        missing_bonus = max(0, expected_bonus - bonus_counts.get(eid, 0))
        is_complete = (
            missing_match == 0 and missing_bracket == 0 and missing_bonus == 0
        )
        out.append(
            EntryCompletenessResult(
                entry_id=eid,
                entry_name=entry.display_name,
                user_name=name,
                user_email=email,
                missing_match_picks=missing_match,
                missing_bracket_picks=missing_bracket,
                missing_bonus_picks=missing_bonus,
                is_complete=is_complete,
                detail=detail_by_entry.get(eid) if detail else None,
            )
        )
    return out
