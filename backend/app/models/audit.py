"""System-wide audit log.

`AuditEvent` is the unified log for every user-attributable action on the
system: authentication (login, logout, register), entry mutations,
prediction writes, admin settings changes, etc. This is a prize-money
competition, so the audit log is part of the system's integrity guarantee
— every state change must be recoverable from the log alone.

Two log tables coexist:

- `prediction_entry_events` — entry status transitions only, optimized for
  fast per-entry timeline queries (see `entry.py`).
- `audit_events` — everything else (and a row is also written here for
  every entry transition, so this table is the global source of truth).

Both are written in the same transaction as the state mutation, so the
log can never disagree with the state.

`event_type` is a dotted string with a fixed namespace (e.g. `entry.created`,
`auth.login_succeeded`, `competition.settings_updated`). Subjects use a
polymorphic `(subject_type, subject_id)` pair so we don't pile up nullable
FKs to every table.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# JSONB on Postgres (production), JSON on SQLite (tests). Using
# `with_variant` keeps the model dialect-portable without losing the
# Postgres-specific GIN-indexable JSONB at runtime.
_PORTABLE_JSON = JSONB().with_variant(JSON(), "sqlite")

from app.models._datetime import utc_datetime_column, utc_now
from app.models.entry import ActorRole


class AuditEvent(SQLModel, table=True):
    """One auditable action by one actor.

    Designed to be append-only — nothing in the system mutates a row after
    it's written. There is no `updated_at` column for this reason.
    """

    __tablename__ = "audit_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Dotted namespace string — e.g. "auth.login_succeeded", "entry.created",
    # "entry.phase_ready", "competition.settings_updated". Indexed because
    # filtering by event type is the most common audit query pattern.
    event_type: str = Field(index=True, max_length=64)

    # Nullable: for failed-login or unauthenticated requests we don't always
    # have a user id to attribute. The combination of (event_type, ip_address)
    # plus the metadata payload provides enough context for forensics.
    actor_user_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", index=True
    )
    actor_role: ActorRole

    # Polymorphic subject — what the action affected. `subject_type` is a
    # short string like "entry", "user", "competition", "match_prediction".
    # `subject_id` is the row id of that subject. Both nullable so events
    # without a concrete subject (e.g. failed login by email-not-found) can
    # still be recorded.
    subject_type: str | None = Field(default=None, index=True, max_length=32)
    subject_id: uuid.UUID | None = Field(default=None, index=True)

    # HTTP context, captured at the API boundary. ip_address is a string
    # (not INET) to keep the audit table dialect-portable and to avoid
    # leaking the request type into the service layer.
    ip_address: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=512)

    # Structured payload — `{"old_name": "X", "new_name": "Y"}`,
    # `{"phase": "phase_1"}`, etc. Stored as JSONB so it's queryable
    # without parsing in the application layer.
    event_metadata: dict[str, Any] | None = Field(
        default=None, sa_column=Column(_PORTABLE_JSON, nullable=True)
    )

    # Free-form user-supplied reason (e.g. admin's reason for disabling).
    reason: str | None = None

    created_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column(index=True)
    )
