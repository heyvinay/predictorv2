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

    competition_id: uuid.UUID | None = Field(default=None, foreign_key="competitions.id")

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationships
    competition: Optional["Competition"] = Relationship(back_populates="users")
    entries: list["PredictionEntry"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "[PredictionEntry.user_id]"},
    )
    magic_link_tokens: list["MagicLinkToken"] = Relationship(back_populates="user")
