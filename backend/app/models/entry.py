"""Prediction entry models.

A `PredictionEntry` is one user's competing instance in a competition. A
user may have multiple entries (configurable per competition; default 5,
minimum 1). All prediction rows (match / team / bonus) are owned by an
entry, not by a user directly — this is what makes per-entry leaderboards,
duplication, and withdrawal possible without affecting other entries.

Three tables in this module:

- `prediction_entries` — the entry itself, owns a reference, display name,
  payment/disable/withdrawn state.
- `prediction_entry_phases` — per-(entry, phase) lifecycle row tracking
  status (draft/ready/submitted/locked/withdrawn/disabled) and the
  timestamps for each transition. Always created in both whole-competition
  and phase-scoped status modes.
- `prediction_entry_events` — append-only audit log of every status
  transition. Records who moved what entry from which state to which,
  with optional reason.

The `entrystatus`, `actorrole`, and `paymentmode` Postgres enum types
are created by the migration that introduces this module. The existing
`predictionphase` enum (PHASE_1/PHASE_2) is reused.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now
from app.models.prediction import PredictionPhase

if TYPE_CHECKING:
    from app.models.bonus import BonusPrediction
    from app.models.competition import Competition
    from app.models.leaderboard_snapshot import LeaderboardSnapshot
    from app.models.prediction import MatchPrediction, TeamPrediction
    from app.models.user import User


class EntryStatus(str, Enum):
    """Lifecycle state of a prediction entry (or a single phase of one).

    `locked` is terminal for prediction edits. To exclude a locked entry
    from a competition, use the `is_disabled` overlay on PredictionEntry
    rather than mutating status.
    """

    DRAFT = "draft"
    READY = "ready"
    SUBMITTED = "submitted"
    LOCKED = "locked"
    WITHDRAWN = "withdrawn"
    DISABLED = "disabled"


class ActorRole(str, Enum):
    """Who triggered a state transition (for audit events)."""

    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class PaymentMode(str, Enum):
    """Whether payment is tracked per entry or per user.

    `per_entry` is the default — each entry has its own paid flag.
    `per_user` falls back to User.paid (legacy single-entry behaviour).
    """

    PER_ENTRY = "per_entry"
    PER_USER = "per_user"


class PredictionEntry(SQLModel, table=True):
    """One competing instance owned by a user within a competition."""

    __tablename__ = "prediction_entries"
    __table_args__ = (
        UniqueConstraint(
            "competition_id", "reference", name="uq_entry_competition_reference"
        ),
        UniqueConstraint(
            "competition_id",
            "user_id",
            "entry_number",
            name="uq_entry_competition_user_number",
        ),
        Index("ix_entry_competition_user", "competition_id", "user_id"),
        Index("ix_entry_competition_disabled", "competition_id", "is_disabled"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    competition_id: uuid.UUID = Field(foreign_key="competitions.id")
    user_id: uuid.UUID = Field(foreign_key="users.id")

    # Backend-generated, immutable per (competition, reference). Format
    # WC26-000001 — competition code + zero-padded global sequence.
    reference: str
    # User-editable label shown in the UI. Defaults to "Entry N" until
    # the user renames it.
    display_name: str
    # Per-user sequence within a competition (1, 2, 3...).
    entry_number: int

    paid: bool = Field(default=False)
    prize_eligible: bool = Field(default=True)

    # Admin overlay — set when an admin disables an entry post-lock. Does
    # NOT mutate phase status (which may be `locked` and is terminal).
    is_disabled: bool = Field(default=False)
    disabled_reason: str | None = None
    disabled_at: datetime | None = Field(
        default=None, sa_column=utc_datetime_column(nullable=True)
    )
    # FK to users.id — stays a bare column (no ORM Relationship) so we
    # don't trigger SQLAlchemy's AmbiguousForeignKeysError between this
    # and user_id. If a relationship is ever needed, declare it with
    # explicit foreign_keys=[disabled_by_user_id] on both ends.
    disabled_by_user_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id"
    )

    withdrawn_at: datetime | None = Field(
        default=None, sa_column=utc_datetime_column(nullable=True)
    )
    withdrawn_reason: str | None = None

    created_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column()
    )
    updated_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column()
    )

    # Relationships
    competition: "Competition" = Relationship(back_populates="entries")
    user: "User" = Relationship(
        back_populates="entries",
        sa_relationship_kwargs={"foreign_keys": "[PredictionEntry.user_id]"},
    )
    phases: list["PredictionEntryPhase"] = Relationship(back_populates="entry")
    events: list["PredictionEntryEvent"] = Relationship(back_populates="entry")
    match_predictions: list["MatchPrediction"] = Relationship(
        back_populates="entry"
    )
    team_predictions: list["TeamPrediction"] = Relationship(
        back_populates="entry"
    )
    bonus_predictions: list["BonusPrediction"] = Relationship(
        back_populates="entry"
    )
    leaderboard_snapshots: list["LeaderboardSnapshot"] = Relationship(
        back_populates="entry"
    )


class PredictionEntryPhase(SQLModel, table=True):
    """Per-phase lifecycle record for a prediction entry.

    Always created in both whole-competition and phase-scoped modes — the
    schema doesn't change when an admin enables `phase_scoped_status_enabled`,
    only the UX surface.
    """

    __tablename__ = "prediction_entry_phases"
    __table_args__ = (
        UniqueConstraint("entry_id", "phase", name="uq_entry_phase"),
        Index("ix_entry_phase_status", "phase", "status"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entry_id: uuid.UUID = Field(foreign_key="prediction_entries.id", index=True)
    # `phase` reuses the existing `predictionphase` enum type from Postgres.
    # `status` uses the new `entrystatus` type created by this task's
    # migration. Plain `Field(...)` lets SQLModel store via the enum's
    # `.name` (UPPERCASE), matching the literal values declared in the
    # CREATE TYPE statements. The dialect-specific `create_type` toggle
    # only matters in the migration, not in the ORM model.
    phase: PredictionPhase
    status: EntryStatus

    ready_at: datetime | None = Field(
        default=None, sa_column=utc_datetime_column(nullable=True)
    )
    submitted_at: datetime | None = Field(
        default=None, sa_column=utc_datetime_column(nullable=True)
    )
    locked_at: datetime | None = Field(
        default=None, sa_column=utc_datetime_column(nullable=True)
    )
    status_reason: str | None = None

    created_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column()
    )
    updated_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column()
    )

    # Relationships
    entry: "PredictionEntry" = Relationship(back_populates="phases")


class PredictionEntryEvent(SQLModel, table=True):
    """Append-only audit row for one entry state transition.

    `from_status` and `to_status` are plain strings (not enum-typed) to
    keep this log immune to future renames of EntryStatus values.
    """

    __tablename__ = "prediction_entry_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entry_id: uuid.UUID = Field(foreign_key="prediction_entries.id", index=True)
    phase: PredictionPhase | None = None

    from_status: str
    to_status: str

    actor_user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    actor_role: ActorRole

    reason: str | None = None

    created_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column()
    )

    # Relationships
    entry: "PredictionEntry" = Relationship(back_populates="events")
