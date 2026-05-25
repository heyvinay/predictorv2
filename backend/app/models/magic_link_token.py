"""Magic link token model for passwordless authentication.

Workflow:
  1. User submits email → backend creates (or finds) the User row, then
     generates a fresh token via :func:`generate_magic_token`. The
     **hash** is stored in the DB row; the **raw** token is embedded in
     the link sent by email. Raw is never persisted.
  2. User clicks the email link → backend SHA-256s the incoming raw
     token, looks up the row by hash (indexed), and validates it is:
       - not expired (`expires_at > now`)
       - not yet used (`used_at IS NULL`)
  3. Backend marks `used_at = now`, mints a JWT, and redirects the
     browser to the frontend's `/auth/callback?token=<jwt>`.

Single-use, time-limited (default 15 min), unguessable
(`secrets.token_urlsafe(32)` → 256 bits of entropy).
"""

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now

if TYPE_CHECKING:
    from app.models.user import User


class MagicLinkToken(SQLModel, table=True):
    """Single-use, time-limited token for passwordless email login."""

    __tablename__ = "magic_link_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    # SHA-256 of the raw token (hex digest, 64 chars). Stored hashed so a
    # DB leak can't be turned into account takeover. Indexed so the
    # verify endpoint's lookup is O(log n).
    token_hash: str = Field(index=True)
    expires_at: datetime = Field(sa_column=utc_datetime_column(nullable=False))
    # NULL = unused. Set to `now` on first successful verify; subsequent
    # verifies of the same raw token are rejected.
    used_at: datetime | None = Field(default=None, sa_column=utc_datetime_column())
    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    user: "User" = Relationship(back_populates="magic_link_tokens")


def generate_magic_token() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)``.

    Only the hash is stored in the DB; the raw value is what travels in
    the email link. SHA-256 is appropriate here — we never compare two
    user-supplied tokens, only look up the hash row given an incoming
    raw token, so we don't need bcrypt's slow-by-design behaviour.
    """
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_token(raw: str) -> str:
    """Hash an incoming raw token the same way :func:`generate_magic_token`
    hashes the one it generates. Used by the verify endpoint."""
    return hashlib.sha256(raw.encode()).hexdigest()
