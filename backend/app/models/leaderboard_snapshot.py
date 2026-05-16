"""Daily leaderboard snapshot — one row per entry per day.

Powers the rank trajectory sparkline on the Panini dashboard and the
per-row 7-day trend column on the leaderboard. We take one snapshot per
day per entry; the live current position is fetched separately and
prepended client-side so the most recent dot is always up to date.

Snapshots are taken by a background task in score_scheduler.py — idempotent
per (entry_id, captured_date), so running the snapshot loop on every tick
is cheap and self-healing if the server was down for a day.

`user_id` is retained alongside `entry_id` so leaderboard responses can
render the user's display name without an extra join. `entry_id` is the
primary key for uniqueness — every snapshot row must belong to an entry.
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now

if TYPE_CHECKING:
    from app.models.entry import PredictionEntry
    from app.models.user import User


class LeaderboardSnapshot(SQLModel, table=True):
    """One entry's position + points captured on a given calendar day (UTC)."""

    __tablename__ = "leaderboard_snapshots"
    __table_args__ = (
        UniqueConstraint("entry_id", "captured_date", name="uq_snapshot_entry_date"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    entry_id: uuid.UUID = Field(
        foreign_key="prediction_entries.id", index=True
    )

    # Rank as of the snapshot.
    position: int
    # Total points across all phases at the moment of capture.
    total_points: int

    # The wall-clock UTC date this snapshot represents. Used for uniqueness
    # so we never end up with two snapshots for the same entry on the same
    # day (the service uses INSERT ... ON CONFLICT semantics).
    captured_date: date = Field(index=True)
    # Exact moment the snapshot row was inserted (for audit/debug).
    captured_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationships
    user: Optional["User"] = Relationship()
    entry: Optional["PredictionEntry"] = Relationship(back_populates="leaderboard_snapshots")
