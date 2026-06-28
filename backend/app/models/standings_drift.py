"""StandingsDriftEvent — records of standings disagreement (v2.182.0).

Each row captures a single moment in time when our computed standings
disagreed with a trusted external source. The drift verifier creates
these; admins resolve them via the admin UI. Audit-style: NEVER deleted,
just transitions through statuses.

Detect-only design (per design call 2026-06-28):
  - The verifier never overwrites our /standings page; it just writes
    a drift event row.
  - The admin reviews the diff in the admin UI, picks a remediation
    (edit score in /admin/sync → fixes the cause; dismiss as ours-correct
    → trusts our compute; dismiss as transient → trusted source was
    briefly stale), and the event closes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.models._datetime import utc_datetime_column, utc_now


class TrustedSource(str, Enum):
    """Which external source's standings produced the disagreement."""

    FOOTBALL_DATA = "FOOTBALL_DATA"
    ESPN = "ESPN"
    WIKIPEDIA = "WIKIPEDIA"


class DriftEventStatus(str, Enum):
    """Lifecycle of a drift event row."""

    # Just opened — admin hasn't reviewed yet.
    OPEN = "OPEN"
    # Admin reviewed and decided our compute is right (trusted source was
    # wrong). Adds a resolution_note explaining.
    DISMISSED_OURS_CORRECT = "DISMISSED_OURS_CORRECT"
    # Admin reviewed and the disagreement was a brief settle-window
    # blip — by next tick the sources agreed again.
    DISMISSED_TRANSIENT = "DISMISSED_TRANSIENT"
    # Admin edited a fixture's score via /admin/sync to fix the cause;
    # the next verification cycle confirmed both sides agree.
    RESOLVED_VIA_SCORE_EDIT = "RESOLVED_VIA_SCORE_EDIT"


class StandingsDriftEvent(SQLModel, table=True):
    """One disagreement between our computed standings and a trusted
    source's standings, captured at detection time."""

    __tablename__ = "standings_drift_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    competition_id: uuid.UUID = Field(foreign_key="competitions.id", index=True)
    detected_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column()
    )
    trusted_source: TrustedSource

    # JSON snapshot of the disagreement at detection time:
    # {"groups": {"A": {"ours": [<rows>], "theirs": [<rows>]}, ...}}
    # Frozen at detection time so the admin can review even after the
    # live standings have moved. Uses portable JSON (JSONB on Postgres,
    # TEXT-backed JSON on SQLite for the test suite).
    groups_disagreeing: dict = Field(
        default_factory=dict,
        sa_column=sa.Column(sa.JSON(), nullable=False, server_default="{}"),
    )

    status: DriftEventStatus = Field(default=DriftEventStatus.OPEN, index=True)
    resolved_at: datetime | None = Field(
        default=None, sa_column=utc_datetime_column(nullable=True)
    )
    resolved_by_user_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id"
    )
    resolution_note: str | None = None

    created_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column()
    )
    updated_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column()
    )
