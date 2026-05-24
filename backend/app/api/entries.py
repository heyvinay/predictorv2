"""Prediction-entry HTTP endpoints.

Two routers live in this module:

- `user_router` — mounted at `/api/entries`, the user-facing surface.
- `admin_router` — mounted at `/api/admin`, the admin/competition-config
  surface. Routes inside this router require `AdminUser`.

The API layer is thin: it parses inputs, calls the service, and translates
typed service exceptions into HTTP status codes. All business logic lives
in `services/entries.py`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import AdminUser, CurrentUser, DbSession
from app.models.entry import EntryStatus
from app.models.prediction import PredictionPhase
from app.schemas.entry import (
    AdminEntriesPage,
    EntryCompletionSummary,
    EntryCreate,
    EntryDisable,
    EntryEventRead,
    EntryPaidUpdate,
    EntryPrizeEligibleUpdate,
    EntryRead,
    EntryReinstate,
    EntryRename,
    EntrySettingsRead,
    EntrySettingsUpdate,
    EntryWithdraw,
    Phase2OpenResponse,
)
from app.services import entries as entries_service
from app.services.audit import AuditContext, audit_context
from app.services.entries import (
    EntryAccessDeniedError,
    EntryConfigError,
    EntryDuplicateError,
    EntryLimitExceededError,
    EntryNotFoundError,
    EntryStateError,
    EntryValidationError,
)


user_router = APIRouter()
admin_router = APIRouter()


AuditCtx = Annotated[AuditContext, Depends(audit_context)]


# ---------------------------------------------------------------------------
# Exception → HTTP translation
# ---------------------------------------------------------------------------
def _raise_for(exc: Exception) -> None:
    """Convert a service-layer exception to an HTTPException."""
    if isinstance(exc, EntryNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, EntryAccessDeniedError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, EntryDuplicateError):
        # 409 with the conflicting reference attached so the frontend
        # can deep-link the user to their existing identical entry.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "conflict_reference": exc.conflict_reference,
            },
        )
    if isinstance(exc, EntryLimitExceededError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, EntryStateError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, EntryValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    if isinstance(exc, EntryConfigError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    raise exc  # let unknown errors bubble to FastAPI's 500 handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_competition(session: AsyncSession):
    try:
        return await entries_service.get_active_competition(session)
    except EntryConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------
@user_router.get("", response_model=list[EntryRead])
async def list_entries(
    session: DbSession, current_user: CurrentUser
) -> list[EntryRead]:
    """List the current user's entries in the active competition."""
    competition = await _get_competition(session)
    entries = await entries_service.list_user_entries(
        session, user=current_user, competition=competition
    )
    return [EntryRead.model_validate(e) for e in entries]


@user_router.post(
    "", response_model=EntryRead, status_code=status.HTTP_201_CREATED
)
async def create_entry(
    payload: EntryCreate,
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> EntryRead:
    """Create a new draft entry."""
    competition = await _get_competition(session)
    try:
        entry = await entries_service.create_entry(
            session,
            user=current_user,
            competition=competition,
            display_name=payload.display_name,
            ctx=ctx,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@user_router.get("/settings", response_model=EntrySettingsRead)
async def get_user_entry_settings(
    session: DbSession, _current_user: CurrentUser
) -> EntrySettingsRead:
    """Read-only view of the active competition's entry settings.

    Mirrors the admin endpoint but requires only an authenticated user.
    The frontend reads this to decide whether to show the multi-entry
    selector (`max_entries_per_user > 1`) and which user actions
    (rename, duplicate, withdraw) to expose.
    """
    competition = await _get_competition(session)
    return EntrySettingsRead.model_validate(competition)


@user_router.get("/completion-summary", response_model=list[EntryCompletionSummary])
async def get_completion_summary(
    session: DbSession, current_user: CurrentUser
) -> list[EntryCompletionSummary]:
    """Per-entry completion counts for the current user's entries.

    Returns one object per entry with group / bracket / bonus done+total
    counts. Used by the /entries list page to render progress indicators
    without fetching every prediction row.
    """
    competition = await _get_competition(session)
    rows = await entries_service.get_completion_summary(
        session, user=current_user, competition=competition
    )
    return [EntryCompletionSummary.model_validate(r) for r in rows]


@user_router.get("/{entry_id}", response_model=EntryRead)
async def get_entry(
    entry_id: uuid.UUID, session: DbSession, current_user: CurrentUser
) -> EntryRead:
    """Read a single entry.

    Visibility: owner + admin always; other users only after the
    competition's Phase 1 deadline has passed and the entry is eligible.
    Disabled and withdrawn entries are never visible to outsiders.
    """
    try:
        entry = await entries_service.get_entry_for_view(
            session, entry_id=entry_id, viewer=current_user
        )
    except Exception as exc:
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@user_router.patch("/{entry_id}", response_model=EntryRead)
async def rename_entry(
    entry_id: uuid.UUID,
    payload: EntryRename,
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> EntryRead:
    competition = await _get_competition(session)
    try:
        entry = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=current_user
        )
        entry = await entries_service.rename_entry(
            session,
            entry=entry,
            user=current_user,
            new_name=payload.display_name,
            competition=competition,
            ctx=ctx,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@user_router.post(
    "/{entry_id}/duplicate",
    response_model=EntryRead,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_entry(
    entry_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> EntryRead:
    competition = await _get_competition(session)
    try:
        source = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=current_user
        )
        new_entry = await entries_service.duplicate_entry(
            session,
            source=source,
            user=current_user,
            competition=competition,
            ctx=ctx,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(new_entry)


# ---------------------------------------------------------------------------
# Lifecycle: user submits / edits an entry. Two transitions only.
#   POST /entries/{id}/submit  → DRAFT → SUBMITTED   (qualifies for scoring)
#   POST /entries/{id}/edit    → SUBMITTED → DRAFT   (revert; before deadline)
# Mark-Ready and user-Withdraw were removed in the lifecycle simplification.
# ---------------------------------------------------------------------------
@user_router.post("/{entry_id}/submit", response_model=EntryRead)
async def submit_entry(
    entry_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> EntryRead:
    competition = await _get_competition(session)
    try:
        entry = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=current_user
        )
        await entries_service.submit_entry(
            session,
            entry=entry,
            user=current_user,
            competition=competition,
            ctx=ctx,
        )
        await session.commit()
        entry = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=current_user
        )
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@user_router.post("/{entry_id}/edit", response_model=EntryRead)
async def edit_entry(
    entry_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> EntryRead:
    """SUBMITTED → DRAFT. Only allowed before competition start."""
    competition = await _get_competition(session)
    try:
        entry = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=current_user
        )
        await entries_service.edit_entry(
            session,
            entry=entry,
            user=current_user,
            competition=competition,
            ctx=ctx,
        )
        await session.commit()
        entry = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=current_user
        )
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@user_router.post("/{entry_id}/withdraw", response_model=EntryRead)
async def withdraw_entry(
    entry_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> EntryRead:
    """DRAFT → WITHDRAWN. User-initiated, before competition start."""
    competition = await _get_competition(session)
    try:
        entry = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=current_user
        )
        entry = await entries_service.withdraw_entry(
            session,
            entry=entry,
            user=current_user,
            competition=competition,
            ctx=ctx,
        )
        await session.commit()
        entry = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=current_user
        )
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@user_router.post("/{entry_id}/reinstate", response_model=EntryRead)
async def reinstate_entry(
    entry_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
    ctx: AuditCtx,
) -> EntryRead:
    """WITHDRAWN → DRAFT. User-initiated, before competition start."""
    competition = await _get_competition(session)
    try:
        entry = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=current_user
        )
        entry = await entries_service.reinstate_entry(
            session,
            entry=entry,
            user=current_user,
            competition=competition,
            ctx=ctx,
        )
        await session.commit()
        entry = await entries_service.get_entry(
            session, entry_id=entry_id, requesting_user=current_user
        )
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


# ---------------------------------------------------------------------------
# Admin endpoints — mounted at /api/admin
# ---------------------------------------------------------------------------
@admin_router.get(
    "/competition/entry-settings", response_model=EntrySettingsRead
)
async def admin_get_entry_settings(
    session: DbSession, _admin: AdminUser
) -> EntrySettingsRead:
    competition = await _get_competition(session)
    return EntrySettingsRead.model_validate(competition)


@admin_router.patch(
    "/competition/entry-settings", response_model=EntrySettingsRead
)
async def admin_update_entry_settings(
    payload: EntrySettingsUpdate,
    session: DbSession,
    admin: AdminUser,
    ctx: AuditCtx,
) -> EntrySettingsRead:
    competition = await _get_competition(session)
    updates = payload.model_dump(exclude_unset=True)
    try:
        competition = await entries_service.update_entry_settings(
            session,
            competition=competition,
            admin=admin,
            updates=updates,
            ctx=ctx,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntrySettingsRead.model_validate(competition)


@admin_router.post(
    "/competition/phase2/open", response_model=Phase2OpenResponse
)
async def admin_open_phase2(
    session: DbSession, admin: AdminUser, ctx: AuditCtx
) -> Phase2OpenResponse:
    competition = await _get_competition(session)
    try:
        summary = await entries_service.admin_open_phase2(
            session, admin=admin, competition=competition, ctx=ctx
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return Phase2OpenResponse(**summary.__dict__)


@admin_router.get("/entries", response_model=AdminEntriesPage)
async def admin_list_entries(
    session: DbSession,
    _admin: AdminUser,
    user_id: uuid.UUID | None = Query(default=None),
    reference: str | None = Query(default=None),
    status_: EntryStatus | None = Query(default=None, alias="status"),
    paid: bool | None = Query(default=None),
    disabled: bool | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdminEntriesPage:
    """Paginated admin list. Pass `limit=None` (omit it) to return every
    matching row — used for CSV export. Otherwise client provides
    page-sized `limit` and `offset`; response carries the total."""
    competition = await _get_competition(session)
    rows, total = await entries_service.admin_list_entries(
        session,
        competition=competition,
        user_id=user_id,
        reference=reference,
        status=status_,
        paid=paid,
        disabled=disabled,
        limit=limit,
        offset=offset,
    )
    return AdminEntriesPage(
        items=[EntryRead.model_validate(r) for r in rows],
        total=total,
    )


@admin_router.post(
    "/entries/{entry_id}/withdraw", response_model=EntryRead
)
async def admin_withdraw_entry(
    entry_id: uuid.UUID,
    payload: EntryWithdraw,
    session: DbSession,
    admin: AdminUser,
    ctx: AuditCtx,
) -> EntryRead:
    """Admin withdraws an entry. Reason mandatory. Allowed from DRAFT or
    SUBMITTED. Reversible via /reinstate."""
    try:
        entry = await entries_service.get_entry(
            session,
            entry_id=entry_id,
            requesting_user=admin,
            allow_admin=True,
        )
        entry = await entries_service.admin_withdraw_entry(
            session, entry=entry, admin=admin, reason=payload.reason, ctx=ctx
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@admin_router.post(
    "/entries/{entry_id}/reinstate", response_model=EntryRead
)
async def admin_reinstate_entry(
    entry_id: uuid.UUID,
    payload: EntryReinstate,
    session: DbSession,
    admin: AdminUser,
    ctx: AuditCtx,
) -> EntryRead:
    """Admin reinstates a withdrawn entry to SUBMITTED. Reason mandatory.
    Rescue path for users who filled everything but forgot to click Submit."""
    try:
        entry = await entries_service.get_entry(
            session,
            entry_id=entry_id,
            requesting_user=admin,
            allow_admin=True,
        )
        entry = await entries_service.admin_reinstate_entry(
            session, entry=entry, admin=admin, reason=payload.reason, ctx=ctx
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@admin_router.post(
    "/entries/{entry_id}/disable", response_model=EntryRead
)
async def admin_disable_entry(
    entry_id: uuid.UUID,
    payload: EntryDisable,
    session: DbSession,
    admin: AdminUser,
    ctx: AuditCtx,
) -> EntryRead:
    try:
        entry = await entries_service.get_entry(
            session,
            entry_id=entry_id,
            requesting_user=admin,
            allow_admin=True,
        )
        entry = await entries_service.admin_disable_entry(
            session, entry=entry, admin=admin, reason=payload.reason, ctx=ctx
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@admin_router.post("/entries/{entry_id}/enable", response_model=EntryRead)
async def admin_enable_entry(
    entry_id: uuid.UUID,
    session: DbSession,
    admin: AdminUser,
    ctx: AuditCtx,
) -> EntryRead:
    try:
        entry = await entries_service.get_entry(
            session,
            entry_id=entry_id,
            requesting_user=admin,
            allow_admin=True,
        )
        entry = await entries_service.admin_enable_entry(
            session, entry=entry, admin=admin, ctx=ctx
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@admin_router.patch("/entries/{entry_id}/paid", response_model=EntryRead)
async def admin_set_paid(
    entry_id: uuid.UUID,
    payload: EntryPaidUpdate,
    session: DbSession,
    admin: AdminUser,
    ctx: AuditCtx,
) -> EntryRead:
    try:
        entry = await entries_service.get_entry(
            session,
            entry_id=entry_id,
            requesting_user=admin,
            allow_admin=True,
        )
        entry = await entries_service.admin_set_paid(
            session, entry=entry, admin=admin, paid=payload.paid, ctx=ctx
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@admin_router.patch(
    "/entries/{entry_id}/prize-eligible", response_model=EntryRead
)
async def admin_set_prize_eligible(
    entry_id: uuid.UUID,
    payload: EntryPrizeEligibleUpdate,
    session: DbSession,
    admin: AdminUser,
    ctx: AuditCtx,
) -> EntryRead:
    try:
        entry = await entries_service.get_entry(
            session,
            entry_id=entry_id,
            requesting_user=admin,
            allow_admin=True,
        )
        entry = await entries_service.admin_set_prize_eligible(
            session,
            entry=entry,
            admin=admin,
            prize_eligible=payload.prize_eligible,
            ctx=ctx,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _raise_for(exc)
    return EntryRead.model_validate(entry)


@admin_router.get(
    "/entries/{entry_id}/events", response_model=list[EntryEventRead]
)
async def admin_get_events(
    entry_id: uuid.UUID, session: DbSession, _admin: AdminUser
) -> list[EntryEventRead]:
    try:
        entry = await entries_service.get_entry(
            session,
            entry_id=entry_id,
            requesting_user=_admin,
            allow_admin=True,
        )
        events = await entries_service.admin_get_events(session, entry=entry)
    except Exception as exc:
        _raise_for(exc)
    return [EntryEventRead.model_validate(e) for e in events]
