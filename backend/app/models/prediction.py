"""Prediction models for match scores and team advancement.

Prediction rows are owned by a `PredictionEntry` (not by a User directly).
The owning user is resolved through `entry.user_id`. This is what allows
a single user to hold multiple independent prediction sets within the
same competition.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now

if TYPE_CHECKING:
    from app.models.entry import PredictionEntry
    from app.models.fixture import Fixture


class PredictionPhase(str, Enum):
    """Which prediction phase this was submitted in."""

    PHASE_1 = "phase_1"  # Pre-tournament
    PHASE_2 = "phase_2"  # After group stage


class MatchPrediction(SQLModel, table=True):
    """An entry's predicted score for a single match."""

    __tablename__ = "match_predictions"
    __table_args__ = (
        UniqueConstraint(
            "entry_id", "fixture_id", name="uq_match_pred_entry_fixture"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entry_id: uuid.UUID = Field(foreign_key="prediction_entries.id", index=True)
    fixture_id: uuid.UUID = Field(foreign_key="fixtures.id", index=True)

    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    phase: PredictionPhase = Field(default=PredictionPhase.PHASE_1)

    locked_at: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationships
    entry: "PredictionEntry" = Relationship(back_populates="match_predictions")
    fixture: "Fixture" = Relationship(back_populates="predictions")

    @property
    def predicted_outcome(self) -> str:
        """Get predicted outcome: '1' (home), 'X' (draw), '2' (away)."""
        if self.home_score > self.away_score:
            return "1"
        elif self.home_score < self.away_score:
            return "2"
        return "X"


class TeamPrediction(SQLModel, table=True):
    """An entry's prediction for team advancement in knockout stages.

    Unique per (entry, phase, team, stage) — the phase column is part of
    the uniqueness key so the same team/stage can have different picks
    across Phase 1 and Phase 2 within the same entry.
    """

    __tablename__ = "team_predictions"
    __table_args__ = (
        UniqueConstraint(
            "entry_id",
            "phase",
            "team",
            "stage",
            name="uq_team_pred_entry_phase_team_stage",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entry_id: uuid.UUID = Field(foreign_key="prediction_entries.id", index=True)

    team: str = Field(index=True)  # Team name/code
    stage: str  # "round_of_32", "round_of_16", "quarter_final", etc.
    group_position: int | None = None  # 1, 2, or 3 for group stage
    phase: PredictionPhase = Field(default=PredictionPhase.PHASE_1)

    locked_at: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationships
    entry: "PredictionEntry" = Relationship(back_populates="team_predictions")
