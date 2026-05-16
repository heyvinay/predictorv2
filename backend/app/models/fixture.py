"""Fixture model for matches."""

import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import aware_utc, utc_datetime_column, utc_now

if TYPE_CHECKING:
    from app.models.competition import Competition
    from app.models.prediction import MatchPrediction
    from app.models.score import Score


class MatchStatus(str, Enum):
    """Match status for tracking live games."""

    SCHEDULED = "scheduled"
    LIVE = "live"
    HALFTIME = "halftime"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class Fixture(SQLModel, table=True):
    """Match fixture in the tournament."""

    __tablename__ = "fixtures"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    competition_id: uuid.UUID = Field(foreign_key="competitions.id")

    home_team: str = Field(index=True)
    away_team: str = Field(index=True)
    kickoff: datetime = Field(sa_column=utc_datetime_column(index=True))

    # Tournament position
    stage: str  # "group", "round_of_32", "round_of_16", "quarter_final", "semi_final", "final"
    group: str | None = None  # "A", "B", etc. for group stage
    match_number: int | None = None  # For ordering

    # Match state
    status: MatchStatus = Field(default=MatchStatus.SCHEDULED)
    minute: int | None = None  # Current minute if live

    # External API reference
    external_id: str | None = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationships
    competition: "Competition" = Relationship(back_populates="fixtures")
    predictions: list["MatchPrediction"] = Relationship(back_populates="fixture")
    score: Optional["Score"] = Relationship(back_populates="fixture")

    def is_locked(self, lock_minutes: int = 5) -> bool:
        """Check if predictions are locked for this fixture."""
        kickoff = aware_utc(self.kickoff)
        lock_time = kickoff - timedelta(minutes=lock_minutes)
        return aware_utc(utc_now()) >= lock_time

    def time_until_lock(self, lock_minutes: int = 5) -> timedelta | None:
        """Get time remaining until predictions lock."""
        kickoff = aware_utc(self.kickoff)
        lock_time = kickoff - timedelta(minutes=lock_minutes)
        remaining = lock_time - aware_utc(utc_now())
        return remaining if remaining.total_seconds() > 0 else None
