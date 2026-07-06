"""Tests for dashboard-stats service — daily MVPs, personal trail, pool distribution.

Project-truth model names (adapted from plan):
- PredictionEntry.display_name (NOT entry_name), .is_disabled, .withdrawn_at
- PredictionEntryPhase.status = EntryStatus.SUBMITTED
- LeaderboardSnapshot.position (NOT rank); no competition_id on snapshot
- Uses session.execute(...) not .exec() (raw SQLAlchemy convention).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — registers all models
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services.dashboard_stats import (
    compute_daily_mvps,
    compute_personal_trail,
    compute_pool_distribution,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared DB fixture (aiosqlite in-memory — same pattern as test_champion_survival)
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


async def _seed_basic_pool(
    session: AsyncSession, *, deadline_passed: bool = True
):
    """Seed 5 eligible entries with daily snapshots over the last 6 days."""
    deadline = (
        utc_now() - timedelta(hours=1)
        if deadline_passed
        else utc_now() + timedelta(days=1)
    )
    comp = Competition(
        name="t",
        external_id="WC",
        is_active=True,
        phase1_deadline=deadline,
        is_phase2_active=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.flush()

    entries: dict[str, PredictionEntry] = {}
    for idx, label in enumerate(("a", "b", "c", "d", "e")):
        user = User(
            email=f"{label}@t",
            name=label.upper(),
            is_admin=False,
            password_hash="x",
            auth_provider=AuthProvider.EMAIL,
        )
        session.add(user)
        await session.flush()
        entry = PredictionEntry(
            user_id=user.id,
            competition_id=comp.id,
            reference=f"WC26-{uuid.uuid4().hex[:6]}",
            display_name=f"{label}-entry",
            entry_number=1,
            is_disabled=False,
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
        entries[label] = entry

    # Daily snapshots, 6 days of history. Points go up over time.
    # On Day 5 (today), entry A scored +20 (most), so A is today's MVP.
    today = date.today()
    plan = {
        "a": [100, 105, 110, 120, 130, 150],  # +5,+5,+10,+10,+20 (today MVP)
        "b": [100, 110, 120, 125, 135, 140],
        "c": [100, 105, 115, 130, 140, 145],
        "d": [100, 108, 113, 121, 130, 135],
        "e": [100, 102, 105, 110, 115, 122],
    }
    for label, points_path in plan.items():
        for d_offset, pts in enumerate(points_path):
            session.add(
                LeaderboardSnapshot(
                    entry_id=entries[label].id,
                    user_id=entries[label].user_id,
                    captured_date=today - timedelta(days=5 - d_offset),
                    position=1,
                    total_points=pts,
                )
            )
    await session.commit()
    return entries, comp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_daily_mvps_returns_empty_pre_deadline(session: AsyncSession):
    await _seed_basic_pool(session, deadline_passed=False)
    result = await compute_daily_mvps(session)
    assert result == []


async def test_daily_mvps_picks_top_day_scorer(session: AsyncSession):
    entries, _comp = await _seed_basic_pool(session)
    result = await compute_daily_mvps(session)
    # Today's MVP (most-recent-first): entry A with +20
    assert result, "Expected at least one MVP"
    today_mvp = result[0]
    assert today_mvp.subject_entry_id == str(entries["a"].id)
    assert today_mvp.day_points == 20


async def test_daily_mvps_caps_at_5(session: AsyncSession):
    await _seed_basic_pool(session)
    result = await compute_daily_mvps(session)
    assert len(result) <= 5


async def test_daily_mvps_tie_break_lower_rank_wins(session: AsyncSession):
    """When two entries score the same day-points, the lower current rank wins."""
    comp = Competition(
        name="t",
        external_id="WC",
        is_active=True,
        phase1_deadline=utc_now() - timedelta(hours=1),
        is_phase2_active=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.flush()
    today = date.today()
    for label in ("hi", "lo"):
        user = User(
            email=f"{label}@t",
            name=label,
            is_admin=False,
            password_hash="x",
            auth_provider=AuthProvider.EMAIL,
        )
        session.add(user)
        await session.flush()
        entry = PredictionEntry(
            user_id=user.id,
            competition_id=comp.id,
            reference=f"WC26-{uuid.uuid4().hex[:6]}",
            display_name=label,
            entry_number=1,
            is_disabled=False,
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
        # Both scored exactly +10 today
        session.add(
            LeaderboardSnapshot(
                entry_id=entry.id,
                user_id=user.id,
                captured_date=today - timedelta(days=1),
                position=10 if label == "lo" else 5,
                total_points=90,
            )
        )
        session.add(
            LeaderboardSnapshot(
                entry_id=entry.id,
                user_id=user.id,
                captured_date=today,
                position=10 if label == "lo" else 5,
                total_points=100,
            )
        )
    await session.commit()

    result = await compute_daily_mvps(session)
    # "hi" is at rank 5 (lower number = better) so should win the tie
    assert result, "Expected at least one MVP"
    assert result[0].user_name == "hi"


async def test_daily_mvps_captured_date_is_date(session: AsyncSession):
    await _seed_basic_pool(session)
    result = await compute_daily_mvps(session)
    for mvp in result:
        assert isinstance(mvp.captured_date, date)


async def test_personal_trail_empty_pre_deadline(session: AsyncSession):
    entries, _ = await _seed_basic_pool(session, deadline_passed=False)
    from sqlalchemy import select as sa_select
    user_row = (await session.execute(sa_select(User).where(User.name == "A"))).scalar_one()
    result = await compute_personal_trail(session, user_id=str(user_row.id))
    assert result == []


async def test_personal_trail_returns_user_entries(session: AsyncSession):
    entries, _ = await _seed_basic_pool(session)
    from sqlalchemy import select as sa_select
    user_row = (await session.execute(sa_select(User).where(User.name == "A"))).scalar_one()
    result = await compute_personal_trail(session, user_id=str(user_row.id))
    assert len(result) >= 1
    assert any(e.entry_id == str(entries["a"].id) for e in result)


async def test_personal_trail_includes_pool_average(session: AsyncSession):
    """`pool_avg_points` per day should be the mean across all eligible entries that day."""
    entries, _ = await _seed_basic_pool(session)
    from sqlalchemy import select as sa_select
    user_row = (await session.execute(sa_select(User).where(User.name == "A"))).scalar_one()
    result = await compute_personal_trail(session, user_id=str(user_row.id))
    # On today, snapshots are a=150, b=140, c=145, d=135, e=122; mean = 138.4
    entry_a = next(e for e in result if e.entry_id == str(entries["a"].id))
    today_point = entry_a.points[-1]
    assert today_point.pool_avg_points == pytest.approx(138.4)
    assert today_point.your_points == 150


async def test_personal_trail_current_gap(session: AsyncSession):
    entries, _ = await _seed_basic_pool(session)
    from sqlalchemy import select as sa_select
    user_row = (await session.execute(sa_select(User).where(User.name == "A"))).scalar_one()
    result = await compute_personal_trail(session, user_id=str(user_row.id))
    entry_a = next(e for e in result if e.entry_id == str(entries["a"].id))
    # 150 - 138.4 = 11.6
    assert entry_a.current_gap == pytest.approx(11.6)


async def test_pool_distribution_empty_pre_deadline(session: AsyncSession):
    entries, _ = await _seed_basic_pool(session, deadline_passed=False)
    from sqlalchemy import select as sa_select
    user_row = (await session.execute(sa_select(User).where(User.name == "A"))).scalar_one()
    result = await compute_pool_distribution(session, user_id=str(user_row.id))
    assert result.total_entries == 0
    assert result.bins == []
    assert result.your_entries == []


async def test_pool_distribution_bins(session: AsyncSession):
    """Full-pool histogram spans every eligible entry's today-points
    (122..150 across the 5-entry seed pool), not a narrow window around
    one user — every bucket's count sums to the pool size."""
    entries, _ = await _seed_basic_pool(session)
    from sqlalchemy import select as sa_select
    user_row = (await session.execute(sa_select(User).where(User.name == "A"))).scalar_one()
    result = await compute_pool_distribution(session, user_id=str(user_row.id))
    assert result.total_entries == 5
    assert result.min_points == 122
    assert result.max_points == 150
    assert sum(b.count for b in result.bins) == 5
    # Entry A (150 pts, the day's best) is marked in your_entries.
    assert len(result.your_entries) == 1
    assert result.your_entries[0].entry_id == str(entries["a"].id)
    assert result.your_entries[0].points == 150


async def test_pool_distribution_marks_all_of_a_multi_entry_users_entries(session: AsyncSession):
    """A user with 2 entries gets BOTH marked in your_entries, not just
    their best-ranked one — the v2.198.x redesign's whole point."""
    import uuid
    from app.models import AuthProvider
    comp = Competition(name="t", phase1_deadline=utc_now() - timedelta(hours=1), is_phase2_active=False)
    session.add(comp)
    await session.flush()
    u = User(email="multi@t", name="Multi", is_admin=False, password_hash="x", auth_provider=AuthProvider.EMAIL)
    session.add(u)
    await session.flush()
    today = date.today()
    for entry_number, (label, pts, pos) in enumerate((("first", 200, 1), ("second", 150, 3)), start=1):
        entry = PredictionEntry(
            user_id=u.id, competition_id=comp.id, display_name=label,
            is_disabled=False, reference=f"WC26-{uuid.uuid4().hex[:6]}", entry_number=entry_number,
        )
        session.add(entry)
        await session.flush()
        session.add(PredictionEntryPhase(entry_id=entry.id, phase=PredictionPhase.PHASE_1, status=EntryStatus.SUBMITTED))
        session.add(LeaderboardSnapshot(entry_id=entry.id, user_id=u.id, captured_date=today, position=pos, total_points=pts))
    # A third, unrelated entry so the pool isn't just this one user.
    other = User(email="other@t", name="Other", is_admin=False, password_hash="x", auth_provider=AuthProvider.EMAIL)
    session.add(other)
    await session.flush()
    other_entry = PredictionEntry(
        user_id=other.id, competition_id=comp.id, display_name="other-entry",
        is_disabled=False, reference=f"WC26-{uuid.uuid4().hex[:6]}", entry_number=1,
    )
    session.add(other_entry)
    await session.flush()
    session.add(PredictionEntryPhase(entry_id=other_entry.id, phase=PredictionPhase.PHASE_1, status=EntryStatus.SUBMITTED))
    session.add(LeaderboardSnapshot(entry_id=other_entry.id, user_id=other.id, captured_date=today, position=2, total_points=175))
    await session.commit()

    from sqlalchemy import select as sa_select
    multi_user = (await session.execute(sa_select(User).where(User.name == "Multi"))).scalar_one()
    result = await compute_pool_distribution(session, user_id=str(multi_user.id))
    assert result.total_entries == 3
    assert {e.entry_name for e in result.your_entries} == {"first", "second"}
    # Sorted best-first (lowest position number first).
    assert [e.position for e in result.your_entries] == [1, 3]


async def test_pool_distribution_leader_caption(session: AsyncSession):
    """When the user's single entry is at #1, caption says they're leading."""
    import uuid
    from app.models import AuthProvider
    comp = Competition(name="t", phase1_deadline=utc_now() - timedelta(hours=1), is_phase2_active=False)
    session.add(comp)
    await session.flush()
    today = date.today()
    for i, (label, pts) in enumerate([("leader", 200), ("second", 180)]):
        u = User(
            email=f"{label}@t", name=label, is_admin=False,
            password_hash="x", auth_provider=AuthProvider.EMAIL,
        )
        session.add(u)
        await session.flush()
        entry = PredictionEntry(
            user_id=u.id, competition_id=comp.id,
            display_name=label, is_disabled=False,
            reference=f"WC26-{uuid.uuid4().hex[:6]}",
            entry_number=1,
        )
        session.add(entry)
        await session.flush()
        session.add(PredictionEntryPhase(
            entry_id=entry.id, phase=PredictionPhase.PHASE_1,
            status=EntryStatus.SUBMITTED,
        ))
        session.add(LeaderboardSnapshot(
            entry_id=entry.id, user_id=u.id,
            captured_date=today, position=1 if label == "leader" else 2,
            total_points=pts,
        ))
    await session.commit()

    from sqlalchemy import select as sa_select
    leader_user = (await session.execute(sa_select(User).where(User.name == "leader"))).scalar_one()
    result = await compute_pool_distribution(session, user_id=str(leader_user.id))
    assert result.your_entries[0].position == 1
    caption_lower = result.caption.lower()
    assert any(word in caption_lower for word in ("leading", "above", "ahead"))


async def test_pool_distribution_default_caption(session: AsyncSession):
    entries, _ = await _seed_basic_pool(session)
    from sqlalchemy import select as sa_select
    user_row = (await session.execute(sa_select(User).where(User.name == "A"))).scalar_one()
    result = await compute_pool_distribution(session, user_id=str(user_row.id))
    caption_lower = result.caption.lower()
    assert "entries" in caption_lower or "points" in caption_lower
