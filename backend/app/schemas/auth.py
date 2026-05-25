"""Authentication schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import AuthProvider
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

    class Config:
        """Pydantic config."""

        from_attributes = True


class UserUpdate(BaseModel):
    """Schema for updating user profile.

    Used by ``PATCH /api/auth/me`` — primarily by the /onboarding page
    to set a name for new magic-link users, and by admin profile edits.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None


class MagicLinkRequest(BaseModel):
    """Payload for ``POST /api/auth/request-magic-link``."""

    email: EmailStr


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
