"""Daily leaderboard snapshot service — entry-keyed.

Two write paths and two read paths:

WRITE
- take_daily_snapshots(session) — for every eligible entry on the
  leaderboard, insert today's snapshot row. Idempotent: a per-entry-per-day
  unique constraint means a second call on the same day is a no-op for
  entries that already have a row. Called from the score_scheduler tick.

READ
- get_entry_trajectory(session, entry_id, days) — return the last `days`
  of snapshot points for one entry (oldest first). The current live
  position is NOT included; the API endpoint prepends/appends it.
- get_steepest_climbers(session, days, limit) — rank entries by their
  position improvement over the trailing N days. A user with two
  climbing entries can legitimately appear twice — entries are the
  unit, not users.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models._datetime import utc_now
from app.models.entry import PredictionEntry
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.services.leaderboard import calculate_leaderboard


logger = logging.getLogger(__name__)


async def take_daily_snapshots(session: AsyncSession) -> int:
    """Snapshot every eligible entry's current position + total points for
    today (UTC).

    Returns the number of rows actually inserted (zero if today's snapshot
    already exists for everyone — i.e. on every tick after the first).

    Uses an idempotent INSERT ... ON CONFLICT DO NOTHING so concurrent
    scheduler invocations can't double-insert. Safe to call every minute.
    """
    leaderboard = await calculate_leaderboard(session, phase=None)
    if not leaderboard.entries:
        return 0

    today = utc_now().date()
    rows = [
        {
            "id": uuid.uuid4(),
            "user_id": entry.user_id,
            "entry_id": entry.entry_id,
            "position": entry.position,
            "total_points": entry.total_points,
            "captured_date": today,
            "captured_at": utc_now(),
        }
        for entry in leaderboard.entries
    ]

    stmt = (
        pg_insert(LeaderboardSnapshot)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_snapshot_entry_date")
    )
    result = await session.execute(stmt)
    await session.commit()
    inserted = result.rowcount or 0
    if inserted:
        logger.info("leaderboard_snapshots: inserted %d rows for %s", inserted, today)
    return inserted


async def get_entry_trajectory(
    session: AsyncSession,
    entry_id: uuid.UUID,
    days: int = 7,
) -> list[LeaderboardSnapshot]:
    """Return one entry's snapshot history for the last `days` days, oldest first.

    Includes today's snapshot if one exists; doesn't fabricate missing days.
    The API endpoint appends a live "now" point on top of this so the chart's
    final dot is always the current rank.

    Returns an empty list if the entry is disabled — historical snapshot
    rows are preserved on disk (re-enable should restore the trajectory
    without holes) but withheld at read-time. Belt-and-braces with the
    visibility check in `check_entry_visibility`; the API routes call
    that first and 403 before reaching this function, but a future
    direct caller wouldn't.
    """
    floor_date = utc_now().date() - timedelta(days=days - 1)
    result = await session.execute(
        select(LeaderboardSnapshot)
        .join(PredictionEntry, PredictionEntry.id == LeaderboardSnapshot.entry_id)
        .where(LeaderboardSnapshot.entry_id == entry_id)
        .where(LeaderboardSnapshot.captured_date >= floor_date)
        .where(PredictionEntry.is_disabled == False)  # noqa: E712
        .order_by(LeaderboardSnapshot.captured_date.asc())
    )
    return list(result.scalars().all())


async def get_steepest_climbers(
    session: AsyncSession,
    days: int = 7,
    limit: int = 5,
) -> list[dict]:
    """Return the entries whose position improved the most over the last `days`.

    Compared between each entry's earliest snapshot in the window and its
    most recent. `places` is positive when the entry climbed (a lower number
    = better rank), so a move from 14 → 8 returns places=6.

    Returns a list of dicts: { entry_id, user_id, places, current_position,
    previous_position }. `user_id` lets the API layer join to the display
    name without a second pass over the entries table.
    """
    floor_date = utc_now().date() - timedelta(days=days - 1)
    result = await session.execute(
        select(LeaderboardSnapshot)
        .where(LeaderboardSnapshot.captured_date >= floor_date)
        .order_by(LeaderboardSnapshot.entry_id, LeaderboardSnapshot.captured_date.asc())
    )
    snaps = list(result.scalars().all())

    # Group by entry → (earliest, latest)
    per_entry: dict[uuid.UUID, tuple[LeaderboardSnapshot, LeaderboardSnapshot]] = {}
    for snap in snaps:
        if snap.entry_id is None:
            continue
        if snap.entry_id not in per_entry:
            per_entry[snap.entry_id] = (snap, snap)
        else:
            first, _last = per_entry[snap.entry_id]
            per_entry[snap.entry_id] = (first, snap)

    climbers = []
    for entry_id, (first, last) in per_entry.items():
        places = first.position - last.position  # positive = climbed
        climbers.append(
            {
                "entry_id": entry_id,
                "user_id": last.user_id,
                "places": places,
                "current_position": last.position,
                "previous_position": first.position,
            }
        )

    climbers.sort(key=lambda c: c["places"], reverse=True)
    return climbers[:limit]
