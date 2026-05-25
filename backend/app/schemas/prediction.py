"""Prediction schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.prediction import PredictionPhase
from app.schemas.fixture import FixtureScore


class MatchPredictionCreate(BaseModel):
    """Schema for creating a match prediction."""

    fixture_id: uuid.UUID
    home_score: int = Field(ge=0, le=15)
    away_score: int = Field(ge=0, le=15)


class MatchPredictionUpdate(BaseModel):
    """Schema for updating a match prediction."""

    home_score: int = Field(ge=0, le=15)
    away_score: int = Field(ge=0, le=15)


class MatchPredictionRead(BaseModel):
    """Schema for reading a match prediction."""

    id: uuid.UUID
    fixture_id: uuid.UUID
    home_score: int
    away_score: int
    phase: PredictionPhase
    locked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # Include fixture info for display
    home_team: str | None = None
    away_team: str | None = None
    kickoff: datetime | None = None
    is_locked: bool = False

    class Config:
        """Pydantic config."""

        from_attributes = True


class MatchPredictionBatch(BaseModel):
    """Schema for batch updating match predictions."""

    predictions: list[MatchPredictionCreate]


class TeamAdvancementPrediction(BaseModel):
    """Single team advancement prediction."""

    team: str
    stage: str  # "round_of_32", "round_of_16", etc.
    group_position: int | None = Field(default=None, ge=1, le=4)


class BracketPrediction(BaseModel):
    """User's full bracket prediction."""

    group_winners: dict[str, list[str]]  # group -> [1st, 2nd, 3rd (if advances)]
    round_of_32: list[str]
    round_of_16: list[str]
    quarter_finals: list[str]
    semi_finals: list[str]
    final: list[str]
    winner: str


class BracketPredictionUpdate(BaseModel):
    """Schema for updating bracket predictions."""

    predictions: list[TeamAdvancementPrediction]


# Community predictions schemas (for the results page scatter plot)


class CommunityPrediction(BaseModel):
    """A single entry's prediction for a match.

    Identified by entry_reference + entry_name + user_name — one row per
    eligible entry, not per user (a user with two entries appears twice
    with distinct references). Visibility is gated by fixture lock /
    finish at the API layer.
    """

    user_name: str
    entry_reference: str
    entry_name: str
    home_score: int
    away_score: int


class CommunityPredictionsResponse(BaseModel):
    """All predictions for a single fixture, for community viewing."""

    fixture_id: uuid.UUID
    home_team: str
    away_team: str
    predictions: list[CommunityPrediction]
    actual: FixtureScore | None = None
