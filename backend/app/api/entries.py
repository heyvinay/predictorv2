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

import csv
import io
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.dependencies import AdminUser, CurrentUser, DbSession
from app.models._datetime import aware_utc, utc_now
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase

logger = logging.getLogger(__name__)
from app.schemas.entry import (
    AdminEntriesPage,
    AdminEntryOwner,
    AdminEntryRead,
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
from app.services.email import (
    send_entry_unlocked_email,
    send_submission_confirmation_email,
)
from app.services.entry_recap import build_entry_recap
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
    """List the current user's entries in the active competition.

    The ``updated_at`` field on each entry is the rolled-up "last
    activity" timestamp — see ``effective_updated_at_for_entries`` for
    why we don't just return ``PredictionEntry.updated_at`` raw.
    Computed read-side; no DB writes.
    """
    competition = await _get_competition(session)
    entries = await entries_service.list_user_entries(
        session, user=current_user, competition=competition
    )
    effective = await entries_service.effective_updated_at_for_entries(
        session, entries=entries
    )
    return [
        EntryRead.model_validate(e).model_copy(
            update={"updated_at": effective[e.id]}
        )
        for e in entries
    ]


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


@user_router.get("/completion", response_model=list[EntryCompletionSummary])
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

    # Submission confirmation email — best-effort. The entry is already
    # committed and audit-logged; failing the API call on a Resend outage
    # would tell the user "submission failed" when in fact it succeeded,
    # which is the worst outcome. Log and swallow.
    settings = get_settings()
    # The submission just committed milliseconds ago; using utc_now() avoids
    # having to relationship-load the phase row's submitted_at. "%d %b %Y,
    # %H:%M" → "27 May 2026, 14:32" — zero-padded day is portable across
    # platforms (Linux's %-d is not on Windows containers).
    submitted_at_display = utc_now().strftime("%d %b %Y, %H:%M")
    deep_link_url = f"{settings.frontend_url}/entries/{entry_id}"
    # Build the prediction recap for the email body. Best-effort: a failure
    # here drops to None so the email still sends without the recap section.
    recap: dict | None = None
    try:
        recap = await build_entry_recap(session, entry_id=entry_id)
    except Exception as e:  # noqa: BLE001 — recap is best-effort, don't fail the email
        logger.warning(
            "[submission] recap build failed for entry %s: %s",
            entry_id,
            e,
        )
    try:
        await send_submission_confirmation_email(
            to_email=current_user.email,
            player_name=current_user.name or current_user.email,
            entry_name=entry.display_name,
            entry_ref=entry.reference,
            submitted_at_display=submitted_at_display,
            deep_link_url=deep_link_url,
            recap=recap,
        )
    except Exception as e:  # noqa: BLE001 — email is best-effort
        logger.warning(
            "[submission] confirmation email failed for entry %s: %s",
            entry_id,
            e,
        )

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

    # Unlock notification email — best-effort. Safety-net for users who
    # unlock to tweak a pick, close the tab, and forget to re-submit:
    # without this notice the entry silently doesn't count.
    settings = get_settings()
    deadline = aware_utc(competition.phase1_deadline) if competition.phase1_deadline else None
    deadline_display = deadline.strftime("%d %b %Y, %H:%M UTC") if deadline else None
    deep_link_url = f"{settings.frontend_url}/entries/{entry_id}"
    try:
        await send_entry_unlocked_email(
            to_email=current_user.email,
            player_name=current_user.name or current_user.email,
            entry_name=entry.display_name,
            entry_ref=entry.reference,
            deadline_display=deadline_display,
            deep_link_url=deep_link_url,
        )
    except Exception as e:  # noqa: BLE001 — email is best-effort
        logger.warning(
            "[unlock] entry-unlocked email failed for entry %s: %s",
            entry_id,
            e,
        )

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
    search: str | None = Query(
        default=None,
        description="Case-insensitive substring match against either user email or entry reference.",
    ),
    status_: EntryStatus | None = Query(default=None, alias="status"),
    paid: bool | None = Query(default=None),
    disabled: bool | None = Query(default=None),
    modified_within: str | None = Query(
        default=None,
        description="'1h' | '24h' | '7d' | '30d' — filters entries with updated_at within the window. Unknown values are silently ignored.",
    ),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdminEntriesPage:
    """Paginated admin list. Pass `limit=None` (omit it) to return every
    matching row — used for CSV export. Otherwise client provides
    page-sized `limit` and `offset`; response carries the total.

    `search` is the user-facing free-text filter; it OR-matches user
    email and entry reference (Tweak 6 in
    stay-in-plan-mode-dynamic-adleman.md). `reference` is the legacy
    exact-match param — preserved for any existing bookmarked URLs.
    """
    competition = await _get_competition(session)
    rows, total = await entries_service.admin_list_entries(
        session,
        competition=competition,
        user_id=user_id,
        reference=reference,
        search=search,
        status=status_,
        paid=paid,
        disabled=disabled,
        modified_within=modified_within,
        limit=limit,
        offset=offset,
    )
    items: list[AdminEntryRead] = []
    for r in rows:
        item = AdminEntryRead.model_validate(r)
        if r.user is not None:
            item.owner = AdminEntryOwner.model_validate(r.user)
        items.append(item)
    return AdminEntriesPage(items=items, total=total)


class AdminEntriesStatsResponse(BaseModel):
    """Full entry-state breakdown for the /admin/entries stat cards.

    Added v2.160.5 to replace per-page-derived stats on the frontend
    (which only counted over the first 100 entries loaded for the
    table). All counts are GLOBAL to the active competition — the
    table's filter / paging state does not affect them.
    """

    total: int
    submitted: int
    drafts: int
    paid: int
    disabled_or_withdrawn: int


@admin_router.get("/entries/stats", response_model=AdminEntriesStatsResponse)
async def admin_entries_stats(
    session: DbSession,
    _admin: AdminUser,
) -> AdminEntriesStatsResponse:
    """Global entry-state breakdown for the active competition.

    Powers the four stat cards on /admin/entries (Total / Submitted /
    Paid / Disabled-Withdrawn) so the figures match the truth of the
    table rather than counting over the visible 100-row page. The
    Submitted figure uses the same canonical helper as the landing
    /api/landing/stats prize pot and the admin overview /admin/stats
    prize pool — see ``count_eligible_submitted_entries`` in
    services/entries.py.
    """
    competition = await _get_competition(session)
    stats = await entries_service.admin_entries_stats(
        session, competition=competition
    )
    return AdminEntriesStatsResponse(
        total=stats.total,
        submitted=stats.submitted,
        drafts=stats.drafts,
        paid=stats.paid,
        disabled_or_withdrawn=stats.disabled_or_withdrawn,
    )


# ---------------------------------------------------------------------------
# CSV export of all entries — admin tooling (v2.160.6)
# ---------------------------------------------------------------------------
# Columns (per request, mirroring the admin Entries page plus user-profile
# fields admin needs for reconciliation):
#   Reference · Entry Name · User Name · User Email · Works At ·
#   Atlas/JMFA Contact · Paid To · Status · Paid · Prize Eligibility ·
#   Created At · Last Modified
#
# Status logic mirrors the admin Entries page's `computeDisplayStatus`:
# "withdrawn" wins over disabled wins over phase_1.status.
#
# "Last Modified" uses the rolled-up effective timestamp from
# ``effective_updated_at_for_entries`` (v2.160.1) so the column matches
# what users see in the live UI rather than the raw DB column.
# ---------------------------------------------------------------------------
def _entry_csv_status(entry: PredictionEntry) -> str:
    """Effective display status. Mirrors frontend computeDisplayStatus +
    withdrawn / disabled overlays.

    Order of precedence:
      1. withdrawn (entry.withdrawn_at set)  → "withdrawn"
      2. disabled  (entry.is_disabled true)  → "disabled"
      3. phase_1 status                      → "submitted" / "draft" / etc
      4. fallback                            → "draft"
    """
    if entry.withdrawn_at is not None:
        return "withdrawn"
    if entry.is_disabled:
        return "disabled"
    phase_1 = next(
        (p for p in entry.phases if p.phase == PredictionPhase.PHASE_1), None
    )
    return phase_1.status.value if phase_1 is not None else "draft"


def _entry_csv_paid(entry: PredictionEntry) -> bool:
    """Effective paid — entry.paid OR owner-user.paid. Mirrors frontend
    isEffectivelyPaid; matches the helper used by the Submitted/Paid
    stat cards via admin_entries_stats."""
    if entry.paid:
        return True
    if entry.user is not None and entry.user.paid:
        return True
    return False


def _entry_csv_prize_eligibility(
    entry: PredictionEntry, paid: bool, status: str
) -> str:
    """Mirror frontend ``computePrizeEligibility``:

    - excluded — disabled / withdrawn / not prize_eligible / not submitted
    - pending  — eligible & submitted but unpaid
    - eligible — eligible & submitted & paid
    """
    if entry.is_disabled or entry.withdrawn_at is not None:
        return "excluded"
    if not entry.prize_eligible:
        return "excluded"
    if status != "submitted":
        return "excluded"
    return "eligible" if paid else "pending"


def _iso_or_blank(dt) -> str:
    """ISO 8601 with UTC offset, or blank if missing. ``aware_utc``
    defends against aiosqlite-stripped tzinfo (test runs); on prod
    Postgres the value is already aware so the call is a no-op."""
    if dt is None:
        return ""
    return aware_utc(dt).isoformat()


@admin_router.get("/entries/export.csv", response_class=Response)
async def admin_export_entries_csv(
    session: DbSession,
    _admin: AdminUser,
) -> Response:
    """CSV export of every entry in the active competition.

    Includes withdrawn / disabled entries (admin tooling needs the full
    audit picture, not just actively eligible). Sorted by entry_number
    so the export is stable run-to-run.

    Returns ``text/csv`` with a ``Content-Disposition: attachment``
    header so the browser downloads rather than displays. Filename
    embeds today's date for at-a-glance archive sorting.
    """
    competition = await _get_competition(session)

    # Load entries with user + phases eager-loaded. Single round-trip
    # via selectinload — N+1 free.
    result = await session.execute(
        select(PredictionEntry)
        .options(
            selectinload(PredictionEntry.user),
            selectinload(PredictionEntry.phases),
        )
        .where(PredictionEntry.competition_id == competition.id)
        .order_by(PredictionEntry.entry_number)
    )
    entries = list(result.scalars().all())

    # Rolled-up Last Modified — same source-of-truth that the entries
    # list UI uses (max of entry.updated_at, child predictions,
    # phase rows). See effective_updated_at_for_entries docstring.
    effective_updated = await entries_service.effective_updated_at_for_entries(
        session, entries=entries
    )

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "Reference",
            "Entry Name",
            "User Name",
            "User Email",
            "Works At",
            "Atlas/JMFA Contact",
            "Paid To",
            "Status",
            "Paid",
            "Prize Eligibility",
            "Created At",
            "Last Modified",
        ]
    )
    for entry in entries:
        u = entry.user
        status_value = _entry_csv_status(entry)
        paid_bool = _entry_csv_paid(entry)
        writer.writerow(
            [
                entry.reference,
                entry.display_name or "",
                u.name if u else "",
                u.email if u else "",
                u.employer.value if (u and u.employer) else "",
                u.company_contact if u else "",
                u.paid_to if u else "",
                status_value,
                "Yes" if paid_bool else "No",
                _entry_csv_prize_eligibility(entry, paid_bool, status_value),
                _iso_or_blank(entry.created_at),
                _iso_or_blank(effective_updated.get(entry.id, entry.updated_at)),
            ]
        )

    filename = f"entries-{utc_now().strftime('%Y-%m-%d')}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
