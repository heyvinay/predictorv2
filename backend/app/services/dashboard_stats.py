"""Dashboard widget derivations — daily MVPs, personal trail, pool distribution.

All three read from LeaderboardSnapshot and respect the blind-pool gate.
Datetimes are aware-UTC; dates are plain `date`.
"""
from __future__ import annotations

import math
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
    bucket_start: int
    bucket_end: int
    count: int


@dataclass
class YourEntryMarker:
    entry_id: str
    entry_name: str
    points: int
    position: int


@dataclass
class PoolDistributionResult:
    bins: list[DistBin]
    bucket_width: int
    min_points: int
    max_points: int
    total_entries: int
    your_entries: list[YourEntryMarker]
    caption: str
    generated_at: datetime


def _nice_bucket_width(value_range: int, target_buckets: int = 12) -> int:
    """Round a raw bucket width up to a "nice" step (1/2/5 × a power of ten)
    so histogram axis labels land on clean numbers instead of arbitrary
    point values. Mirrors the standard D3-style tick-step algorithm."""
    if value_range <= 0:
        return 1
    raw = value_range / target_buckets
    magnitude = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 5, 10):
        step = magnitude * mult
        if step >= raw:
            return int(step)
    return int(magnitude * 10)  # pragma: no cover — unreachable, mult=10 always satisfies step >= raw


def _empty_result(total_entries: int = 0) -> PoolDistributionResult:
    return PoolDistributionResult(
        bins=[], bucket_width=1, min_points=0, max_points=0,
        total_entries=total_entries, your_entries=[], caption="",
        generated_at=utc_now(),
    )


async def compute_pool_distribution(
    session: AsyncSession, *, user_id: str,
) -> PoolDistributionResult:
    """Full-pool points histogram with the requesting user's OWN entries
    (all of them, not just their best) marked individually. Buckets span
    every eligible entry's total_points, not a narrow window around one
    score — with real point gaps between ranks, a narrow window is often
    empty except the user's own bar (v2.198.x redesign)."""
    if not await is_phase1_locked(session):
        return _empty_result()

    user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    today = date.today()

    rows = (
        await session.execute(
            select(
                LeaderboardSnapshot.entry_id,
                LeaderboardSnapshot.position,
                LeaderboardSnapshot.total_points,
                PredictionEntry.user_id,
                PredictionEntry.display_name,
            )
            .join(PredictionEntry, PredictionEntry.id == LeaderboardSnapshot.entry_id)
            .where(LeaderboardSnapshot.entry_id.in_(eligible_entry_ids_select()))
            .where(LeaderboardSnapshot.captured_date == today)
        )
    ).all()

    if not rows:
        return _empty_result()

    user_rows = [r for r in rows if r[3] == user_uuid]
    if not user_rows:
        return _empty_result(total_entries=len(rows))

    all_pts = [r[2] for r in rows]
    min_pts, max_pts = min(all_pts), max(all_pts)
    width = _nice_bucket_width(max_pts - min_pts)
    origin = (min_pts // width) * width

    bins_map: dict[int, int] = {}
    for p in all_pts:
        bucket_start = origin + ((p - origin) // width) * width
        bins_map[bucket_start] = bins_map.get(bucket_start, 0) + 1

    bins = [
        DistBin(bucket_start=start, bucket_end=start + width - 1, count=count)
        for start, count in sorted(bins_map.items())
    ]

    your_entries = sorted(
        (
            YourEntryMarker(
                entry_id=str(entry_id), entry_name=display_name or "",
                points=pts, position=position,
            )
            for entry_id, position, pts, _uid, display_name in user_rows
        ),
        key=lambda e: e.position,
    )

    caption = _build_caption(your_entries=your_entries, total_entries=len(rows))

    return PoolDistributionResult(
        bins=bins,
        bucket_width=width,
        min_points=min_pts,
        max_points=max_pts,
        total_entries=len(rows),
        your_entries=your_entries,
        caption=caption,
        generated_at=utc_now(),
    )


def _build_caption(*, your_entries: list[YourEntryMarker], total_entries: int) -> str:
    """Compose the server-side caption for the full-pool distribution.
    Every entry the user owns is in `your_entries` (sorted best-first)."""
    if not your_entries:
        return ""
    if len(your_entries) == 1:
        pos = your_entries[0].position
        if pos == 1:
            return f"You're leading the pool of {total_entries} entries."
        return f"You're #{pos} of {total_entries} entries."
    best, worst = your_entries[0].position, your_entries[-1].position
    if best == 1:
        return (
            f"Your best entry leads the pool of {total_entries} — "
            f"{len(your_entries)} entries total."
        )
    return f"Your {len(your_entries)} entries rank #{best}–#{worst} of {total_entries}."
