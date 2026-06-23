"""Race-story derivations for the /leaderboard race-tab story cards.

The first three candidates (biggest_climb, steepest_fall, hottest_streak)
are independent — any/all may fire. The 4th slot is filled by the first
candidate from a fallback chain (phoenix > slow_burn > steady_hand) that
qualifies, so the slot is almost never empty.

All datetimes returned are aware-UTC. Eligible entries only.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LeaderboardSnapshot, PredictionEntry, User
from app.services.locking import is_phase1_locked
from app.services.scoring import eligible_entry_ids_select


# How far back to look for the various qualifications.
WINDOW_DAYS_CLIMB_FALL = 3
WINDOW_DAYS_STREAK = 5  # min streak length

# Thresholds.
MIN_CLIMB_DELTA = 15
MIN_FALL_DELTA = 15
TOP_50_CAP = 50  # climber must currently be in top 50
TOP_25_START_CAP = 25  # faller must have been in top 25 at window start

# Phoenix: must have fallen at least this many ranks at some point AND
# now be within RECOVERY of where they started.
PHOENIX_MIN_DROP = 15
PHOENIX_RECOVERY_BAND = 5

# Slow burn: must have gained at least this many ranks over the window
# AND never had a single-day drop worse than this.
SLOW_BURN_MIN_GAIN = 10
SLOW_BURN_MAX_BAD_DAY = 3

# Steady hand: must currently be at or better than this rank, with the
# smallest population-stdev across the visible window.
STEADY_HAND_CURRENT_CAP = 15

StoryKind = Literal[
    "biggest_climb",
    "steepest_fall",
    "hottest_streak",
    "phoenix",
    "slow_burn",
    "steady_hand",
]


@dataclass
class SparklinePoint:
    captured_date: date
    rank: int


@dataclass
class RaceStory:
    kind: StoryKind
    title: str
    caption: str
    subject_entry_id: str
    compare_entry_id: str | None
    sparkline: list[SparklinePoint]
    compare_sparkline: list[SparklinePoint] | None


async def select_race_stories(session: AsyncSession) -> list[RaceStory]:
    """Compute the 0-4 qualifying race-story cards in display order.

    Returns [] pre-deadline (blind-pool) and when no card qualifies.
    """
    if not await is_phase1_locked(session):
        return []

    trail = await _load_recent_snapshots(session)
    if not trail:
        return []

    stories: list[RaceStory] = []
    # First three slots: independent qualifiers — any/all fire.
    for candidate in (
        _try_biggest_climb,
        _try_steepest_fall,
        _try_hottest_streak,
    ):
        story = candidate(trail)
        if story is not None:
            stories.append(story)
    # Fourth slot: fallback chain — phoenix is the most dramatic but
    # the rarest. Slow_burn fills the patient-climber niche. Steady_hand
    # is the always-something default: somebody always has the lowest
    # stdev within the top-15 cap.
    for fallback in (_try_phoenix, _try_slow_burn, _try_steady_hand):
        story = fallback(trail)
        if story is not None:
            stories.append(story)
            break
    return stories


@dataclass
class EntryTrail:
    entry_id: str
    entry_name: str
    user_name: str
    # ordered oldest->newest
    points: list[SparklinePoint]
    # quick lookups
    current_rank: int
    rank_n_days_ago: dict[int, int]  # 0 = today (most recent), 3 = three days ago, ...


async def _load_recent_snapshots(session: AsyncSession) -> list[EntryTrail]:
    """Load the last 14 days of snapshots for all eligible entries.

    Returned trails are sorted by current_rank ascending.
    """
    today = date.today()
    earliest = today - timedelta(days=13)

    result = await session.execute(
        select(
            LeaderboardSnapshot.entry_id,
            LeaderboardSnapshot.captured_date,
            LeaderboardSnapshot.position,
            LeaderboardSnapshot.total_points,
            PredictionEntry.display_name,
            User.name,
        )
        .join(PredictionEntry, PredictionEntry.id == LeaderboardSnapshot.entry_id)
        .join(User, User.id == PredictionEntry.user_id)
        .where(LeaderboardSnapshot.entry_id.in_(eligible_entry_ids_select()))
        .where(LeaderboardSnapshot.captured_date >= earliest)
        .order_by(LeaderboardSnapshot.entry_id, LeaderboardSnapshot.captured_date)
    )
    rows = result.all()

    by_entry: dict[str, EntryTrail] = {}
    for entry_id, captured_date, position, _pts, display_name, user_name in rows:
        trail = by_entry.get(str(entry_id))
        if trail is None:
            trail = EntryTrail(
                entry_id=str(entry_id),
                entry_name=display_name,
                user_name=user_name or display_name,
                points=[],
                current_rank=position,  # overwritten by newest below
                rank_n_days_ago={},
            )
            by_entry[str(entry_id)] = trail
        trail.points.append(SparklinePoint(captured_date=captured_date, rank=position))

    # Populate current_rank from newest point and rank_n_days_ago lookup
    for trail in by_entry.values():
        if trail.points:
            trail.current_rank = trail.points[-1].rank
            newest_date = trail.points[-1].captured_date
            for p in trail.points:
                days_ago = (newest_date - p.captured_date).days
                trail.rank_n_days_ago[days_ago] = p.rank

    return sorted(by_entry.values(), key=lambda t: t.current_rank)


def _label(trail: EntryTrail) -> str:
    """Frontend-style display name. Mirrors `rowDisplayName` in leaderboardV4.ts."""
    return trail.user_name  # entries grouped per-user in this simple form


def _try_biggest_climb(trails: list[EntryTrail]) -> RaceStory | None:
    """Largest 3-day rank delta upward. Currently top-50, moved >= 15."""
    best: tuple[int, EntryTrail] | None = None  # (delta, trail)
    for t in trails:
        if t.current_rank > TOP_50_CAP:
            continue
        past = t.rank_n_days_ago.get(WINDOW_DAYS_CLIMB_FALL)
        if past is None:
            continue
        delta = past - t.current_rank  # positive = climbed
        if delta < MIN_CLIMB_DELTA:
            continue
        if best is None or delta > best[0] or (delta == best[0] and t.current_rank < best[1].current_rank):
            best = (delta, t)
    if best is None:
        return None
    delta, t = best
    return RaceStory(
        kind="biggest_climb",
        title=f"{_label(t)} — up {delta}",
        caption=f"From #{t.rank_n_days_ago[WINDOW_DAYS_CLIMB_FALL]} to #{t.current_rank} in {WINDOW_DAYS_CLIMB_FALL} days.",
        subject_entry_id=t.entry_id,
        compare_entry_id=None,
        sparkline=t.points[-7:],  # last 7 days
        compare_sparkline=None,
    )


def _try_steepest_fall(trails: list[EntryTrail]) -> RaceStory | None:
    """Largest 3-day rank delta downward. Was top-25 at window start, fell >= 15."""
    worst: tuple[int, EntryTrail] | None = None
    for t in trails:
        past = t.rank_n_days_ago.get(WINDOW_DAYS_CLIMB_FALL)
        if past is None or past > TOP_25_START_CAP:
            continue
        delta = t.current_rank - past
        if delta < MIN_FALL_DELTA:
            continue
        if worst is None or delta > worst[0] or (delta == worst[0] and t.current_rank < worst[1].current_rank):
            worst = (delta, t)
    if worst is None:
        return None
    delta, t = worst
    return RaceStory(
        kind="steepest_fall",
        title=f"{_label(t)} — down {delta}",
        caption=f"Held #{t.rank_n_days_ago[WINDOW_DAYS_CLIMB_FALL]} {WINDOW_DAYS_CLIMB_FALL} days ago; now #{t.current_rank}.",
        subject_entry_id=t.entry_id,
        compare_entry_id=None,
        sparkline=t.points[-7:],
        compare_sparkline=None,
    )


def _try_closest_race(trails: list[EntryTrail]) -> RaceStory | None:
    """#1 and #2 within 5 points AND traded the lead at least once in 7 days."""
    if len(trails) < 2:
        return None
    leader = trails[0]
    runner = trails[1]
    if leader.current_rank != 1 or runner.current_rank != 2:
        return None
    # Look at last 7 days — did the lead change hands at least once?
    days_to_check = min(WINDOW_DAYS_CLOSEST, len(leader.points), len(runner.points))
    leader_ranks = [p.rank for p in leader.points[-days_to_check:]]
    runner_ranks = [p.rank for p in runner.points[-days_to_check:]]
    trades = sum(
        1
        for a, b in zip(leader_ranks, runner_ranks)
        if (a == 2 and b == 1) or (a == 1 and b == 2)
    )
    if trades < 1:
        return None
    # Gap check uses points trail — re-query by points instead of rank
    # (rank is what we have; points are accessible via total_points — we need to
    # re-query just for the leader/runner if we want exact gap; for the qualification
    # threshold we approximate as: if rank-swap happened, they're close)
    # NOTE: simplified — exact gap not enforced in code, qualification proxy is
    # the rank-swap. Title states the swap count.
    return RaceStory(
        kind="closest_race",
        title=f"{_label(leader)} vs {_label(runner)}",
        caption=f"Have traded the lead {trades} times in the last {WINDOW_DAYS_CLOSEST} days.",
        subject_entry_id=leader.entry_id,
        compare_entry_id=runner.entry_id,
        sparkline=leader.points[-WINDOW_DAYS_CLOSEST:],
        compare_sparkline=runner.points[-WINDOW_DAYS_CLOSEST:],
    )


def _try_hottest_streak(trails: list[EntryTrail]) -> RaceStory | None:
    """Longest unbroken run in the top 5. Skipped if the only qualifier is the leader holding #1 every day."""
    best: tuple[int, EntryTrail] | None = None  # (streak_len, trail)
    for t in trails:
        # Count current run of top-5 placements working backwards
        streak = 0
        for p in reversed(t.points):
            if p.rank <= 5:
                streak += 1
            else:
                break
        if streak < WINDOW_DAYS_STREAK:
            continue
        # Skip the leader-only-at-#1 boring case
        if all(p.rank == 1 for p in t.points[-streak:]):
            continue
        if best is None or streak > best[0] or (streak == best[0] and t.current_rank < best[1].current_rank):
            best = (streak, t)
    if best is None:
        return None
    streak, t = best
    return RaceStory(
        kind="hottest_streak",
        title=f"{_label(t)} — {streak} days in top 5",
        caption=f"Hasn't dropped below #5 in {streak} consecutive days.",
        subject_entry_id=t.entry_id,
        compare_entry_id=None,
        sparkline=t.points[-7:],
        compare_sparkline=None,
    )


def _try_phoenix(trails: list[EntryTrail]) -> RaceStory | None:
    """Comeback story: dropped >= PHOENIX_MIN_DROP at some point in the
    visible window AND has since recovered to within PHOENIX_RECOVERY_BAND
    of their starting rank. Pick the deepest fall — the most dramatic
    recovery wins. The U-shape sparkline visually carries the narrative."""
    best: tuple[int, EntryTrail] | None = None  # (drop_depth, trail)
    for t in trails:
        if len(t.points) < 5:
            continue
        ranks = [p.rank for p in t.points]
        start_rank = ranks[0]
        current_rank = ranks[-1]
        worst_rank = max(ranks)  # higher number = worse rank
        drop_depth = worst_rank - start_rank
        recovery_gap = abs(current_rank - start_rank)
        if drop_depth < PHOENIX_MIN_DROP:
            continue
        if recovery_gap > PHOENIX_RECOVERY_BAND:
            continue
        if best is None or drop_depth > best[0]:
            best = (drop_depth, t)
    if best is None:
        return None
    drop_depth, t = best
    climbed_back = max(p.rank for p in t.points) - t.current_rank
    return RaceStory(
        kind="phoenix",
        title=f"{_label(t)} — comeback",
        caption=f"Fell {drop_depth}, climbed {climbed_back} back since.",
        subject_entry_id=t.entry_id,
        compare_entry_id=None,
        sparkline=t.points,
        compare_sparkline=None,
    )


def _try_slow_burn(trails: list[EntryTrail]) -> RaceStory | None:
    """Patient climber: rank improved by >= SLOW_BURN_MIN_GAIN over the
    window AND no single-day drop worse than SLOW_BURN_MAX_BAD_DAY.
    Pick the biggest gain. Gentle uphill sparkline."""
    best: tuple[int, EntryTrail] | None = None  # (gain, trail)
    for t in trails:
        if len(t.points) < 5:
            continue
        ranks = [p.rank for p in t.points]
        gain = ranks[0] - ranks[-1]  # positive = improved (lower rank number)
        if gain < SLOW_BURN_MIN_GAIN:
            continue
        had_bad_day = False
        for i in range(1, len(ranks)):
            day_change = ranks[i] - ranks[i - 1]  # positive = rank got worse
            if day_change > SLOW_BURN_MAX_BAD_DAY:
                had_bad_day = True
                break
        if had_bad_day:
            continue
        if best is None or gain > best[0]:
            best = (gain, t)
    if best is None:
        return None
    gain, t = best
    days_span = len(t.points) - 1
    return RaceStory(
        kind="slow_burn",
        title=f"{_label(t)} — climbing steadily",
        caption=f"Up {gain} places over {days_span} days without a single bad day.",
        subject_entry_id=t.entry_id,
        compare_entry_id=None,
        sparkline=t.points,
        compare_sparkline=None,
    )


def _try_steady_hand(trails: list[EntryTrail]) -> RaceStory | None:
    """Currently inside STEADY_HAND_CURRENT_CAP and the smallest
    population-stdev across the window. The flat sparkline IS the story —
    consistency, not drama."""
    candidates: list[tuple[float, EntryTrail]] = []
    for t in trails:
        if t.current_rank > STEADY_HAND_CURRENT_CAP:
            continue
        if len(t.points) < 5:
            continue
        ranks = [p.rank for p in t.points]
        candidates.append((statistics.pstdev(ranks), t))
    if not candidates:
        return None
    # Smallest stdev wins; ties broken by best current rank.
    candidates.sort(key=lambda x: (x[0], x[1].current_rank))
    _stdev, t = candidates[0]
    worst_rank = max(p.rank for p in t.points)
    days_span = len(t.points) - 1
    return RaceStory(
        kind="steady_hand",
        title=f"{_label(t)} — steady hand",
        caption=f"Hasn't ranked worse than #{worst_rank} in {days_span} days.",
        subject_entry_id=t.entry_id,
        compare_entry_id=None,
        sparkline=t.points,
        compare_sparkline=None,
    )
