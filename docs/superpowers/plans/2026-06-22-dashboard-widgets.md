# Dashboard Widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three new widgets — Daily MVP, Personal Trail, Pool Distribution — to the V4 Dashboard as a full-width region below the existing two-column grid.

**Architecture:** Backend adds three additive endpoints (`/daily-mvps`, `/personal-trail`, `/pool-distribution`) and one service module (`dashboard_stats.py`) — no schema migration. Frontend mounts three new component cards inside `DashboardV4.svelte`, below the existing grid. All widgets respect blind-pool gate and degrade gracefully when their data is unavailable.

**Tech Stack:** FastAPI + SQLModel + Pydantic backend; SvelteKit + TypeScript + Tailwind/DaisyUI frontend; pytest + vitest tests; PostgreSQL prod / aiosqlite tests.

**Sister plan:** [2026-06-22-leaderboard-race-redesign.md](2026-06-22-leaderboard-race-redesign.md). Both ship in one PR per the **Bundle** decision; execute race redesign first, then this plan.

---

## File Structure

### Backend (created)

```
backend/app/services/dashboard_stats.py     # all 3 derivations
backend/tests/test_dashboard_stats.py       # pytest cases for all 3
```

### Backend (modified)

```
backend/app/api/leaderboard.py              # 3 new endpoints + Pydantic schemas
```

### Frontend (created — components live in dashboard/v4/ subfolder)

```
frontend/src/lib/components/dashboard/v4/DailyMvpStrip.svelte
frontend/src/lib/components/dashboard/v4/MvpChip.svelte
frontend/src/lib/components/dashboard/v4/PersonalTrailStrip.svelte
frontend/src/lib/components/dashboard/v4/PoolDistribution.svelte
```

### Frontend (modified)

```
frontend/src/lib/types/leaderboard.ts                       # add new types
frontend/src/lib/api/leaderboard.ts                         # add 3 fetchers
frontend/src/lib/utils/leaderboardV4.ts                     # add pure helpers
frontend/src/lib/utils/leaderboardV4.test.ts                # extend vitest cases
frontend/src/lib/components/dashboard/v4/DashboardV4.svelte # mount new region
```

---

## Conventions

- **Worktree-overlay test pattern** per CLAUDE.md for all `pytest` / `npm run check` commands.
- **Aware-UTC** datetimes throughout — `utc_now()` and `aware_utc()` from `app.models._datetime`.
- **Phase filter:** any join against `prediction_entry_phases` includes `phase = PhaseStatus.PHASE_1`.
- **Eligible entries:** `eligible_entry_ids_select()` from `app.services.scoring`.
- **Blind-pool:** every new endpoint checks `await is_phase1_locked(session)` and returns empty pre-deadline.

---

## Phase 1: Backend

### Task 1.1: Pydantic schemas + endpoint stubs

**Files:**
- Modify: `backend/app/api/leaderboard.py` (append schemas + 3 stub endpoints)

**Why this task:** Lock down wire-format types in one place so frontend can build against real URLs immediately. Stubs return zero/empty.

- [ ] **Step 1: Append the schemas at the bottom of `api/leaderboard.py`** (after the race-tab schemas added in the sister plan)

```python
# --------------------------------------------------------------------------
# Dashboard-widgets schemas (2026-06-22 spec)
# --------------------------------------------------------------------------

class DailyMvp(BaseModel):
    captured_date: date
    subject_entry_id: str
    user_name: str
    entry_name: str
    day_points: int
    rank_delta: int  # positive = climbed, negative = dropped


class DailyMvpsResponse(BaseModel):
    mvps: list[DailyMvp]
    generated_at: datetime


class TrailPoint(BaseModel):
    captured_date: date
    your_points: int
    pool_avg_points: float


class EntryTrail(BaseModel):
    entry_id: str
    entry_name: str
    current_rank: int
    current_gap: float
    points: list[TrailPoint]


class PersonalTrailResponse(BaseModel):
    entries: list[EntryTrail]
    generated_at: datetime


class DistBin(BaseModel):
    points_delta: int
    count: int


class PoolDistributionResponse(BaseModel):
    user_points: int
    window_size: int
    bins: list[DistBin]
    next_rank_points_away: int | None
    next_rank_position: int | None
    near_count: int
    caption: str
    generated_at: datetime
```

- [ ] **Step 2: Append the three stub endpoints**

```python
@router.get("/daily-mvps", response_model=DailyMvpsResponse)
async def daily_mvps(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DailyMvpsResponse:
    """Returns up to 5 daily MVPs (top scorer per day, most-recent-first)."""
    return DailyMvpsResponse(mvps=[], generated_at=utc_now())


@router.get("/personal-trail", response_model=PersonalTrailResponse)
async def personal_trail(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PersonalTrailResponse:
    """Returns the requesting user's entries' point trails vs the pool average."""
    return PersonalTrailResponse(entries=[], generated_at=utc_now())


@router.get("/pool-distribution", response_model=PoolDistributionResponse)
async def pool_distribution(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PoolDistributionResponse:
    """Returns the histogram of entries around the requesting user's points total."""
    return PoolDistributionResponse(
        user_points=0,
        window_size=5,
        bins=[],
        next_rank_points_away=None,
        next_rank_position=None,
        near_count=0,
        caption="",
        generated_at=utc_now(),
    )
```

- [ ] **Step 3: Smoke-test module compiles**

Overlay into main worktree, then:
```bash
docker-compose exec -T backend python -c "from app.api.leaderboard import router; print('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/leaderboard.py
git commit -m "feat(dashboard): scaffold widget endpoints + Pydantic schemas"
```

---

### Task 1.2: Daily MVPs service + wire endpoint

**Files:**
- Create: `backend/app/services/dashboard_stats.py`
- Modify: `backend/app/api/leaderboard.py` (replace stub body)
- Test: `backend/tests/test_dashboard_stats.py`

**Why this task:** Computes the top day-scorer for each of the last 5 days from `LeaderboardSnapshot` day-over-day diffs.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_dashboard_stats.py`:

```python
"""Tests for dashboard-stats service — daily MVPs, personal trail, pool distribution."""
from __future__ import annotations

from datetime import date, timedelta
import pytest

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Competition, LeaderboardSnapshot, PredictionEntry,
    PredictionEntryPhase, PhaseStatus, User,
)
from app.models._datetime import utc_now
from app.services.dashboard_stats import (
    compute_daily_mvps,
    compute_personal_trail,
    compute_pool_distribution,
)


pytestmark = pytest.mark.asyncio


async def _seed_basic_pool(session: AsyncSession, *, deadline_passed: bool = True):
    """Seed 5 eligible entries with daily snapshots over the last 6 days."""
    comp = Competition(
        name="t",
        phase1_deadline=utc_now() + timedelta(days=-1 if deadline_passed else 1),
        is_phase2_active=False,
    )
    session.add(comp)
    await session.flush()

    entries: dict[str, PredictionEntry] = {}
    for label in ("a", "b", "c", "d", "e"):
        user = User(email=f"{label}@t", name=label.upper(), is_admin=False)
        session.add(user)
        await session.flush()
        entry = PredictionEntry(
            user_id=user.id, competition_id=comp.id,
            entry_name=f"{label}-entry",
            disabled=False, withdrawn=False,
        )
        session.add(entry)
        await session.flush()
        session.add(PredictionEntryPhase(
            entry_id=entry.id, phase=PhaseStatus.PHASE_1,
            submitted_at=utc_now() - timedelta(days=10),
        ))
        entries[label] = entry

    # Daily snapshots, 6 days of history. Points go up over time.
    # On Day 5 (today), entry A scored +20 (most), so A is today's MVP.
    today = date.today()
    plan = {
        "a": [100, 105, 110, 120, 130, 150],  # +5,+5,+10,+10,+20 (today MVP)
        "b": [100, 110, 120, 125, 135, 140],  # +10,+10,+5,+10,+5  (Day 1 & 2 MVP w/ ties)
        "c": [100, 105, 115, 130, 140, 145],  # +5,+10,+15,+10,+5  (Day 3 MVP)
        "d": [100, 108, 113, 121, 130, 135],  # mostly low
        "e": [100, 102, 105, 110, 115, 122],  # mostly low
    }
    for label, points_path in plan.items():
        for d_offset, pts in enumerate(points_path):
            session.add(LeaderboardSnapshot(
                entry_id=entries[label].id, competition_id=comp.id,
                captured_date=today - timedelta(days=5 - d_offset),
                rank=1, total_points=pts,
            ))
    await session.commit()
    return entries, comp


async def test_daily_mvps_returns_empty_pre_deadline(session: AsyncSession):
    await _seed_basic_pool(session, deadline_passed=False)
    result = await compute_daily_mvps(session)
    assert result == []


async def test_daily_mvps_picks_top_day_scorer(session: AsyncSession):
    entries, _comp = await _seed_basic_pool(session)
    result = await compute_daily_mvps(session)
    # Today's MVP (most-recent-first): entry A with +20
    today_mvp = result[0]
    assert today_mvp.subject_entry_id == str(entries["a"].id)
    assert today_mvp.day_points == 20


async def test_daily_mvps_caps_at_5(session: AsyncSession):
    """Even if there are 10 days of snapshots, only return 5."""
    await _seed_basic_pool(session)
    result = await compute_daily_mvps(session)
    assert len(result) <= 5


async def test_daily_mvps_tie_break_lower_rank_wins(session: AsyncSession):
    """When two entries score the same day-points, the lower current rank wins."""
    comp = Competition(name="t", phase1_deadline=utc_now() - timedelta(hours=1), is_phase2_active=False)
    session.add(comp)
    await session.flush()
    today = date.today()
    for label in ("hi", "lo"):
        user = User(email=f"{label}@t", name=label, is_admin=False)
        session.add(user)
        await session.flush()
        entry = PredictionEntry(
            user_id=user.id, competition_id=comp.id,
            entry_name=label, disabled=False, withdrawn=False,
        )
        session.add(entry)
        await session.flush()
        session.add(PredictionEntryPhase(
            entry_id=entry.id, phase=PhaseStatus.PHASE_1,
            submitted_at=utc_now() - timedelta(days=5),
        ))
        # Both scored exactly +10 today
        session.add(LeaderboardSnapshot(
            entry_id=entry.id, competition_id=comp.id,
            captured_date=today - timedelta(days=1),
            rank=10 if label == "lo" else 5,
            total_points=90,
        ))
        session.add(LeaderboardSnapshot(
            entry_id=entry.id, competition_id=comp.id,
            captured_date=today,
            rank=10 if label == "lo" else 5,
            total_points=100,
        ))
    await session.commit()

    result = await compute_daily_mvps(session)
    # "hi" is at rank 5 (lower number = better) so should win the tie
    assert result[0].user_name == "hi"


async def test_daily_mvps_generated_at_aware(session: AsyncSession):
    """`compute_daily_mvps` returns list[DailyMvp]; the endpoint wrapper adds generated_at.
    Sanity-check the dataclass dates are date-typed, not datetimes."""
    await _seed_basic_pool(session)
    result = await compute_daily_mvps(session)
    for mvp in result:
        assert isinstance(mvp.captured_date, date)
```

- [ ] **Step 2: Run failing tests**

```bash
docker-compose exec -T backend pytest backend/tests/test_dashboard_stats.py::test_daily_mvps_returns_empty_pre_deadline backend/tests/test_dashboard_stats.py::test_daily_mvps_picks_top_day_scorer backend/tests/test_dashboard_stats.py::test_daily_mvps_caps_at_5 backend/tests/test_dashboard_stats.py::test_daily_mvps_tie_break_lower_rank_wins backend/tests/test_dashboard_stats.py::test_daily_mvps_generated_at_aware -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.dashboard_stats'`.

- [ ] **Step 3: Create the service**

Create `backend/app/services/dashboard_stats.py`:

```python
"""Dashboard widget derivations — daily MVPs, personal trail, pool distribution.

All three read from LeaderboardSnapshot and respect the blind-pool gate.
Datetimes are aware-UTC; dates are plain `date`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean

from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import LeaderboardSnapshot, PredictionEntry, User
from app.models._datetime import utc_now
from app.services.locking import is_phase1_locked
from app.services.scoring import eligible_entry_ids_select


MVP_LOOKBACK_DAYS = 5


@dataclass
class DailyMvp:
    captured_date: date
    subject_entry_id: str
    user_name: str
    entry_name: str
    day_points: int
    rank_delta: int


async def compute_daily_mvps(session: AsyncSession) -> list[DailyMvp]:
    """Returns up to 5 daily MVPs, newest-first. Empty pre-deadline."""
    if not await is_phase1_locked(session):
        return []

    today = date.today()
    earliest = today - timedelta(days=MVP_LOOKBACK_DAYS)

    rows = (
        await session.exec(
            select(
                LeaderboardSnapshot.entry_id,
                LeaderboardSnapshot.captured_date,
                LeaderboardSnapshot.rank,
                LeaderboardSnapshot.total_points,
                PredictionEntry.entry_name,
                User.name,
            )
            .join(PredictionEntry, PredictionEntry.id == LeaderboardSnapshot.entry_id)
            .join(User, User.id == PredictionEntry.user_id)
            .where(LeaderboardSnapshot.entry_id.in_(eligible_entry_ids_select()))
            .where(LeaderboardSnapshot.captured_date >= earliest - timedelta(days=1))  # need one day before to compute day-1's delta
            .order_by(LeaderboardSnapshot.entry_id, LeaderboardSnapshot.captured_date)
        )
    ).all()

    # Build per-entry chronological points map: entry_id -> [(date, rank, total, user_name, entry_name), ...]
    per_entry: dict[str, list[tuple[date, int, int, str, str]]] = {}
    for entry_id, captured_date, rank, pts, entry_name, user_name in rows:
        per_entry.setdefault(str(entry_id), []).append(
            (captured_date, rank, pts, user_name, entry_name)
        )

    # Compute day-points (delta vs previous day) per (entry_id, date)
    day_scores: dict[date, list[tuple[int, int, str, str, str, str]]] = {}
    # value tuples: (day_points, current_rank, entry_id, user_name, entry_name, _)
    for entry_id, history in per_entry.items():
        for i in range(1, len(history)):
            prev_date, _prev_rank, prev_pts, _, _ = history[i - 1]
            cur_date, cur_rank, cur_pts, user_name, entry_name = history[i]
            if cur_date < today - timedelta(days=MVP_LOOKBACK_DAYS - 1):
                continue
            day_pts = cur_pts - prev_pts
            if day_pts <= 0:
                continue  # zero-points day → not an MVP candidate
            day_scores.setdefault(cur_date, []).append(
                (day_pts, cur_rank, entry_id, user_name, entry_name, "")
            )

    # For each day, pick the MVP: highest day_pts; tie-break = lower current rank
    out: list[DailyMvp] = []
    for d in sorted(day_scores.keys(), reverse=True)[:MVP_LOOKBACK_DAYS]:
        candidates = day_scores[d]
        candidates.sort(key=lambda x: (-x[0], x[1]))
        winner = candidates[0]
        day_pts, cur_rank, entry_id, user_name, entry_name, _ = winner
        # rank_delta: previous day's rank for the winner - cur_rank
        history = per_entry[entry_id]
        prev_rank_for_winner = next(
            (r for cd, r, _, _, _ in history if cd == d - timedelta(days=1)),
            cur_rank,
        )
        out.append(DailyMvp(
            captured_date=d,
            subject_entry_id=entry_id,
            user_name=user_name,
            entry_name=entry_name,
            day_points=day_pts,
            rank_delta=prev_rank_for_winner - cur_rank,
        ))
    return out
```

- [ ] **Step 4: Run the MVP tests**

```bash
docker-compose exec -T backend pytest backend/tests/test_dashboard_stats.py -k daily_mvps -v
```

Expected: all 5 daily-MVP tests PASS.

- [ ] **Step 5: Wire the endpoint**

Replace the `daily_mvps` stub body in `api/leaderboard.py`:

```python
@router.get("/daily-mvps", response_model=DailyMvpsResponse)
async def daily_mvps(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DailyMvpsResponse:
    from app.services.dashboard_stats import compute_daily_mvps
    raw = await compute_daily_mvps(session)
    return DailyMvpsResponse(
        mvps=[
            DailyMvp(
                captured_date=m.captured_date,
                subject_entry_id=m.subject_entry_id,
                user_name=m.user_name,
                entry_name=m.entry_name,
                day_points=m.day_points,
                rank_delta=m.rank_delta,
            )
            for m in raw
        ],
        generated_at=utc_now(),
    )
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dashboard_stats.py backend/tests/test_dashboard_stats.py backend/app/api/leaderboard.py
git commit -m "feat(dashboard): daily-mvps service + endpoint"
```

---

### Task 1.3: Personal Trail service + wire endpoint

**Files:**
- Modify: `backend/app/services/dashboard_stats.py` (append function)
- Modify: `backend/app/api/leaderboard.py` (replace stub)
- Modify: `backend/tests/test_dashboard_stats.py` (append tests)

**Why this task:** Returns the requesting user's entries' trails vs pool average. Used by the Personal Trail strip.

- [ ] **Step 1: Append failing tests**

Add to `backend/tests/test_dashboard_stats.py`:

```python
async def test_personal_trail_empty_pre_deadline(session: AsyncSession):
    entries, _ = await _seed_basic_pool(session, deadline_passed=False)
    # Pick an arbitrary user
    from sqlmodel import select
    user = (await session.exec(select(User).where(User.name == "A"))).one()
    result = await compute_personal_trail(session, user_id=str(user.id))
    assert result == []


async def test_personal_trail_returns_user_entries(session: AsyncSession):
    entries, _ = await _seed_basic_pool(session)
    from sqlmodel import select
    user = (await session.exec(select(User).where(User.name == "A"))).one()
    result = await compute_personal_trail(session, user_id=str(user.id))
    assert len(result) >= 1
    # First entry should be the A-entry
    assert any(e.entry_id == str(entries["a"].id) for e in result)


async def test_personal_trail_includes_pool_average(session: AsyncSession):
    """`pool_avg_points` per day should be the mean across all eligible entries that day."""
    entries, _ = await _seed_basic_pool(session)
    from sqlmodel import select
    user = (await session.exec(select(User).where(User.name == "A"))).one()
    result = await compute_personal_trail(session, user_id=str(user.id))
    # On today, snapshots are a=150, b=140, c=145, d=135, e=122; mean = (150+140+145+135+122)/5 = 138.4
    entry_a = next(e for e in result if e.entry_id == str(entries["a"].id))
    today_point = entry_a.points[-1]
    assert today_point.pool_avg_points == pytest.approx(138.4)
    assert today_point.your_points == 150


async def test_personal_trail_current_gap(session: AsyncSession):
    """`current_gap` = your_points - pool_avg_points for today."""
    entries, _ = await _seed_basic_pool(session)
    from sqlmodel import select
    user = (await session.exec(select(User).where(User.name == "A"))).one()
    result = await compute_personal_trail(session, user_id=str(user.id))
    entry_a = next(e for e in result if e.entry_id == str(entries["a"].id))
    # today_gap = 150 - 138.4 = 11.6
    assert entry_a.current_gap == pytest.approx(11.6)
```

- [ ] **Step 2: Run failing tests**

```bash
docker-compose exec -T backend pytest backend/tests/test_dashboard_stats.py -k personal_trail -v
```

Expected: `ImportError: cannot import name 'compute_personal_trail'`.

- [ ] **Step 3: Append the service function**

Append to `backend/app/services/dashboard_stats.py`:

```python
@dataclass
class TrailPoint:
    captured_date: date
    your_points: int
    pool_avg_points: float


@dataclass
class EntryTrail:
    entry_id: str
    entry_name: str
    current_rank: int
    current_gap: float
    points: list[TrailPoint]


async def compute_personal_trail(
    session: AsyncSession, *, user_id: str,
) -> list[EntryTrail]:
    """Returns the requesting user's entries' point trails vs the pool average.

    Empty pre-deadline. One EntryTrail per submitted entry the user owns,
    sorted by current_rank ascending.
    """
    if not await is_phase1_locked(session):
        return []

    today = date.today()
    earliest = today - timedelta(days=29)  # 30 days of history

    # 1. Compute pool-average points per day across all eligible entries
    pool_rows = (
        await session.exec(
            select(
                LeaderboardSnapshot.captured_date,
                func.avg(LeaderboardSnapshot.total_points),
            )
            .where(LeaderboardSnapshot.entry_id.in_(eligible_entry_ids_select()))
            .where(LeaderboardSnapshot.captured_date >= earliest)
            .group_by(LeaderboardSnapshot.captured_date)
        )
    ).all()
    pool_avg_by_date = {d: float(avg) for d, avg in pool_rows}

    # 2. Load the requesting user's entries' snapshots
    user_rows = (
        await session.exec(
            select(
                LeaderboardSnapshot.entry_id,
                LeaderboardSnapshot.captured_date,
                LeaderboardSnapshot.rank,
                LeaderboardSnapshot.total_points,
                PredictionEntry.entry_name,
            )
            .join(PredictionEntry, PredictionEntry.id == LeaderboardSnapshot.entry_id)
            .where(PredictionEntry.user_id == user_id)
            .where(LeaderboardSnapshot.entry_id.in_(eligible_entry_ids_select()))
            .where(LeaderboardSnapshot.captured_date >= earliest)
            .order_by(LeaderboardSnapshot.entry_id, LeaderboardSnapshot.captured_date)
        )
    ).all()

    by_entry: dict[str, EntryTrail] = {}
    for entry_id, captured_date, rank, pts, entry_name in user_rows:
        trail = by_entry.get(str(entry_id))
        if trail is None:
            trail = EntryTrail(
                entry_id=str(entry_id),
                entry_name=entry_name,
                current_rank=rank,
                current_gap=0.0,
                points=[],
            )
            by_entry[str(entry_id)] = trail
        trail.current_rank = rank  # overwritten by newest below
        trail.points.append(TrailPoint(
            captured_date=captured_date,
            your_points=pts,
            pool_avg_points=pool_avg_by_date.get(captured_date, 0.0),
        ))

    # Set current_gap from last point
    for trail in by_entry.values():
        if trail.points:
            last = trail.points[-1]
            trail.current_gap = last.your_points - last.pool_avg_points

    return sorted(by_entry.values(), key=lambda t: t.current_rank)
```

- [ ] **Step 4: Run tests**

```bash
docker-compose exec -T backend pytest backend/tests/test_dashboard_stats.py -k personal_trail -v
```

Expected: all 4 personal-trail tests PASS.

- [ ] **Step 5: Wire the endpoint**

Replace the `personal_trail` stub body:

```python
@router.get("/personal-trail", response_model=PersonalTrailResponse)
async def personal_trail(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PersonalTrailResponse:
    from app.services.dashboard_stats import compute_personal_trail
    raw = await compute_personal_trail(session, user_id=str(user.id))
    return PersonalTrailResponse(
        entries=[
            EntryTrail(
                entry_id=t.entry_id,
                entry_name=t.entry_name,
                current_rank=t.current_rank,
                current_gap=t.current_gap,
                points=[
                    TrailPoint(captured_date=p.captured_date, your_points=p.your_points, pool_avg_points=p.pool_avg_points)
                    for p in t.points
                ],
            )
            for t in raw
        ],
        generated_at=utc_now(),
    )
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dashboard_stats.py backend/tests/test_dashboard_stats.py backend/app/api/leaderboard.py
git commit -m "feat(dashboard): personal-trail service + endpoint"
```

---

### Task 1.4: Pool Distribution service + wire endpoint

**Files:**
- Modify: `backend/app/services/dashboard_stats.py` (append function)
- Modify: `backend/app/api/leaderboard.py` (replace stub)
- Modify: `backend/tests/test_dashboard_stats.py` (append tests)

**Why this task:** Counts entries clustered around the user's points total; surfaces the next-rank-points-away and a server-composed caption.

- [ ] **Step 1: Append failing tests**

Add to `backend/tests/test_dashboard_stats.py`:

```python
async def test_pool_distribution_empty_pre_deadline(session: AsyncSession):
    entries, _ = await _seed_basic_pool(session, deadline_passed=False)
    from sqlmodel import select
    user = (await session.exec(select(User).where(User.name == "A"))).one()
    result = await compute_pool_distribution(session, user_id=str(user.id))
    # Should be empty/zero across all fields
    assert result.user_points == 0


async def test_pool_distribution_bins(session: AsyncSession):
    """User at 150 pts; other points 140, 145, 135, 122 → bins fall around user.
    Window ±5 covers 145, 150, 155 ranges. With sparse pool, widens to ±10."""
    entries, _ = await _seed_basic_pool(session)
    from sqlmodel import select
    user = (await session.exec(select(User).where(User.name == "A"))).one()
    result = await compute_pool_distribution(session, user_id=str(user.id))
    assert result.user_points == 150
    # User's own bin (delta=0) should have count >= 1
    own = [b for b in result.bins if b.points_delta == 0]
    assert own and own[0].count >= 1


async def test_pool_distribution_caption_leader(session: AsyncSession):
    """When user is at #1 (highest points), caption switches."""
    # Seed pool where user is #1
    comp = Competition(name="t", phase1_deadline=utc_now() - timedelta(hours=1), is_phase2_active=False)
    session.add(comp)
    await session.flush()
    today = date.today()
    for label, pts in [("leader", 200), ("second", 180)]:
        u = User(email=f"{label}@t", name=label, is_admin=False)
        session.add(u)
        await session.flush()
        entry = PredictionEntry(
            user_id=u.id, competition_id=comp.id,
            entry_name=label, disabled=False, withdrawn=False,
        )
        session.add(entry)
        await session.flush()
        session.add(PredictionEntryPhase(
            entry_id=entry.id, phase=PhaseStatus.PHASE_1,
            submitted_at=utc_now() - timedelta(days=5),
        ))
        session.add(LeaderboardSnapshot(
            entry_id=entry.id, competition_id=comp.id,
            captured_date=today, rank=1 if label == "leader" else 2,
            total_points=pts,
        ))
    await session.commit()

    from sqlmodel import select
    leader_user = (await session.exec(select(User).where(User.name == "leader"))).one()
    result = await compute_pool_distribution(session, user_id=str(leader_user.id))
    assert result.next_rank_points_away is None
    assert "above" in result.caption.lower() or "leader" in result.caption.lower() or "behind" in result.caption.lower()


async def test_pool_distribution_caption_default(session: AsyncSession):
    entries, _ = await _seed_basic_pool(session)
    from sqlmodel import select
    user = (await session.exec(select(User).where(User.name == "A"))).one()
    result = await compute_pool_distribution(session, user_id=str(user.id))
    assert "entries" in result.caption.lower() or "points" in result.caption.lower()
```

- [ ] **Step 2: Run failing tests**

```bash
docker-compose exec -T backend pytest backend/tests/test_dashboard_stats.py -k pool_distribution -v
```

Expected: `ImportError: cannot import name 'compute_pool_distribution'`.

- [ ] **Step 3: Append the service function**

Append to `backend/app/services/dashboard_stats.py`:

```python
@dataclass
class DistBin:
    points_delta: int
    count: int


@dataclass
class PoolDistributionResult:
    user_points: int
    window_size: int
    bins: list[DistBin]
    next_rank_points_away: int | None
    next_rank_position: int | None
    near_count: int
    caption: str
    generated_at: datetime


DEFAULT_WINDOW = 5
WIDENED_WINDOW = 10
MIN_NEAR_FOR_DEFAULT = 2  # below this we widen


async def compute_pool_distribution(
    session: AsyncSession, *, user_id: str,
) -> PoolDistributionResult:
    """Returns the histogram of entries around the requesting user's points total."""
    if not await is_phase1_locked(session):
        return PoolDistributionResult(
            user_points=0, window_size=DEFAULT_WINDOW, bins=[],
            next_rank_points_away=None, next_rank_position=None,
            near_count=0, caption="", generated_at=utc_now(),
        )

    today = date.today()

    # Load today's eligible-pool ranks+points
    rows = (
        await session.exec(
            select(
                LeaderboardSnapshot.entry_id,
                LeaderboardSnapshot.rank,
                LeaderboardSnapshot.total_points,
                PredictionEntry.user_id,
            )
            .join(PredictionEntry, PredictionEntry.id == LeaderboardSnapshot.entry_id)
            .where(LeaderboardSnapshot.entry_id.in_(eligible_entry_ids_select()))
            .where(LeaderboardSnapshot.captured_date == today)
        )
    ).all()

    user_rows = [r for r in rows if str(r[3]) == user_id]
    if not user_rows:
        return PoolDistributionResult(
            user_points=0, window_size=DEFAULT_WINDOW, bins=[],
            next_rank_points_away=None, next_rank_position=None,
            near_count=0, caption="", generated_at=utc_now(),
        )

    # Use user's best-ranked entry as the anchor
    best = min(user_rows, key=lambda r: r[1])  # (entry_id, rank, points, user_id)
    user_points: int = best[2]
    user_rank: int = best[1]

    all_pts = [r[2] for r in rows]

    # Decide window — try default, widen if too sparse
    def count_in_window(window: int) -> int:
        return sum(1 for p in all_pts if abs(p - user_points) <= window and p != user_points)

    window = DEFAULT_WINDOW
    if count_in_window(window) < MIN_NEAR_FOR_DEFAULT:
        window = WIDENED_WINDOW

    bins_map: dict[int, int] = {}
    for p in all_pts:
        delta = p - user_points
        if abs(delta) <= window:
            bins_map[delta] = bins_map.get(delta, 0) + 1

    bins = sorted(
        (DistBin(points_delta=d, count=c) for d, c in bins_map.items()),
        key=lambda b: b.points_delta,
    )

    # next-rank: smallest positive points-delta above user (someone with more points = better rank)
    higher_deltas = [p - user_points for p in all_pts if p > user_points]
    if higher_deltas:
        next_rank_points_away = min(higher_deltas)
        # next_rank_position = user_rank - 1 (or fewer if multiple entries are tied at that points level)
        ranks_above = [r[1] for r in rows if r[2] > user_points]
        next_rank_position = max(ranks_above) if ranks_above else user_rank - 1
    else:
        next_rank_points_away = None
        next_rank_position = None

    near_count = count_in_window(window)
    caption = _build_caption(
        user_rank=user_rank,
        near_count=near_count,
        window=window,
        next_rank_points_away=next_rank_points_away,
        next_rank_position=next_rank_position,
        tied_with=bins_map.get(0, 1) - 1,
    )

    return PoolDistributionResult(
        user_points=user_points,
        window_size=window,
        bins=bins,
        next_rank_points_away=next_rank_points_away,
        next_rank_position=next_rank_position,
        near_count=near_count,
        caption=caption,
        generated_at=utc_now(),
    )


def _build_caption(
    *, user_rank: int, near_count: int, window: int,
    next_rank_points_away: int | None,
    next_rank_position: int | None,
    tied_with: int,
) -> str:
    """Compose the server-side caption. See spec for the 4 variants."""
    if user_rank == 1 and next_rank_points_away is None:
        # User is the leader
        return f"Nobody within {window} points of you above. You're leading the pool."
    if tied_with > 0:
        return (
            f"You're tied with {tied_with} other "
            f"entr{'y' if tied_with == 1 else 'ies'} at this score. "
            f"{near_count} entries within {window} points."
        )
    if next_rank_points_away is None:
        return f"You're alone at this points total — {near_count} other entries within {window} points."
    return (
        f"{near_count} entries within {window} points of you. "
        f"The next rank is {next_rank_points_away} points away."
    )
```

- [ ] **Step 4: Run tests**

```bash
docker-compose exec -T backend pytest backend/tests/test_dashboard_stats.py -k pool_distribution -v
```

Expected: all 4 pool-distribution tests PASS.

- [ ] **Step 5: Wire the endpoint**

Replace the `pool_distribution` stub body:

```python
@router.get("/pool-distribution", response_model=PoolDistributionResponse)
async def pool_distribution(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PoolDistributionResponse:
    from app.services.dashboard_stats import compute_pool_distribution
    r = await compute_pool_distribution(session, user_id=str(user.id))
    return PoolDistributionResponse(
        user_points=r.user_points,
        window_size=r.window_size,
        bins=[DistBin(points_delta=b.points_delta, count=b.count) for b in r.bins],
        next_rank_points_away=r.next_rank_points_away,
        next_rank_position=r.next_rank_position,
        near_count=r.near_count,
        caption=r.caption,
        generated_at=r.generated_at,
    )
```

- [ ] **Step 6: Run the full dashboard-stats test file**

```bash
docker-compose exec -T backend pytest backend/tests/test_dashboard_stats.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/dashboard_stats.py backend/tests/test_dashboard_stats.py backend/app/api/leaderboard.py
git commit -m "feat(dashboard): pool-distribution service + endpoint"
```

---

## Phase 2: Frontend foundation

### Task 2.1: Types

**Files:**
- Modify: `frontend/src/lib/types/leaderboard.ts`

- [ ] **Step 1: Append the new types**

```typescript
// ---------------------------------------------------------------------------
// Dashboard widget types (2026-06-22 spec)
// ---------------------------------------------------------------------------

export interface DailyMvp {
	captured_date: string;
	subject_entry_id: string;
	user_name: string;
	entry_name: string;
	day_points: number;
	rank_delta: number;
}

export interface DailyMvpsResponse {
	mvps: DailyMvp[];
	generated_at: string;
}

export interface TrailPoint {
	captured_date: string;
	your_points: number;
	pool_avg_points: number;
}

export interface EntryTrail {
	entry_id: string;
	entry_name: string;
	current_rank: number;
	current_gap: number;
	points: TrailPoint[];
}

export interface PersonalTrailResponse {
	entries: EntryTrail[];
	generated_at: string;
}

export interface DistBin {
	points_delta: number;
	count: number;
}

export interface PoolDistributionResponse {
	user_points: number;
	window_size: number;
	bins: DistBin[];
	next_rank_points_away: number | null;
	next_rank_position: number | null;
	near_count: number;
	caption: string;
	generated_at: string;
}
```

- [ ] **Step 2: Type check + commit**

```bash
docker-compose exec -T frontend-dev npm run check
git add frontend/src/lib/types/leaderboard.ts
git commit -m "feat(dashboard): types for widget responses"
```

---

### Task 2.2: API client fetchers

**Files:**
- Modify: `frontend/src/lib/api/leaderboard.ts`

- [ ] **Step 1: Append fetchers**

```typescript
import type {
	DailyMvpsResponse,
	PersonalTrailResponse,
	PoolDistributionResponse,
} from '$lib/types/leaderboard';

export async function getDailyMvps(): Promise<DailyMvpsResponse> {
	const res = await fetch('/api/leaderboard/daily-mvps', { credentials: 'include' });
	if (!res.ok) throw new Error(`daily-mvps ${res.status}`);
	return res.json();
}

export async function getPersonalTrail(): Promise<PersonalTrailResponse> {
	const res = await fetch('/api/leaderboard/personal-trail', { credentials: 'include' });
	if (!res.ok) throw new Error(`personal-trail ${res.status}`);
	return res.json();
}

export async function getPoolDistribution(): Promise<PoolDistributionResponse> {
	const res = await fetch('/api/leaderboard/pool-distribution', { credentials: 'include' });
	if (!res.ok) throw new Error(`pool-distribution ${res.status}`);
	return res.json();
}
```

- [ ] **Step 2: Type check + commit**

```bash
docker-compose exec -T frontend-dev npm run check
git add frontend/src/lib/api/leaderboard.ts
git commit -m "feat(dashboard): API client wrappers for widget endpoints"
```

---

### Task 2.3: Pure helpers + tests

**Files:**
- Modify: `frontend/src/lib/utils/leaderboardV4.ts`
- Modify: `frontend/src/lib/utils/leaderboardV4.test.ts`

- [ ] **Step 1: Append failing tests**

Append to `frontend/src/lib/utils/leaderboardV4.test.ts`:

```typescript
import { composeRankDelta, firstTwoPlusExpand } from './leaderboardV4';

describe('composeRankDelta', () => {
	it('positive: returns ▲ N', () => expect(composeRankDelta(12)).toBe('▲ 12'));
	it('negative: returns ▼ N', () => expect(composeRankDelta(-3)).toBe('▼ 3'));
	it('zero: returns —', () => expect(composeRankDelta(0)).toBe('—'));
});

describe('firstTwoPlusExpand', () => {
	const arr = ['a', 'b', 'c', 'd'];

	it('expanded=false → first 2 + remaining count', () => {
		const r = firstTwoPlusExpand(arr, false);
		expect(r.visible).toEqual(['a', 'b']);
		expect(r.remaining).toBe(2);
	});

	it('expanded=true → all + zero remaining', () => {
		const r = firstTwoPlusExpand(arr, true);
		expect(r.visible).toEqual(arr);
		expect(r.remaining).toBe(0);
	});

	it('≤ 2 items: returns all, zero remaining regardless', () => {
		expect(firstTwoPlusExpand(['x'], false).remaining).toBe(0);
		expect(firstTwoPlusExpand([], false).visible).toEqual([]);
	});
});
```

- [ ] **Step 2: Run failing tests**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/utils/leaderboardV4.test.ts
```

Expected: failures referencing missing exports.

- [ ] **Step 3: Append implementations**

Append to `frontend/src/lib/utils/leaderboardV4.ts`:

```typescript
/** Renders a rank-delta as a string with ▲/▼ glyph. Zero → em-dash. */
export function composeRankDelta(delta: number): string {
	if (delta > 0) return `▲ ${delta}`;
	if (delta < 0) return `▼ ${-delta}`;
	return '—';
}

/** Personal Trail multi-entry helper — show first 2 entries by default,
 *  with a "+N more" link to expand. */
export function firstTwoPlusExpand<T>(items: T[], expanded: boolean): { visible: T[]; remaining: number } {
	if (expanded || items.length <= 2) {
		return { visible: items, remaining: 0 };
	}
	return { visible: items.slice(0, 2), remaining: items.length - 2 };
}
```

- [ ] **Step 4: Run tests + commit**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/utils/leaderboardV4.test.ts
git add frontend/src/lib/utils/leaderboardV4.ts frontend/src/lib/utils/leaderboardV4.test.ts
git commit -m "feat(dashboard): composeRankDelta + firstTwoPlusExpand pure helpers"
```

---

## Phase 3: Frontend components

### Task 3.1: `MvpChip.svelte`

**Files:**
- Create: `frontend/src/lib/components/dashboard/v4/MvpChip.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
	import type { DailyMvp } from '$lib/types/leaderboard';
	import { composeRankDelta } from '$lib/utils/leaderboardV4';
	import { createEventDispatcher } from 'svelte';

	export let mvp: DailyMvp;
	export let isToday: boolean = false;

	const dispatch = createEventDispatcher<{ open: { entry_id: string } }>();

	$: dateLabel = isToday
		? `Today · ${formatShort(mvp.captured_date)}`
		: formatShort(mvp.captured_date);

	function formatShort(iso: string): string {
		const d = new Date(iso + 'T00:00:00Z');
		return d.toLocaleDateString('en-GB', { month: 'short', day: 'numeric', timeZone: 'UTC' });
	}
</script>

<button
	type="button"
	class="flex-[1_1_200px] min-w-[180px] rounded-box border bg-base-100 p-3 text-left
		   hover:border-primary/50 transition-colors
		   {isToday ? 'border-primary/40 bg-primary/15' : 'border-base-300'}"
	on:click={() => dispatch('open', { entry_id: mvp.subject_entry_id })}
>
	<div class="text-[11px] font-bold tracking-wide uppercase text-base-content/40">{dateLabel}</div>
	<div class="mt-1 mb-0.5 text-sm font-bold">{mvp.user_name}</div>
	<div class="flex gap-3 text-xs text-base-content/55">
		<span><span class="text-success font-bold">+{mvp.day_points}</span> pts</span>
		<span class={mvp.rank_delta < 0 ? 'text-error font-bold' : 'text-primary font-bold'}>
			{composeRankDelta(mvp.rank_delta)}
		</span>
	</div>
</button>
```

- [ ] **Step 2: Type check + commit**

```bash
docker-compose exec -T frontend-dev npm run check
git add frontend/src/lib/components/dashboard/v4/MvpChip.svelte
git commit -m "feat(dashboard): MvpChip presentation component"
```

---

### Task 3.2: `DailyMvpStrip.svelte`

**Files:**
- Create: `frontend/src/lib/components/dashboard/v4/DailyMvpStrip.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
	import { onMount, createEventDispatcher } from 'svelte';
	import { getDailyMvps } from '$lib/api/leaderboard';
	import type { DailyMvp } from '$lib/types/leaderboard';
	import MvpChip from './MvpChip.svelte';

	const dispatch = createEventDispatcher<{ open: { entry_id: string } }>();

	let mvps: DailyMvp[] = [];
	let loading = true;
	let failed = false;

	function todayIso(): string {
		return new Date().toISOString().slice(0, 10);
	}

	onMount(async () => {
		try {
			const data = await getDailyMvps();
			mvps = data.mvps;
		} catch {
			failed = true;
		} finally {
			loading = false;
		}
	});

	$: today = todayIso();
</script>

{#if !loading && !failed && mvps.length > 0}
	<section class="rounded-box border border-base-300 bg-base-200 p-4">
		<header class="mb-3 flex items-center gap-2">
			<h3 class="m-0 text-xs font-bold uppercase tracking-wide text-primary">Daily MVP — last 5 days</h3>
		</header>
		<div class="flex flex-wrap gap-2.5">
			{#each mvps as mvp (mvp.captured_date)}
				<MvpChip
					{mvp}
					isToday={mvp.captured_date === today}
					on:open={e => dispatch('open', e.detail)}
				/>
			{/each}
		</div>
	</section>
{/if}
```

- [ ] **Step 2: Type check + commit**

```bash
docker-compose exec -T frontend-dev npm run check
git add frontend/src/lib/components/dashboard/v4/DailyMvpStrip.svelte
git commit -m "feat(dashboard): DailyMvpStrip container with collapse-on-empty"
```

---

### Task 3.3: `PersonalTrailStrip.svelte`

**Files:**
- Create: `frontend/src/lib/components/dashboard/v4/PersonalTrailStrip.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { getPersonalTrail } from '$lib/api/leaderboard';
	import type { EntryTrail } from '$lib/types/leaderboard';
	import { firstTwoPlusExpand } from '$lib/utils/leaderboardV4';

	let entries: EntryTrail[] = [];
	let loading = true;
	let expanded = false;

	onMount(async () => {
		try {
			const data = await getPersonalTrail();
			entries = data.entries;
		} catch {
			entries = [];
		} finally {
			loading = false;
		}
	});

	$: split = firstTwoPlusExpand(entries, expanded);

	function pathFor(points: EntryTrail['points'], getter: (p: any) => number, w = 800, h = 90): string {
		if (points.length === 0) return '';
		const ys = points.map(getter);
		const min = Math.min(...ys);
		const max = Math.max(...ys);
		const range = Math.max(1, max - min);
		return points
			.map((p, i) => {
				const x = (i / Math.max(1, points.length - 1)) * w;
				const y = h - 5 - ((getter(p) - min) / range) * (h - 10);
				return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
			})
			.join(' ');
	}
</script>

{#if !loading && entries.length > 0}
	<section class="rounded-box border border-base-300 bg-base-200 p-4">
		<header class="mb-3 flex items-center gap-2">
			<h3 class="m-0 text-xs font-bold uppercase tracking-wide text-primary">Your Trail — points vs pool average</h3>
		</header>

		<div class="flex flex-col gap-3">
			{#each split.visible as t (t.entry_id)}
				<div class="grid grid-cols-1 md:grid-cols-[1fr_2.5fr_0.8fr] gap-4 items-center">
					<div>
						<div class="font-bold text-sm">{t.entry_name}</div>
						<div class="text-xs text-base-content/40 mt-0.5">#{t.current_rank} · last 30 days</div>
					</div>
					<div>
						{#if t.points.length < 3}
							<div class="text-xs text-base-content/40 italic py-4">It's early — check back tomorrow.</div>
						{:else}
							<svg viewBox="0 0 800 90" class="w-full block">
								<path d={pathFor(t.points, p => p.pool_avg_points)} stroke="currentColor" stroke-width="2.5" fill="none" class="text-base-content/30" />
								<path d={pathFor(t.points, p => p.your_points)} stroke="currentColor" stroke-width="3.5" fill="none" class="text-primary" />
							</svg>
						{/if}
					</div>
					<div class="text-right">
						<div class="font-display text-2xl font-extrabold leading-none {t.current_gap >= 0 ? 'text-success' : 'text-error'}">
							{t.current_gap >= 0 ? '+' : ''}{Math.round(t.current_gap)}
						</div>
						<div class="text-[10px] uppercase tracking-wide text-base-content/40 mt-1">vs pool avg</div>
					</div>
				</div>
			{/each}

			{#if split.remaining > 0 && !expanded}
				<button type="button" class="text-xs text-primary self-start hover:underline" on:click={() => (expanded = true)}>
					+{split.remaining} more {split.remaining === 1 ? 'entry' : 'entries'}
				</button>
			{/if}
			{#if expanded && entries.length > 2}
				<button type="button" class="text-xs text-base-content/55 self-start hover:underline" on:click={() => (expanded = false)}>
					Show less
				</button>
			{/if}
		</div>
	</section>
{/if}
```

- [ ] **Step 2: Type check + commit**

```bash
docker-compose exec -T frontend-dev npm run check
git add frontend/src/lib/components/dashboard/v4/PersonalTrailStrip.svelte
git commit -m "feat(dashboard): PersonalTrailStrip with first-2-plus-expand"
```

---

### Task 3.4: `PoolDistribution.svelte`

**Files:**
- Create: `frontend/src/lib/components/dashboard/v4/PoolDistribution.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { getPoolDistribution } from '$lib/api/leaderboard';
	import type { PoolDistributionResponse } from '$lib/types/leaderboard';

	let data: PoolDistributionResponse | null = null;
	let loading = true;

	onMount(async () => {
		try {
			data = await getPoolDistribution();
			if (data.user_points === 0 && data.bins.length === 0) data = null; // pre-deadline / no entries
		} catch {
			data = null;
		} finally {
			loading = false;
		}
	});

	const W = 1080;
	const H = 150;
	const PAD_X = 20;

	$: chartGeom = data ? buildChartGeom(data) : null;

	function buildChartGeom(d: PoolDistributionResponse) {
		const totalBins = d.window_size * 2 + 1;
		const usable = W - PAD_X * 2;
		const binWidth = usable / totalBins;
		const maxCount = Math.max(1, ...d.bins.map(b => b.count));
		const baseY = H - 30;
		const topY = 35;
		const bars = d.bins.map(b => {
			const x = PAD_X + (b.points_delta + d.window_size) * binWidth + binWidth * 0.1;
			const h = ((b.count / maxCount) * (baseY - topY));
			return {
				x,
				y: baseY - h,
				width: binWidth * 0.8,
				height: h,
				delta: b.points_delta,
			};
		});
		const userX = PAD_X + d.window_size * binWidth + binWidth * 0.5;
		const nextRankX = d.next_rank_points_away != null
			? PAD_X + (d.next_rank_points_away + d.window_size) * binWidth + binWidth * 0.5
			: null;
		return { bars, userX, nextRankX, baseY, topY };
	}
</script>

{#if !loading && data && chartGeom}
	<section class="rounded-box border border-base-300 bg-base-200 p-4">
		<header class="mb-3 flex items-center gap-2">
			<h3 class="m-0 text-xs font-bold uppercase tracking-wide text-primary">Pool Distribution</h3>
		</header>
		<p class="m-0 mb-2 text-sm text-base-content/55">{data.caption}</p>
		<svg viewBox="0 0 {W} {H}" class="w-full block">
			<line x1={PAD_X} y1={chartGeom.baseY} x2={W - PAD_X} y2={chartGeom.baseY} stroke="currentColor" stroke-opacity="0.18" stroke-width="1" />
			{#each chartGeom.bars as bar (bar.delta)}
				{@const isUser = bar.delta === 0}
				{@const isNear = Math.abs(bar.delta) <= 2 && !isUser}
				<rect
					x={bar.x}
					y={bar.y}
					width={bar.width}
					height={bar.height}
					class={isUser ? 'fill-primary' : isNear ? 'fill-primary/40' : 'fill-base-content/15'}
				/>
			{/each}
			<line x1={chartGeom.userX} y1={14} x2={chartGeom.userX} y2={chartGeom.topY - 2} stroke="currentColor" stroke-width="1.5" class="text-primary" />
			<text x={chartGeom.userX} y={11} text-anchor="middle" font-size="11" font-weight="700" class="fill-primary">YOU</text>
			{#if chartGeom.nextRankX != null && data.next_rank_position != null}
				<line x1={chartGeom.nextRankX} y1={22} x2={chartGeom.nextRankX} y2={chartGeom.topY + 14} stroke="currentColor" stroke-width="1.2" stroke-dasharray="3 3" class="text-success" />
				<text x={chartGeom.nextRankX} y={18} text-anchor="middle" font-size="11" font-weight="600" class="fill-success">#{data.next_rank_position}</text>
			{/if}
			<text x={PAD_X} y={H - 10} font-size="11" class="fill-base-content/40">−{data.window_size}pt</text>
			<text x={W / 2} y={H - 10} text-anchor="middle" font-size="11" font-weight="700" class="fill-base-content/40">YOU</text>
			<text x={W - PAD_X} y={H - 10} text-anchor="end" font-size="11" class="fill-base-content/40">+{data.window_size}pt</text>
		</svg>
	</section>
{/if}
```

- [ ] **Step 2: Type check + commit**

```bash
docker-compose exec -T frontend-dev npm run check
git add frontend/src/lib/components/dashboard/v4/PoolDistribution.svelte
git commit -m "feat(dashboard): PoolDistribution histogram"
```

---

## Phase 4: Integration

### Task 4.1: Mount the new region in `DashboardV4.svelte`

**Files:**
- Modify: `frontend/src/lib/components/dashboard/v4/DashboardV4.svelte`

- [ ] **Step 1: Add imports**

In the `<script lang="ts">` block, add:

```typescript
import DailyMvpStrip from './DailyMvpStrip.svelte';
import PersonalTrailStrip from './PersonalTrailStrip.svelte';
import PoolDistribution from './PoolDistribution.svelte';
```

- [ ] **Step 2: Add a drawer-open handler (if not already present)**

If the dashboard already has an `openDrawer` function (e.g. for clicking a MiniLeaderboard row), reuse it. Otherwise add:

```typescript
function openDrawer(entryId: string) {
	// hook into the existing entry-detail surface the dashboard uses;
	// if no drawer is present, navigate to /leaderboard?entry=<id>
	location.href = `/leaderboard?entry=${entryId}`;
}
```

- [ ] **Step 3: Append the new region**

At [DashboardV4.svelte:229](frontend/src/lib/components/dashboard/v4/DashboardV4.svelte:229), after the closing `</div>` of the two-column grid, insert:

```svelte
		<!-- ============ NEW: dashboard widgets region (2026-06-22) ============ -->
		<div class="my-5 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent opacity-60"></div>
		<div class="flex flex-col gap-4">
			<DailyMvpStrip on:open={e => openDrawer(e.detail.entry_id)} />
			<PersonalTrailStrip />
			<PoolDistribution />
		</div>
```

- [ ] **Step 4: Type check**

```bash
docker-compose exec -T frontend-dev npm run check
```

Expected: 0 errors.

- [ ] **Step 5: Visual smoke-test in browser**

```bash
docker-compose restart frontend-dev
```

Open `http://localhost:5173`, sign in as admin, verify:
- Existing dashboard (header, grid, mini-leaderboard, movers) renders unchanged
- Below the grid: thin gold divider line
- Below the divider: Daily MVP strip (or hidden if no qualifying days)
- Personal Trail strip (or hidden if no entries)
- Pool Distribution histogram (or hidden if pre-deadline)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/components/dashboard/v4/DashboardV4.svelte
git commit -m "feat(dashboard): mount widgets region below existing grid"
```

---

## Phase 5: Ship

### Task 5.1: Run all tests + type check

- [ ] **Step 1: Backend pytest**

```bash
docker-compose exec -T backend pytest backend/tests/test_dashboard_stats.py -v
```

Expected: all PASS.

- [ ] **Step 2: Frontend vitest**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/utils/leaderboardV4.test.ts
```

Expected: all PASS, including `composeRankDelta` and `firstTwoPlusExpand` cases.

- [ ] **Step 3: Type check**

```bash
docker-compose exec -T frontend-dev npm run check
```

Expected: 0 errors. Existing warnings tolerated.

---

### Task 5.2: Mobile verification

- [ ] **Step 1: Open Chrome DevTools, viewport 375×812**

Visit `/`, sign in.

- [ ] **Step 2: Visual checklist**

- Daily MVP chips wrap to 2-3 rows (not horizontal scroll)
- Personal Trail stacks vertically (identity row, sparkline, stat row)
- Pool Distribution bars don't crush; caption still readable
- Whole new region sits cleanly below the existing dashboard

---

### Task 5.3: Combined version bump (shared with race redesign)

The race-redesign plan owns the version bump. This plan does NOT add an additional version bump — both feature sets ship under one version.

The race-redesign plan's changelog entry should be amended to also mention these widgets. Edit `frontend/src/lib/data/changelog.json` after the version bump task in the race-redesign plan completes:

```json
{
	"version": "X.Y.Z",
	"date": "2026-06-22",
	"type": "feature",
	"summary": "Leaderboard 'The Race' tab redesigned with story cards, neighbourhood chart and cohort race. Dashboard gains three new widgets below the existing grid: Daily MVP, Personal Trail, and Pool Distribution.",
	"commit": "pending"
}
```

- [ ] **Step 1: Patch the changelog summary**

After the race-redesign plan's version-bump task completes, update the just-added changelog entry's `summary` field to the combined text above.

```bash
git add frontend/src/lib/data/changelog.json
git commit -m "chore(changelog): combine race redesign + dashboard widgets summary"
```

---

### Task 5.4: PR + deploy + verify

Both feature sets share a single PR. The race-redesign plan's Phase 5 covers the PR open. After merge, verify both surfaces on prod:

- `/leaderboard` → Race tab: 5 regions render
- `/` (dashboard): below the existing grid, 3 widgets render
- Cross-check that nothing in the existing dashboard grid moved

If anything is off, decide whether to revert via `V4_LEADERBOARD_ENABLED = false` (race side) or remove the widget-region block from `DashboardV4.svelte` (dashboard side) — they're independent rollbacks even though they share a PR.

---

## Self-Review Notes

**Spec coverage:** every section in [`2026-06-22-dashboard-widgets-design.md`](../specs/2026-06-22-dashboard-widgets-design.md) maps to a task:
- Daily MVP widget → Task 1.2 (backend) + Task 3.1, 3.2 (frontend)
- Personal Trail widget → Task 1.3 (backend) + Task 3.3 (frontend)
- Pool Distribution widget → Task 1.4 (backend) + Task 3.4 (frontend)
- Architecture (types + API client + helpers) → Phase 2
- Integration (DashboardV4 mount) → Task 4.1
- Versioning (combined with race redesign) → Task 5.3
- Mobile + edge cases → Task 5.2 manual + per-component code

**Known v1 limitations** documented in the spec's "Out of scope" section — no follow-up tasks needed here.
