"""Fixture schemas."""

import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from app.models.fixture import MatchStatus


class FixtureScore(BaseModel):
    """Embedded score data for a finished fixture."""

    home_score: int
    away_score: int
    home_score_et: int | None = None
    away_score_et: int | None = None
    home_penalties: int | None = None
    away_penalties: int | None = None
    outcome: str  # '1', 'X', '2'
    # Admin-verified scores are locked against the API sync (manual
    # corrections survive the scheduler). Drives the lock badge on
    # /admin/sync.
    verified: bool = False


class FixtureRead(BaseModel):
    """Schema for reading fixture data."""

    id: uuid.UUID
    home_team: str
    away_team: str
    kickoff: datetime
    stage: str
    group: str | None
    match_number: int | None
    # external_id is the Football-Data fixture ID (v2.184.x: surfaced so
    # frontend bracket-position widgets can map a Fixture to its FIFA match
    # number via the hand-verified R32 mapping, mirroring backend
    # bracket_seeding.EXT_ID_TO_MATCH_NUMBER).
    external_id: str | None = None
    status: MatchStatus
    minute: int | None
    is_locked: bool
    time_until_lock: int | None  # Seconds until lock, None if already locked
    score: FixtureScore | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class FixturesByGroup(BaseModel):
    """Fixtures organized by group."""

    group: str
    fixtures: list[FixtureRead]


class LockStatus(BaseModel):
    """Lock status for a fixture."""

    fixture_id: uuid.UUID
    is_locked: bool
    locks_at: datetime
    time_remaining: timedelta | None


# Admin schemas
class FixtureCreate(BaseModel):
    """Schema for creating a fixture (admin only)."""

    competition_id: uuid.UUID
    home_team: str = Field(..., min_length=1, max_length=100)
    away_team: str = Field(..., min_length=1, max_length=100)
    kickoff: datetime
    stage: str = Field(..., min_length=1, max_length=50)
    group: str | None = Field(None, max_length=10)
    match_number: int | None = None
    external_id: str | None = None


class FixtureUpdate(BaseModel):
    """Schema for updating a fixture (admin only)."""

    home_team: str | None = Field(None, min_length=1, max_length=100)
    away_team: str | None = Field(None, min_length=1, max_length=100)
    kickoff: datetime | None = None
    stage: str | None = Field(None, min_length=1, max_length=50)
    group: str | None = Field(None, max_length=10)
    match_number: int | None = None
    external_id: str | None = None


class FixtureStatusUpdate(BaseModel):
    """Schema for updating fixture status (admin only)."""

    status: MatchStatus
    minute: int | None = Field(None, ge=0, le=150)
