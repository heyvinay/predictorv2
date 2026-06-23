"""Dashboard widget derivations — daily MVPs, personal trail, pool distribution.

All three read from LeaderboardSnapshot and respect the blind-pool gate.
Datetimes are aware-UTC; dates are plain `date`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    entry_name: str  # API-facing label; sourced from PredictionEntry.display_name
    day_points: int
    rank_delta: int


async def compute_daily_mvps(session: AsyncSession) -> list[DailyMvp]:
    """Returns up to 5 daily MVPs, newest-first. Empty pre-deadline."""
    if not await is_phase1_locked(session):
        return []

    today = date.today()
    # Need one extra day before the lookback window so the earliest in-window
    # day can compare against its prior-day snapshot.
    earliest = today - timedelta(days=MVP_LOOKBACK_DAYS + 1)

    rows = (
        await session.execute(
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
    ).all()

    # Group rows by entry_id, preserving captured_date order from the SQL ORDER BY.
    per_entry: dict[str, list[tuple[date, int, int, str, str]]] = {}
    for entry_id, captured_date, position, pts, display_name, user_name in rows:
        per_entry.setdefault(str(entry_id), []).append(
            (captured_date, position, pts, user_name or "", display_name or "")
        )

    # Build per-day score lists by diffing consecutive snapshots.
    # tuple: (day_points, current_rank, entry_id, user_name, display_name)
    day_scores: dict[date, list[tuple[int, int, str, str, str]]] = {}
    for entry_id, history in per_entry.items():
        for i in range(1, len(history)):
            _prev_date, _prev_rank, prev_pts, _, _ = history[i - 1]
            cur_date, cur_rank, cur_pts, user_name, display_name = history[i]
            if cur_date < today - timedelta(days=MVP_LOOKBACK_DAYS - 1):
                continue
            day_pts = cur_pts - prev_pts
            if day_pts <= 0:
                continue
            day_scores.setdefault(cur_date, []).append(
                (day_pts, cur_rank, entry_id, user_name, display_name)
            )

    out: list[DailyMvp] = []
    for d in sorted(day_scores.keys(), reverse=True)[:MVP_LOOKBACK_DAYS]:
        candidates = day_scores[d]
        # Highest day_points; tie-break by lower rank number (better position).
        candidates.sort(key=lambda x: (-x[0], x[1]))
        winner = candidates[0]
        day_pts, cur_rank, entry_id, user_name, display_name = winner
        history = per_entry[entry_id]
        prev_rank_for_winner = next(
            (r for cd, r, _, _, _ in history if cd == d - timedelta(days=1)),
            cur_rank,
        )
        out.append(
            DailyMvp(
                captured_date=d,
                subject_entry_id=entry_id,
                user_name=user_name,
                entry_name=display_name,
                day_points=day_pts,
                rank_delta=prev_rank_for_winner - cur_rank,
            )
        )
    return out


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

    # Coerce string user_id to UUID so SQLAlchemy's UUID type binding works.
    user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

    pool_rows = (
        await session.execute(
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

    user_rows = (
        await session.execute(
            select(
                LeaderboardSnapshot.entry_id,
                LeaderboardSnapshot.captured_date,
                LeaderboardSnapshot.position,
                LeaderboardSnapshot.total_points,
                PredictionEntry.display_name,
            )
            .join(PredictionEntry, PredictionEntry.id == LeaderboardSnapshot.entry_id)
            .where(PredictionEntry.user_id == user_uuid)
            .where(LeaderboardSnapshot.entry_id.in_(eligible_entry_ids_select()))
            .where(LeaderboardSnapshot.captured_date >= earliest)
            .order_by(LeaderboardSnapshot.entry_id, LeaderboardSnapshot.captured_date)
        )
    ).all()

    by_entry: dict[str, EntryTrail] = {}
    for entry_id, captured_date, position, pts, display_name in user_rows:
        trail = by_entry.get(str(entry_id))
        if trail is None:
            trail = EntryTrail(
                entry_id=str(entry_id),
                entry_name=display_name,
                current_rank=position,
                current_gap=0.0,
                points=[],
            )
            by_entry[str(entry_id)] = trail
        trail.current_rank = position  # overwritten by newest below
        trail.points.append(TrailPoint(
            captured_date=captured_date,
            your_points=pts,
            pool_avg_points=pool_avg_by_date.get(captured_date, 0.0),
        ))

    for trail in by_entry.values():
        if trail.points:
            last = trail.points[-1]
            trail.current_gap = last.your_points - last.pool_avg_points

    return sorted(by_entry.values(), key=lambda t: t.current_rank)


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
MIN_NEAR_FOR_DEFAULT = 2


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

    user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    today = date.today()

    rows = (
        await session.execute(
            select(
                LeaderboardSnapshot.entry_id,
                LeaderboardSnapshot.position,
                LeaderboardSnapshot.total_points,
                PredictionEntry.user_id,
            )
            .join(PredictionEntry, PredictionEntry.id == LeaderboardSnapshot.entry_id)
            .where(LeaderboardSnapshot.entry_id.in_(eligible_entry_ids_select()))
            .where(LeaderboardSnapshot.captured_date == today)
        )
    ).all()

    user_rows = [r for r in rows if r[3] == user_uuid]
    if not user_rows:
        return PoolDistributionResult(
            user_points=0, window_size=DEFAULT_WINDOW, bins=[],
            next_rank_points_away=None, next_rank_position=None,
            near_count=0, caption="", generated_at=utc_now(),
        )

    best = min(user_rows, key=lambda r: r[1])  # (entry_id, position, total_points, user_id)
    user_points: int = best[2]
    user_rank: int = best[1]

    all_pts = [r[2] for r in rows]

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

    higher_deltas = [p - user_points for p in all_pts if p > user_points]
    if higher_deltas:
        next_rank_points_away = min(higher_deltas)
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
