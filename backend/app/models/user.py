"""User model for authentication and profile."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now

if TYPE_CHECKING:
    from app.models.competition import Competition
    from app.models.entry import PredictionEntry
    from app.models.magic_link_token import MagicLinkToken


class AuthProvider(str, Enum):
    """Authentication provider options."""

    EMAIL = "email"
    GOOGLE = "google"


class Employer(str, Enum):
    """Which pool-organizing company the participant works for.

    NEITHER means an outside participant who must name a contact at
    Atlas or JMFA (see ``User.company_contact``).
    """

    ATLAS = "atlas"
    JMFA = "jmfa"
    NEITHER = "neither"


class User(SQLModel, table=True):
    """User account for predictions."""

    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    # Name is nullable: new users sign in via magic-link before they pick
    # a display name. The /onboarding page collects the name after first
    # successful sign-in. UserRead reflects this with `name: str | None`.
    name: str | None = None
    # Password hash is also nullable — magic-link users never set one.
    password_hash: str | None = None
    google_id: str | None = Field(default=None, index=True, unique=True)
    auth_provider: AuthProvider = Field(default=AuthProvider.EMAIL)
    is_admin: bool = Field(default=False)
    is_active: bool = Field(default=True)
    # Admin-managed flag tracking whether this participant has paid their
    # entry. Default false; only mutated by /api/admin/users/{id}/paid.
    paid: bool = Field(default=False)

    # Onboarding profile fields. All nullable: enforced by the onboarding
    # gate + API validators rather than DB NOT NULL, so existing rows
    # (and Google sign-ups) can be back-filled rather than rejected.
    employer: Employer | None = None
    # Required only when employer is NEITHER — their named contact at
    # Atlas or JMFA. Enforced in UserUpdate's model_validator.
    company_contact: str | None = None
    # "Who you paid the fee to." Captured later at entry submission, not
    # onboarding (the user doesn't know it at signup). Per-user.
    paid_to: str | None = None

    competition_id: uuid.UUID | None = Field(default=None, foreign_key="competitions.id")

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    # Engagement signal — updated by the get_current_user dependency on
    # each authenticated request, throttled to once per LAST_SEEN_THROTTLE_S
    # (config). Nullable for never-seen users; backfill migration seeds it
    # from MAX(audit_events.created_at) ∪ User.created_at. v2.176.0.
    last_seen_at: datetime | None = Field(
        default=None, sa_column=utc_datetime_column(nullable=True)
    )

    # What-if bracket simulator gating. One-time trivia unlock is permanent
    # per user (never resets); the daily-run counters reset at UTC midnight
    # via services.simulator._apply_daily_reset. Admins bypass both checks
    # entirely (see services.simulator.get_status / record_run) but still
    # have their usage counted + audited.
    simulator_unlocked: bool = Field(default=False)
    simulator_runs_used: int = Field(default=0)
    simulator_runs_reset_at: datetime | None = Field(
        default=None, sa_column=utc_datetime_column(nullable=True)
    )

    # Relationships
    competition: Optional["Competition"] = Relationship(back_populates="users")
    entries: list["PredictionEntry"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "[PredictionEntry.user_id]"},
    )
    magic_link_tokens: list["MagicLinkToken"] = Relationship(back_populates="user")
