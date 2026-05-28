"""Authentication schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.user import AuthProvider, Employer
from app.schemas.leaderboard import PointBreakdown


class UserCreate(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=100)


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


class UserRead(BaseModel):
    """Schema for reading user data."""

    id: uuid.UUID
    email: str
    # Magic-link users start without a name (they pick one on /onboarding).
    name: str | None
    auth_provider: AuthProvider
    is_admin: bool
    is_active: bool
    competition_id: uuid.UUID | None
    created_at: datetime
    # Onboarding profile fields (see app.models.user.User).
    employer: Employer | None
    company_contact: str | None
    paid_to: str | None

    class Config:
        """Pydantic config."""

        from_attributes = True


class UserUpdate(BaseModel):
    """Schema for updating user profile.

    Used by ``PATCH /api/auth/me`` — primarily by the /onboarding page
    to set the mandatory profile fields for new magic-link users, and by
    later profile edits. All fields optional so partial edits (e.g.
    changing just the avatar) don't require resending everything.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    employer: Employer | None = None
    company_contact: str | None = Field(default=None, max_length=100)
    paid_to: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _require_contact_for_neither(self) -> "UserUpdate":
        """If employer is being set to NEITHER, a company contact is
        required (cross-field rule — the picker must send both together)."""
        if self.employer == Employer.NEITHER and not (
            self.company_contact and self.company_contact.strip()
        ):
            raise ValueError(
                "A contact name at Atlas or JMFA is required when employer is Neither."
            )
        return self


class MagicLinkRequest(BaseModel):
    """Payload for ``POST /api/auth/request-magic-link``."""

    email: EmailStr
    # Cloudflare Turnstile token from the login widget. Optional so dev
    # (CAPTCHA disabled) and tests don't need to supply one.
    captcha_token: str | None = None


class MagicLinkResponse(BaseModel):
    """Response for ``POST /api/auth/request-magic-link``.

    The same message is returned whether or not the email maps to an
    existing user — but in this app every email-submission is also an
    implicit account creation, so the response is purely informational.
    """

    message: str


class PasswordChange(BaseModel):
    """Schema for changing password."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=100)


class UserStats(BaseModel):
    """Aggregated profile statistics."""

    total_match_predictions: int
    total_team_predictions: int
    total_predictions: int
    correct_outcomes: int
    exact_scores: int
    accuracy_pct: float
    total_points: int
    leaderboard_position: int | None
    total_participants: int
    breakdown: PointBreakdown


class Token(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # User ID
    exp: datetime


class GoogleAuthCallback(BaseModel):
    """Google OAuth callback data."""

    code: str
    state: str | None = None
