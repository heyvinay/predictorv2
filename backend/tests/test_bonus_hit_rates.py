"""Pool-wide bonus hit-rate aggregate (Insights "Bonus Points" card).

`compute_bonus_hit_rates` counts how many ELIGIBLE entries picked (any of)
the correct answer(s) for each RESOLVED bonus question, over the eligible
denominator. Eligibility mirrors `eligible_entry_ids_select()` (SUBMITTED,
not disabled, not withdrawn) so the stat lines up with every other pool
number. Matching uses `answer_in` — case/accent-insensitive, identical to
the per-entry scorer.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.models._datetime import utc_now
from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services.bonus import compute_bonus_hit_rates


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


_seq = 0


async def _entry(
    s: AsyncSession,
    comp: Competition,
    *,
    status: EntryStatus = EntryStatus.SUBMITTED,
    disabled: bool = False,
    withdrawn: bool = False,
) -> PredictionEntry:
    global _seq
    _seq += 1
    user = User(
        email=f"u{_seq}@test.com",
        name=f"User {_seq}",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
    )
    s.add(user)
    await s.flush()
    entry = PredictionEntry(
        competition_id=comp.id,
        user_id=user.id,
        reference=f"WC26-{_seq:06d}",
        display_name=f"Entry {_seq}",
        is_disabled=disabled,
        withdrawn_at=utc_now() if withdrawn else None,
        entry_number=1,
    )
    s.add(entry)
    await s.flush()
    s.add(
        PredictionEntryPhase(
            entry_id=entry.id, phase=PredictionPhase.PHASE_1, status=status
        )
    )
    await s.flush()
    return entry


async def _pick(s: AsyncSession, entry: PredictionEntry, qid: str, answer: str) -> None:
    s.add(BonusPrediction(entry_id=entry.id, question_id=qid, answer=answer))
    await s.flush()


async def _resolve(s: AsyncSession, comp: Competition, qid: str, *answers: str) -> None:
    for a in answers:
        s.add(
            BonusAnswer(
                competition_id=comp.id,
                question_id=qid,
                correct_answer=a,
                resolved_at=utc_now(),
            )
        )
    await s.flush()


class TestBonusHitRates:
    async def test_counts_correct_eligible_picks(self, db_session, competition):
        # 3 eligible entries; 2 picked the correct dark_horse answer (one
        # with different casing — must still count), 1 picked wrong.
        e1 = await _entry(db_session, competition)
        e2 = await _entry(db_session, competition)
        e3 = await _entry(db_session, competition)
        await _pick(db_session, e1, "dark_horse", "Norway")
        await _pick(db_session, e2, "dark_horse", "norway")  # case-insensitive
        await _pick(db_session, e3, "dark_horse", "Croatia")  # miss
        await _resolve(db_session, competition, "dark_horse", "Norway")
        await db_session.commit()

        rates = await compute_bonus_hit_rates(db_session, competition.id)
        by_qid = {r.question_id: r for r in rates}
        dh = by_qid["dark_horse"]
        assert dh.eligible_count == 3
        assert dh.hit_count == 2
        assert dh.hit_rate == pytest.approx(2 / 3)
        assert dh.correct_answers == ["Norway"]

    async def test_tie_counts_any_matching_answer(self, db_session, competition):
        # flop resolved to Germany + Netherlands (a tie); each entry picking
        # EITHER counts as a hit.
        e1 = await _entry(db_session, competition)
        e2 = await _entry(db_session, competition)
        await _pick(db_session, e1, "flop", "Germany")
        await _pick(db_session, e2, "flop", "Netherlands")
        await _resolve(db_session, competition, "flop", "Germany", "Netherlands")
        await db_session.commit()

        rates = await compute_bonus_hit_rates(db_session, competition.id)
        flop = {r.question_id: r for r in rates}["flop"]
        assert flop.hit_count == 2
        assert flop.eligible_count == 2
        assert flop.correct_answers == ["Germany", "Netherlands"]  # sorted

    async def test_ineligible_entries_excluded_from_both_sides(
        self, db_session, competition
    ):
        # 1 eligible (correct), plus a disabled, a withdrawn, and a DRAFT
        # entry each with the correct pick — none may count in numerator or
        # denominator.
        good = await _entry(db_session, competition)
        disabled = await _entry(db_session, competition, disabled=True)
        withdrawn = await _entry(db_session, competition, withdrawn=True)
        draft = await _entry(db_session, competition, status=EntryStatus.DRAFT)
        for e in (good, disabled, withdrawn, draft):
            await _pick(db_session, e, "dark_horse", "Norway")
        await _resolve(db_session, competition, "dark_horse", "Norway")
        await db_session.commit()

        rates = await compute_bonus_hit_rates(db_session, competition.id)
        dh = {r.question_id: r for r in rates}["dark_horse"]
        assert dh.eligible_count == 1
        assert dh.hit_count == 1
        assert dh.hit_rate == pytest.approx(1.0)

    async def test_unresolved_question_omitted(self, db_session, competition):
        # A pick with no recorded answer yet produces no hit-rate row.
        e1 = await _entry(db_session, competition)
        await _pick(db_session, e1, "dark_horse", "Norway")
        await db_session.commit()

        rates = await compute_bonus_hit_rates(db_session, competition.id)
        assert rates == []
