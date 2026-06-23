"""Dashboard widget derivations — daily MVPs, personal trail, pool distribution.

All three read from LeaderboardSnapshot and respect the blind-pool gate.
Datetimes are aware-UTC; dates are plain `date`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LeaderboardSnapshot, PredictionEntry, User
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
