"""Request and response schemas for prediction entry endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.entry import EntryStatus, PaymentMode
from app.models.prediction import PredictionPhase


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class EntryCreate(BaseModel):
    """Optional display name. If omitted, server generates `Entry {N}`."""

    display_name: str | None = Field(default=None, min_length=1, max_length=64)


class EntryRename(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)


class EntryWithdraw(BaseModel):
    """Admin withdraw — reason is REQUIRED in the simplified lifecycle.

    User-initiated withdraw was removed; admins use this with a mandatory
    reason that goes into the audit log.
    """

    reason: str = Field(min_length=1, max_length=256)


class EntryReinstate(BaseModel):
    """Admin reinstate (WITHDRAWN → SUBMITTED) — reason is REQUIRED.

    Use case: user filled all predictions but forgot to click Submit before
    competition start; admin reviews evidence and reinstates.
    """

    reason: str = Field(min_length=1, max_length=256)


class EntryDisable(BaseModel):
    """Admin disable — reason is REQUIRED per the brief."""

    reason: str = Field(min_length=1, max_length=256)


class EntryPaidUpdate(BaseModel):
    paid: bool


class EntryPrizeEligibleUpdate(BaseModel):
    prize_eligible: bool


class EntrySettingsUpdate(BaseModel):
    """Partial update — only included fields are written. All optional."""

    max_entries_per_user: int | None = Field(default=None, ge=1)
    auto_create_first_entry: bool | None = None
    allow_duplicate_from_existing: bool | None = None
    allow_user_rename: bool | None = None
    allow_user_withdrawal: bool | None = None
    require_ready_before_submit: bool | None = None
    payment_mode: PaymentMode | None = None
    block_unpaid_entry_submission: bool | None = None
    show_entry_reference_publicly: bool | None = None
    phase_scoped_status_enabled: bool | None = None
    bonus_questions_required_for_ready: bool | None = None


# ---------------------------------------------------------------------------
# Response bodies
# ---------------------------------------------------------------------------
class EntryPhaseRead(BaseModel):
    """One phase row within an entry's response payload."""

    model_config = ConfigDict(from_attributes=True)

    phase: PredictionPhase
    status: EntryStatus
    ready_at: datetime | None
    submitted_at: datetime | None
    locked_at: datetime | None
    status_reason: str | None = None


class EntryRead(BaseModel):
    """Full entry view including all phase rows."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    competition_id: uuid.UUID
    user_id: uuid.UUID
    reference: str
    display_name: str
    entry_number: int
    paid: bool
    prize_eligible: bool
    is_disabled: bool
    disabled_reason: str | None
    disabled_at: datetime | None
    disabled_by_user_id: uuid.UUID | None
    withdrawn_at: datetime | None
    withdrawn_reason: str | None
    created_at: datetime
    updated_at: datetime
    phases: list[EntryPhaseRead] = []


class EntryEventRead(BaseModel):
    """One audit row from `prediction_entry_events`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entry_id: uuid.UUID
    phase: PredictionPhase | None
    from_status: str
    to_status: str
    actor_user_id: uuid.UUID
    actor_role: str
    reason: str | None
    created_at: datetime


class EntrySettingsRead(BaseModel):
    """All 11 competition entry settings."""

    model_config = ConfigDict(from_attributes=True)

    max_entries_per_user: int
    auto_create_first_entry: bool
    allow_duplicate_from_existing: bool
    allow_user_rename: bool
    allow_user_withdrawal: bool
    require_ready_before_submit: bool
    payment_mode: PaymentMode
    block_unpaid_entry_submission: bool
    show_entry_reference_publicly: bool
    phase_scoped_status_enabled: bool
    bonus_questions_required_for_ready: bool


class Phase2OpenResponse(BaseModel):
    """Result of admin's `/phase2/open` action."""

    entries_opened: int
    entries_skipped_withdrawn: int
    entries_skipped_disabled: int
    entries_already_open: int


class AdminEntriesPage(BaseModel):
    """Paginated response from `GET /admin/entries`.

    `items` is the entries on the requested page. `total` is the count
    of rows matching the active filters before pagination — the
    frontend uses it to render "Showing X–Y of Z" and to enable / disable
    Prev / Next buttons.
    """

    items: list[EntryRead]
    total: int


class DuplicateConflict(BaseModel):
    """Raised when a user tries to submit an identical entry.

    The frontend can deep-link to the conflicting entry via reference.
    """

    detail: str
    conflict_reference: str


class CompletionCount(BaseModel):
    done: int
    total: int


class EntryCompletionSummary(BaseModel):
    entry_id: uuid.UUID
    groups: CompletionCount
    bracket: CompletionCount
    bonus: CompletionCount
    # The team the user has picked at `stage='winner'` in their bracket
    # prediction, or `None` if not yet predicted. Surfaced on the entries
    # list / card view so users can see their champion pick at a glance
    # without opening the wizard. Added 2026-06-01.
    predicted_winner: Optional[str] = None
