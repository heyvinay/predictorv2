"""Entry-management service.

This module is the single source of truth for prediction-entry business
logic. The API layer (`backend/app/api/entries.py`) translates HTTP into
calls here; the service raises typed exceptions that the API turns into
status codes.

Key invariants enforced here (never in the API layer):
- `max_entries_per_user` limit
- Ownership checks (a user can only mutate their own entries; admins
  bypass via `allow_admin=True`)
- State machine: only the transitions in `_ALLOWED_TRANSITIONS` are
  permitted
- Phase lock — once a phase deadline passes (or its status is `locked`)
  no edits are allowed
- Duplicate-submission rule — `submit` is rejected if another eligible
  entry owned by the same user in the same competition has identical
  predictions for the same phase
- Audit-event writes — every state change writes to BOTH
  `prediction_entry_events` (entry-specific timeline) and `audit_events`
  (global log) in the same transaction
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models._datetime import aware_utc, utc_now
from app.models.audit import AuditEvent  # noqa: F401  (imported for type clarity)
from app.models.bonus import BonusPrediction
from app.models.competition import Competition
from app.models.entry import (
    ActorRole,
    EntryStatus,
    PredictionEntry,
    PredictionEntryEvent,
    PredictionEntryPhase,
)
from app.models.prediction import (
    MatchPrediction,
    PredictionPhase,
    TeamPrediction,
    normalize_stage,
)
from app.models.user import User
from app.services.audit import AuditContext, record_audit_event


# ---------------------------------------------------------------------------
# Exceptions — typed so the API layer can map them to HTTP status codes
# ---------------------------------------------------------------------------
class EntryError(Exception):
    """Base class for entry-service errors."""


class EntryNotFoundError(EntryError):
    """The requested entry does not exist."""


class EntryAccessDeniedError(EntryError):
    """The requester does not own this entry (and isn't an admin)."""


class EntryStateError(EntryError):
    """Illegal state transition or status mismatch."""


class EntryLimitExceededError(EntryError):
    """User would exceed `max_entries_per_user`."""


class EntryValidationError(EntryError):
    """Entry fails a precondition (incomplete predictions, unpaid, etc.)."""


class EntryDuplicateError(EntryError):
    """Identical predictions to another eligible entry of the same user."""

    def __init__(self, message: str, conflict_reference: str):
        super().__init__(message)
        self.conflict_reference = conflict_reference


class EntryConfigError(EntryError):
    """Invalid settings update (e.g. max_entries below current count)."""


# ---------------------------------------------------------------------------
# State machine — exact transitions allowed at the phase level.
# Key: (from_status, to_status); value: roles permitted.
# ---------------------------------------------------------------------------
_ALLOWED_TRANSITIONS: dict[tuple[EntryStatus, EntryStatus], set[ActorRole]] = {
    (EntryStatus.DRAFT, EntryStatus.SUBMITTED): {ActorRole.USER, ActorRole.ADMIN},
    (EntryStatus.SUBMITTED, EntryStatus.DRAFT): {ActorRole.USER, ActorRole.ADMIN},
    (EntryStatus.DRAFT, EntryStatus.WITHDRAWN): {ActorRole.USER, ActorRole.ADMIN, ActorRole.SYSTEM},
    (EntryStatus.SUBMITTED, EntryStatus.WITHDRAWN): {ActorRole.ADMIN},
    (EntryStatus.WITHDRAWN, EntryStatus.SUBMITTED): {ActorRole.ADMIN},
    # User reinstate: goes back to DRAFT (not SUBMITTED) so they can review before re-submitting.
    (EntryStatus.WITHDRAWN, EntryStatus.DRAFT): {ActorRole.USER},
    # `is_disabled` is an orthogonal admin flag — never changes status.
    # WITHDRAWN is non-terminal: admins can reinstate via `admin_reinstate_entry`.
}


# ---------------------------------------------------------------------------
# Reference generation
# ---------------------------------------------------------------------------
def _ref_prefix(competition: Competition) -> str:
    """Build the textual prefix for entry references.

    Format: `{external_id_upper}{2-digit year}-`. Falls back to first
    four uppercase letters of competition name when `external_id` is
    missing. Example: competition external_id='WC' → `WC26-`.
    """
    if competition.external_id:
        code = competition.external_id.upper()
    else:
        # Derive from name when external_id is unset. Strip non-alpha
        # so e.g. "FIFA World Cup 2026" → "FIFA".
        clean = "".join(c for c in competition.name if c.isalpha()).upper()
        code = clean[:4] or "COMP"
    year = (competition.created_at.year if competition.created_at else utc_now().year) % 100
    return f"{code}{year:02d}-"


async def _next_reference_number(
    session: AsyncSession, competition: Competition
) -> int:
    """Allocate the next reference sequence for this competition.

    Uses a `SELECT … FOR UPDATE` on the competition row to serialize
    concurrent allocations. Then counts existing entries — simple and
    correct given the small competition scale (~30 users).
    """
    # Lock the competition row to serialize concurrent reference
    # allocations. Two simultaneous POST /api/entries calls otherwise
    # race on the COUNT(*).
    locked = (
        await session.execute(
            select(Competition)
            .where(Competition.id == competition.id)
            .with_for_update()
        )
    ).scalar_one()
    count = (
        await session.execute(
            select(func.count(PredictionEntry.id)).where(
                PredictionEntry.competition_id == locked.id
            )
        )
    ).scalar_one()
    return count + 1


async def _generate_reference(
    session: AsyncSession, competition: Competition
) -> str:
    """Returns a unique reference like `WC26-000001`."""
    seq = await _next_reference_number(session, competition)
    return f"{_ref_prefix(competition)}{seq:06d}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _count_user_entries(
    session: AsyncSession, user_id: uuid.UUID, competition_id: uuid.UUID
) -> int:
    """Active entries: not withdrawn, regardless of is_disabled."""
    result = await session.execute(
        select(func.count(PredictionEntry.id)).where(
            PredictionEntry.user_id == user_id,
            PredictionEntry.competition_id == competition_id,
            PredictionEntry.withdrawn_at.is_(None),
        )
    )
    return result.scalar_one()


async def _next_entry_number(
    session: AsyncSession, user_id: uuid.UUID, competition_id: uuid.UUID
) -> int:
    """Highest existing entry_number + 1 (does not skip withdrawn slots)."""
    result = await session.execute(
        select(func.coalesce(func.max(PredictionEntry.entry_number), 0)).where(
            PredictionEntry.user_id == user_id,
            PredictionEntry.competition_id == competition_id,
        )
    )
    return int(result.scalar_one()) + 1


async def _ensure_owner(
    entry: PredictionEntry,
    requesting_user: User,
    *,
    allow_admin: bool = False,
) -> None:
    """Raise `EntryAccessDeniedError` if the user can't act on this entry."""
    if entry.user_id == requesting_user.id:
        return
    if allow_admin and requesting_user.is_admin:
        return
    raise EntryAccessDeniedError(
        f"User {requesting_user.id} cannot access entry {entry.id}"
    )


async def check_entry_visibility(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    viewer: User | None,
) -> None:
    """Raise `EntryAccessDeniedError` if `viewer` may not READ `entry`.

    Less strict than :func:`_ensure_owner`. Read-only callers (the public
    leaderboard breakdown, profile views, trajectory) use this so the
    "blind pool" rule is enforced consistently:

    - Admins: always allowed (forensics / support).
    - Owner: allowed for their own active or *withdrawn* entries —
      withdrawn is a user-initiated, reversible state and the owner must
      still see it to reinstate. BLOCKED on their own *disabled* entry
      so disable means "as if the entry never existed" (ghost mode).
    - Non-owner / unauthenticated: allowed iff the competition's Phase 1
      deadline has passed AND the entry is eligible (not disabled, not
      withdrawn).

    The lock signal is :func:`app.services.locking.is_phase1_locked`. Once
    that passes, all prediction contents are public knowledge and rank
    standings can be shared without compromising the blind pool.

    Check order is load-bearing:
      1. Admin bypass (unconditional — admins always see).
      2. Owner branch — return unless their own entry is disabled
         (withdrawn entries stay visible to the owner so they can
         reinstate; admins use a separate withdrawn-visible flow).
      3. Disabled / withdrawn check for any remaining non-owner.
      4. Blind pool check (`is_phase1_locked`).
    Do not reorder — non-owners must continue to fall through to the
    blind-pool gate untouched.
    """
    if viewer is not None:
        if viewer.is_admin:
            return
        if entry.user_id == viewer.id:
            if entry.is_disabled:
                raise EntryAccessDeniedError(
                    f"Entry {entry.id} is not visible to its owner"
                )
            return
    if entry.is_disabled or entry.withdrawn_at is not None:
        raise EntryAccessDeniedError(
            f"Entry {entry.id} is not publicly visible"
        )
    # Local import to keep the locking <-> entries dependency direction
    # clear (locking knows nothing about entries; entries depends on locking).
    from app.services.locking import is_phase1_locked

    if not await is_phase1_locked(session):
        raise EntryAccessDeniedError(
            f"Entry {entry.id} is not yet publicly visible"
        )


async def get_entry_for_view(
    session: AsyncSession,
    *,
    entry_id: uuid.UUID,
    viewer: User | None,
) -> PredictionEntry:
    """Load `entry_id` and enforce read-only visibility rules.

    Use this for endpoints that DISPLAY an entry but don't mutate it
    (entry detail, breakdown, trajectory, profile view). For mutating
    endpoints, use :func:`get_entry` which insists on ownership.
    """
    entry = await _load_entry_with_phases(session, entry_id)
    await check_entry_visibility(session, entry=entry, viewer=viewer)
    return entry


def _phase_record(
    entry: PredictionEntry, phase: PredictionPhase
) -> PredictionEntryPhase:
    """Return the phase row, or raise if missing."""
    for p in entry.phases:
        if p.phase == phase:
            return p
    raise EntryStateError(
        f"Entry {entry.reference} has no record for phase {phase.value}"
    )


def _phase_is_locked(
    phase_row: PredictionEntryPhase, competition: Competition
) -> bool:
    """A phase is locked when its deadline has passed.

    `LOCKED` status was removed in the lifecycle simplification — locking is
    now purely time-based. Once `competition.phase1_deadline` is in the past,
    edits are blocked and any remaining DRAFT entries get auto-withdrawn by
    `flip_drafts_past_deadline` (run every 60s by the scheduler).
    """
    now = utc_now()
    deadline = (
        competition.phase1_deadline
        if phase_row.phase == PredictionPhase.PHASE_1
        else competition.phase2_deadline
    )
    if deadline is not None and aware_utc(now) >= aware_utc(deadline):
        return True
    return False


async def _write_transition_event(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    phase: PredictionPhase | None,
    from_status: EntryStatus,
    to_status: EntryStatus,
    actor_user_id: uuid.UUID,
    actor_role: ActorRole,
    reason: str | None,
    audit_event_type: str,
    ctx: AuditContext | None,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """Write both `PredictionEntryEvent` and `AuditEvent` rows.

    The entry-specific event powers the per-entry timeline endpoint.
    The audit event powers the global audit log. Same transaction —
    they can never disagree.
    """
    entry_event = PredictionEntryEvent(
        entry_id=entry.id,
        phase=phase,
        from_status=from_status.value,
        to_status=to_status.value,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        reason=reason,
    )
    session.add(entry_event)

    metadata: dict[str, Any] = {
        "from_status": from_status.value,
        "to_status": to_status.value,
        "reference": entry.reference,
    }
    if phase is not None:
        metadata["phase"] = phase.value
    if extra_metadata:
        metadata.update(extra_metadata)
    record_audit_event(
        session,
        event_type=audit_event_type,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata=metadata,
        reason=reason,
    )


async def _load_entry_with_phases(
    session: AsyncSession, entry_id: uuid.UUID
) -> PredictionEntry:
    """Eager-loads phases. Raises `EntryNotFoundError` if missing."""
    result = await session.execute(
        select(PredictionEntry)
        .options(selectinload(PredictionEntry.phases))
        .where(PredictionEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise EntryNotFoundError(f"Entry {entry_id} not found")
    return entry


# ---------------------------------------------------------------------------
# Public API — entry CRUD
# ---------------------------------------------------------------------------
async def create_entry(
    session: AsyncSession,
    *,
    user: User,
    competition: Competition,
    display_name: str | None = None,
    actor_role: ActorRole = ActorRole.USER,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    """Create a new draft entry for `user` in `competition`.

    Allocates a sequential reference + entry_number. Spawns both
    phase_1 and phase_2 phase rows in status `draft`. Writes an
    `entry.created` audit event.
    """
    # Door policy (v2.166.0): no new entries once the deadline passes.
    # A post-deadline draft could never be submitted (submit is
    # time-locked) and would be auto-withdrawn within a minute.
    if competition.phase1_deadline is not None and aware_utc(
        utc_now()
    ) >= aware_utc(competition.phase1_deadline):
        raise EntryStateError(
            "Entries are closed — the deadline has passed."
        )

    # Enforce max-entries-per-user. Withdrawn entries don't count.
    active = await _count_user_entries(session, user.id, competition.id)
    if active >= competition.max_entries_per_user:
        raise EntryLimitExceededError(
            f"User already has {active} active entries; "
            f"limit is {competition.max_entries_per_user}"
        )

    entry_number = await _next_entry_number(session, user.id, competition.id)
    reference = await _generate_reference(session, competition)
    chosen_name = display_name.strip() if display_name else f"Entry {entry_number}"

    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=reference,
        display_name=chosen_name,
        entry_number=entry_number,
    )
    session.add(entry)
    await session.flush()  # populate entry.id for phase FKs

    # Both phase rows start as draft. This is true even in
    # whole-competition mode — the phase rows are always present
    # internally; only the UX surface differs.
    phase_rows = [
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.DRAFT,
        ),
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_2,
            status=EntryStatus.DRAFT,
        ),
    ]
    session.add_all(phase_rows)

    record_audit_event(
        session,
        event_type="entry.created",
        actor_user_id=user.id,
        actor_role=actor_role,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata={
            "reference": entry.reference,
            "entry_number": entry.entry_number,
            "display_name": entry.display_name,
        },
    )

    await session.flush()
    # Refresh so .phases relationship is populated for the response.
    await session.refresh(entry, attribute_names=["phases"])
    return entry


async def list_user_entries(
    session: AsyncSession, *, user: User, competition: Competition
) -> list[PredictionEntry]:
    """All entries owned by `user` in `competition`, with phases.

    Disabled entries (`is_disabled=true`) are excluded — once an admin
    disables an entry it disappears from the owner's view entirely
    ("ghost mode"). Admin tooling (`admin_list_entries`) keeps its own
    explicit filter and still sees everything.
    """
    result = await session.execute(
        select(PredictionEntry)
        .options(selectinload(PredictionEntry.phases))
        .where(
            PredictionEntry.user_id == user.id,
            PredictionEntry.competition_id == competition.id,
            PredictionEntry.is_disabled == False,  # noqa: E712
        )
        .order_by(PredictionEntry.entry_number)
    )
    return list(result.scalars().all())


async def effective_updated_at_for_entries(
    session: AsyncSession,
    *,
    entries: Sequence[PredictionEntry],
) -> dict[uuid.UUID, datetime]:
    """For each entry, the latest of its own ``updated_at``, the most
    recent **phase-1** child prediction's ``updated_at`` (match / team /
    bonus), and the most recent **phase-1** ``prediction_entry_phases``
    row's ``updated_at``.

    Background: ``PredictionEntry.updated_at`` only ticks on entry-level
    actions (rename, withdraw / reinstate, admin disable / re-enable,
    paid / prize-eligible toggle). Prediction edits bump the child row
    only; submit / edit transitions bump the phase row only. Without
    this rollup the entries-list "Updated" column shows the entry's
    creation time, not real activity.

    PHASES rule (CLAUDE.md ★): every query and iteration in this helper
    filters to PHASE_1. Phase 2 is permanently dormant — counting its
    rows here was a latent rule violation that this 2.160.7 revision
    closes. In practice phase_2 timestamps for the current competition
    are pinned to entry-creation time and never win the MAX, so the
    observable output is unchanged.

    Returns a map ``{entry_id: effective_updated_at}``. Empty input
    returns ``{}``.

    Performance: three GROUP-BY-MAX queries (one per child table),
    scoped by ``entry_id IN (...)`` against indexed FK columns. Phase
    rows are read from the loaded ``entry.phases`` relationship — no
    extra query — so callers that already eager-loaded phases (e.g.
    ``list_user_entries``) pay nothing for that source.

    Datetime contract: every returned value is coerced through
    ``aware_utc`` so aiosqlite-backed tests see ``tzinfo=UTC`` like
    Postgres does. See CLAUDE.md "Datetime rule (system-wide)".
    """
    if not entries:
        return {}

    entry_ids = [e.id for e in entries]
    result: dict[uuid.UUID, datetime] = {
        e.id: aware_utc(e.updated_at) for e in entries
    }

    # MAX(updated_at) from each child prediction table, scoped by
    # entry_id AND phase (where the model has a phase column —
    # BonusPrediction doesn't, so it's unfiltered). PHASE_1 filter
    # enforces the CLAUDE.md PHASES rule even though no phase_2 child
    # predictions are ever created today (get_current_phase always
    # returns PHASE_1 while is_phase2_active is False).
    for child_model in (MatchPrediction, TeamPrediction, BonusPrediction):
        query = select(
            child_model.entry_id,
            func.max(child_model.updated_at),
        ).where(child_model.entry_id.in_(entry_ids))
        if hasattr(child_model, "phase"):
            query = query.where(child_model.phase == PredictionPhase.PHASE_1)
        query = query.group_by(child_model.entry_id)
        rows = (await session.execute(query)).all()
        for entry_id, ts in rows:
            if ts is None:
                continue
            ts_aware = aware_utc(ts)
            if ts_aware > result[entry_id]:
                result[entry_id] = ts_aware

    # Phase rows are expected to be eager-loaded by callers
    # (selectinload(PredictionEntry.phases) in list_user_entries). Read
    # from the loaded relationship to skip an extra DB round-trip.
    # PHASE_1 filter enforces CLAUDE.md PHASES rule — phase_2 rows are
    # ignored even though they're loaded.
    for entry in entries:
        for phase_row in entry.phases:
            if phase_row.phase != PredictionPhase.PHASE_1:
                continue
            ts_aware = aware_utc(phase_row.updated_at)
            if ts_aware > result[entry.id]:
                result[entry.id] = ts_aware

    return result


@dataclass
class AdminEntriesStats:
    """Full entry-state breakdown for the admin /admin/entries stat cards.

    Each count is global to the given competition (NOT filtered by the
    admin page's current table view). The page's stat cards become
    drill-in shortcuts whose values stay stable as the table is
    filtered — fixing the v2.160.x bug where the cards counted over a
    paginated 100-row subset rather than the whole table.
    """

    total: int
    submitted: int
    drafts: int
    paid: int
    disabled_or_withdrawn: int


async def count_eligible_submitted_entries(
    session: AsyncSession,
    *,
    competition: Competition,
) -> int:
    """Canonical "actively eligible submitted entries" count for the
    given competition. Single source of truth.

    An entry counts when ALL of:
      • belongs to ``competition``
      • PHASE_1 phase row has status SUBMITTED  ← CLAUDE.md PHASES rule
      • ``withdrawn_at`` is NULL
      • ``is_disabled`` is False

    Callers:
      • ``backend/app/api/landing.py``       — prize_pot
      • ``backend/app/api/admin.py`` /stats  — prize_pool
      • ``admin_entries_stats`` below        — Submitted stat card

    Co-locating the query here eliminates the drift class — historically
    three call sites had independently-evolving versions of this filter
    and disagreed on the result. See the test class for the failure
    modes (phase_2 double-count, withdrawn/disabled leak, cross-comp).
    """
    return (
        await session.scalar(
            select(func.count(func.distinct(PredictionEntry.id)))
            .join(
                PredictionEntryPhase,
                PredictionEntryPhase.entry_id == PredictionEntry.id,
            )
            .where(PredictionEntry.competition_id == competition.id)
            .where(PredictionEntryPhase.phase == PredictionPhase.PHASE_1)
            .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
            .where(PredictionEntry.withdrawn_at.is_(None))
            .where(PredictionEntry.is_disabled.is_(False))
        )
    ) or 0


async def admin_entries_stats(
    session: AsyncSession,
    *,
    competition: Competition,
) -> AdminEntriesStats:
    """Full entry-state breakdown for the /admin/entries page's stat
    cards. All counts scoped to ``competition``; every phase-row join
    filters PHASE_1 per the CLAUDE.md rule.

    Definitions:
      • total                 — all entries in this competition
      • submitted             — actively eligible, PHASE_1 SUBMITTED
                                (see ``count_eligible_submitted_entries``)
      • drafts                — actively eligible, PHASE_1 DRAFT
      • paid                  — submitted AND (entry.paid OR user.paid).
                                Mirrors the frontend's
                                ``isEffectivelyPaid`` helper in
                                ``frontend/src/routes/admin/entries/+page.svelte``.
      • disabled_or_withdrawn — ``is_disabled OR withdrawn_at IS NOT NULL``

    Four cheap COUNT queries; sub-ms at competition scale. Could be one
    query with SUM(CASE WHEN ...) for further optimization if profiling
    flags it — not needed now.
    """
    total = (
        await session.scalar(
            select(func.count(PredictionEntry.id)).where(
                PredictionEntry.competition_id == competition.id
            )
        )
    ) or 0

    submitted = await count_eligible_submitted_entries(
        session, competition=competition
    )

    drafts = (
        await session.scalar(
            select(func.count(func.distinct(PredictionEntry.id)))
            .join(
                PredictionEntryPhase,
                PredictionEntryPhase.entry_id == PredictionEntry.id,
            )
            .where(PredictionEntry.competition_id == competition.id)
            .where(PredictionEntryPhase.phase == PredictionPhase.PHASE_1)
            .where(PredictionEntryPhase.status == EntryStatus.DRAFT)
            .where(PredictionEntry.withdrawn_at.is_(None))
            .where(PredictionEntry.is_disabled.is_(False))
        )
    ) or 0

    # Effective-paid: entry.paid OR owner-user.paid. Join the users
    # table so we can OR across the two columns.
    paid = (
        await session.scalar(
            select(func.count(func.distinct(PredictionEntry.id)))
            .join(
                PredictionEntryPhase,
                PredictionEntryPhase.entry_id == PredictionEntry.id,
            )
            .join(User, User.id == PredictionEntry.user_id)
            .where(PredictionEntry.competition_id == competition.id)
            .where(PredictionEntryPhase.phase == PredictionPhase.PHASE_1)
            .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
            .where(PredictionEntry.withdrawn_at.is_(None))
            .where(PredictionEntry.is_disabled.is_(False))
            .where(or_(PredictionEntry.paid.is_(True), User.paid.is_(True)))
        )
    ) or 0

    disabled_or_withdrawn = (
        await session.scalar(
            select(func.count(PredictionEntry.id))
            .where(PredictionEntry.competition_id == competition.id)
            .where(
                or_(
                    PredictionEntry.is_disabled.is_(True),
                    PredictionEntry.withdrawn_at.is_not(None),
                )
            )
        )
    ) or 0

    return AdminEntriesStats(
        total=total,
        submitted=submitted,
        drafts=drafts,
        paid=paid,
        disabled_or_withdrawn=disabled_or_withdrawn,
    )


async def get_entry(
    session: AsyncSession,
    *,
    entry_id: uuid.UUID,
    requesting_user: User,
    allow_admin: bool = False,
) -> PredictionEntry:
    """Single fetch with ownership check."""
    entry = await _load_entry_with_phases(session, entry_id)
    await _ensure_owner(entry, requesting_user, allow_admin=allow_admin)
    return entry


async def rename_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    new_name: str,
    competition: Competition,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    """Rename — only allowed when no phase is locked yet (so user can
    still edit), `allow_user_rename` is true, and the entry isn't
    withdrawn or disabled."""
    await _ensure_owner(entry, user)
    if not competition.allow_user_rename:
        raise EntryValidationError("Rename is disabled for this competition")
    if entry.withdrawn_at is not None:
        raise EntryStateError("Cannot rename a withdrawn entry")
    if entry.is_disabled:
        raise EntryStateError("Cannot rename a disabled entry")
    if any(_phase_is_locked(p, competition) for p in entry.phases):
        raise EntryStateError("Cannot rename after a phase has locked")

    old = entry.display_name
    new = new_name.strip()
    if not new:
        raise EntryValidationError("display_name cannot be empty")
    entry.display_name = new
    entry.updated_at = utc_now()

    record_audit_event(
        session,
        event_type="entry.renamed",
        actor_user_id=user.id,
        actor_role=ActorRole.USER,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata={
            "reference": entry.reference,
            "old_name": old,
            "new_name": new,
        },
    )
    await session.flush()
    return entry


async def duplicate_entry(
    session: AsyncSession,
    *,
    source: PredictionEntry,
    user: User,
    competition: Competition,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    """Copy `source`'s predictions into a new draft entry.

    The new entry is fresh: status draft on both phases, never paid,
    no locked_at timestamps. Match / team / bonus predictions are
    copied verbatim. The source entry is unaffected.
    """
    await _ensure_owner(source, user)
    if not competition.allow_duplicate_from_existing:
        raise EntryValidationError("Duplication is disabled for this competition")
    if source.is_disabled:
        raise EntryValidationError("Cannot duplicate a disabled entry")

    new_entry = await create_entry(
        session,
        user=user,
        competition=competition,
        # Suffix the source name so users can tell duplicates apart.
        display_name=f"{source.display_name} (copy)",
        actor_role=ActorRole.USER,
        ctx=ctx,
    )
    await _copy_predictions(session, source_id=source.id, target_id=new_entry.id)

    record_audit_event(
        session,
        event_type="entry.duplicated",
        actor_user_id=user.id,
        actor_role=ActorRole.USER,
        subject_type="entry",
        subject_id=new_entry.id,
        ctx=ctx,
        metadata={
            "source_reference": source.reference,
            "new_reference": new_entry.reference,
        },
    )
    await session.flush()
    return new_entry


async def _copy_predictions(
    session: AsyncSession,
    *,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> None:
    """Copy match / team / bonus predictions from one entry to another."""
    # MatchPrediction
    src_matches = (
        await session.execute(
            select(MatchPrediction).where(MatchPrediction.entry_id == source_id)
        )
    ).scalars().all()
    for m in src_matches:
        session.add(
            MatchPrediction(
                entry_id=target_id,
                fixture_id=m.fixture_id,
                home_score=m.home_score,
                away_score=m.away_score,
                phase=m.phase,
                # Don't copy locked_at — the new entry is editable.
            )
        )

    # TeamPrediction
    src_teams = (
        await session.execute(
            select(TeamPrediction).where(TeamPrediction.entry_id == source_id)
        )
    ).scalars().all()
    for t in src_teams:
        session.add(
            TeamPrediction(
                entry_id=target_id,
                team=t.team,
                stage=t.stage,
                group_position=t.group_position,
                phase=t.phase,
            )
        )

    # BonusPrediction
    src_bonus = (
        await session.execute(
            select(BonusPrediction).where(BonusPrediction.entry_id == source_id)
        )
    ).scalars().all()
    for b in src_bonus:
        session.add(
            BonusPrediction(
                entry_id=target_id,
                question_id=b.question_id,
                answer=b.answer,
            )
        )


# ---------------------------------------------------------------------------
# State transitions — phase-level
# ---------------------------------------------------------------------------
def _check_transition_allowed(
    from_status: EntryStatus,
    to_status: EntryStatus,
    actor_role: ActorRole,
) -> None:
    """Raise `EntryStateError` if the transition isn't permitted."""
    allowed_roles = _ALLOWED_TRANSITIONS.get((from_status, to_status))
    if allowed_roles is None:
        raise EntryStateError(
            f"Transition {from_status.value} → {to_status.value} is not allowed"
        )
    if actor_role not in allowed_roles:
        raise EntryStateError(
            f"Role {actor_role.value} cannot perform "
            f"{from_status.value} → {to_status.value}"
        )


def _entry_is_active(entry: PredictionEntry) -> bool:
    """Convenience: not withdrawn and not disabled."""
    return entry.withdrawn_at is None and not entry.is_disabled


# ---------------------------------------------------------------------------
# Lifecycle service functions — five transitions only:
#   DRAFT → SUBMITTED          (submit_entry, user/admin, before deadline)
#   SUBMITTED → DRAFT          (edit_entry, user/admin, before deadline)
#   DRAFT/SUBMITTED → WITHDRAWN (admin_withdraw_entry, admin only)
#   WITHDRAWN → SUBMITTED      (admin_reinstate_entry, admin only, reason required)
#   DRAFT → WITHDRAWN          (flip_drafts_past_deadline, system, at deadline)
# Phase 2 is dormant — all functions hardcode PHASE_1.
# ---------------------------------------------------------------------------
async def _validate_phase1_complete(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
) -> None:
    """Raise EntryValidationError if Phase 1 isn't fully predicted.

    Defense-in-depth against the frontend submitting an incomplete entry
    (bypass via curl, stale state, tampering). Checks three things:

    1. Every group fixture has a `MatchPrediction`.
    2. The knockout bracket has the right number of `TeamPrediction`
       rows per stage AND the **winner chain is intact** — every team
       at a later stage must also appear at the prior stage. Catches
       the case where the user changed an upstream pick and stale
       downstream rows survived (e.g. the user changed an R32 winner,
       so `round_of_16` was updated but the old winner's row still
       lives at `quarter_final` / `semi_final` / `final`).
    3. Every bonus question is answered (non-empty).

    Aggregates all missing items into a single error message so the
    user sees the full picture at once instead of fix-one-resubmit.
    """
    # Lazy imports: same pattern as the completion-summary query
    # downstream — keeps the top-level import block lean.
    from app.models.fixture import Fixture
    from app.services.bonus import get_questions as get_bonus_questions

    phase = PredictionPhase.PHASE_1
    missing: list[str] = []

    # --- 1. Groups: every group-stage fixture predicted ----------------
    groups_total = int(
        (
            await session.execute(
                select(func.count(Fixture.id)).where(Fixture.stage == "group")
            )
        ).scalar_one()
    )
    groups_done = int(
        (
            await session.execute(
                select(func.count(MatchPrediction.id))
                .join(Fixture, Fixture.id == MatchPrediction.fixture_id)
                .where(
                    MatchPrediction.entry_id == entry.id,
                    Fixture.stage == "group",
                )
            )
        ).scalar_one()
    )
    if groups_done < groups_total:
        missing.append(
            f"Group fixtures: {groups_total - groups_done} of "
            f"{groups_total} unscored"
        )

    # --- 2. Bracket: counts per stage + winner-chain integrity ---------
    rows = (
        (
            await session.execute(
                select(TeamPrediction).where(
                    TeamPrediction.entry_id == entry.id,
                    TeamPrediction.phase == phase,
                )
            )
        )
        .scalars()
        .all()
    )
    by_stage: dict[str, set[str]] = {}
    for tp in rows:
        # normalize_stage: read-side defense in case any legacy plural
        # rows ("quarter_finals") survive the v2.161.0 data migration.
        by_stage.setdefault(normalize_stage(tp.stage), set()).add(tp.team)

    # R32 picks are auto-derived from group winners; user picks WINNERS
    # from R16 onward, plus the tournament winner. 16 + 8 + 4 + 2 + 1 = 31.
    expected_counts = {
        "round_of_16": 16,
        "quarter_final": 8,
        "semi_final": 4,
        "final": 2,
        "winner": 1,
    }
    for stage, expected in expected_counts.items():
        got = len(by_stage.get(stage, set()))
        if got < expected:
            missing.append(
                f"Bracket {stage.replace('_', ' ')}: {expected - got} of "
                f"{expected} unpicked"
            )

    # Chain integrity. Each team at a later stage must also exist at the
    # prior stage. Catches stale rows that survive when the user changes
    # an upstream winner — the new winner replaces the old at one stage
    # but the old winner's downstream chain (still rows in the DB) is
    # now orphaned. The frontend's `predictionToBracketState` rebuild
    # catches the same class of corruption from a different angle; this
    # is the server-side equivalent operating on the flat row shape.
    stage_order = [
        "round_of_16",
        "quarter_final",
        "semi_final",
        "final",
        "winner",
    ]
    for i in range(1, len(stage_order)):
        higher, lower = stage_order[i], stage_order[i - 1]
        orphans = by_stage.get(higher, set()) - by_stage.get(lower, set())
        if orphans:
            sample = sorted(orphans)[0]
            missing.append(
                f"Bracket chain broken at {higher.replace('_', ' ')}: "
                f"{sample!r} not present in {lower.replace('_', ' ')} "
                "(stale pick — re-pick downstream rounds)"
            )

    # --- 3. Bonus: every question has a non-empty answer ---------------
    bonus_total = len(get_bonus_questions())
    bonus_done = int(
        (
            await session.execute(
                select(func.count(BonusPrediction.id)).where(
                    BonusPrediction.entry_id == entry.id,
                    BonusPrediction.answer != "",
                )
            )
        ).scalar_one()
    )
    if bonus_done < bonus_total:
        missing.append(
            f"Bonus questions: {bonus_total - bonus_done} of "
            f"{bonus_total} unanswered"
        )

    if missing:
        raise EntryValidationError(
            "Entry is not complete:\n" + "\n".join(f"- {m}" for m in missing)
        )


async def submit_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    competition: Competition,
    actor_role: ActorRole = ActorRole.USER,
    ctx: AuditContext | None = None,
    validate_complete: bool = True,
) -> PredictionEntryPhase:
    """`DRAFT → SUBMITTED`. Enforces ownership, deadline, payment + duplicate rules.

    `validate_complete=True` (default) also enforces Phase-1 completeness
    — every group fixture predicted, every knockout-round winner picked
    with an intact chain, every bonus question answered. Production
    callers (the API route) use the default. Transition-mechanics tests
    that don't care about completeness opt out with
    `validate_complete=False`.
    """
    phase = PredictionPhase.PHASE_1
    if actor_role == ActorRole.USER:
        await _ensure_owner(entry, user)
    if not _entry_is_active(entry):
        raise EntryStateError("Entry is withdrawn or disabled")

    phase_row = _phase_record(entry, phase)
    if _phase_is_locked(phase_row, competition):
        raise EntryStateError("Competition has started — submit no longer possible")
    _check_transition_allowed(phase_row.status, EntryStatus.SUBMITTED, actor_role)

    # Payment gate: if competition blocks unpaid submission, entry must be paid.
    if competition.block_unpaid_entry_submission and not entry.paid:
        raise EntryValidationError("Entry is unpaid; submission blocked")

    # Pool-rule (R3): the user must record who they paid the entry fee to
    # before submitting. The field is optional in the profile UI but enforced
    # here so any submit caller (API, future scripts, tests) gets the same
    # gate. The frontend submit modal captures + persists it via PATCH /auth/me
    # right before calling submit; this validation is the safety net.
    if not user.paid_to or not user.paid_to.strip():
        raise EntryValidationError(
            "Please record who you paid the fee to before submitting."
        )

    # Phase-1 completeness — defense-in-depth against the frontend
    # submitting an incomplete entry (curl bypass, stale state, tampering).
    # The frontend already gates the Submit button on the same conditions;
    # this is the server-side belt-and-braces. Critically: rejects
    # knockout brackets whose winner chain is broken (stale teams that
    # survived an upstream pick change). Tests that don't care about
    # completeness pass `validate_complete=False` to skip.
    if validate_complete:
        await _validate_phase1_complete(session, entry=entry)

    # Duplicate-submission check — reject identical predictions.
    conflict = await _find_duplicate_eligible_entry(
        session, entry=entry, phase=phase
    )
    if conflict is not None:
        raise EntryDuplicateError(
            f"Predictions identical to entry {conflict}",
            conflict_reference=conflict,
        )

    prev = phase_row.status
    phase_row.status = EntryStatus.SUBMITTED
    phase_row.submitted_at = utc_now()
    phase_row.updated_at = utc_now()

    await _write_transition_event(
        session,
        entry=entry,
        phase=phase,
        from_status=prev,
        to_status=EntryStatus.SUBMITTED,
        actor_user_id=user.id,
        actor_role=actor_role,
        reason=None,
        audit_event_type="entry.submitted",
        ctx=ctx,
    )
    await session.flush()
    return phase_row


async def edit_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    competition: Competition,
    actor_role: ActorRole = ActorRole.USER,
    ctx: AuditContext | None = None,
) -> PredictionEntryPhase:
    """`SUBMITTED → DRAFT`. Blocked once the competition has started.

    User-facing: "Edit" button on a submitted entry reverts it to draft so the
    user can change picks and re-submit before the deadline.
    """
    phase = PredictionPhase.PHASE_1
    if actor_role == ActorRole.USER:
        await _ensure_owner(entry, user)
    if not _entry_is_active(entry):
        raise EntryStateError("Entry is withdrawn or disabled")

    phase_row = _phase_record(entry, phase)
    if _phase_is_locked(phase_row, competition):
        raise EntryStateError(
            "Competition has started — edit no longer possible"
        )
    _check_transition_allowed(phase_row.status, EntryStatus.DRAFT, actor_role)

    prev = phase_row.status
    phase_row.status = EntryStatus.DRAFT
    phase_row.submitted_at = None
    phase_row.ready_at = None
    phase_row.updated_at = utc_now()

    await _write_transition_event(
        session,
        entry=entry,
        phase=phase,
        from_status=prev,
        to_status=EntryStatus.DRAFT,
        actor_user_id=user.id,
        actor_role=actor_role,
        reason=None,
        audit_event_type="entry.edit_reverted",
        ctx=ctx,
    )
    await session.flush()
    return phase_row


async def admin_withdraw_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    admin: User,
    reason: str,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    """Admin-only withdrawal. Sets `entry.withdrawn_at` + flips phase status
    to WITHDRAWN. Allowed from DRAFT or SUBMITTED. WITHDRAWN is non-terminal —
    `admin_reinstate_entry` can reverse it. `reason` is mandatory.
    """
    if not reason or not reason.strip():
        raise EntryValidationError("Withdrawal reason is required")
    if entry.withdrawn_at is not None:
        raise EntryStateError("Entry already withdrawn")
    if entry.is_disabled:
        raise EntryStateError("Cannot withdraw a disabled entry")

    phase = PredictionPhase.PHASE_1
    phase_row = _phase_record(entry, phase)
    _check_transition_allowed(phase_row.status, EntryStatus.WITHDRAWN, ActorRole.ADMIN)

    now = utc_now()
    entry.withdrawn_at = now
    entry.withdrawn_reason = reason
    entry.updated_at = now

    prev = phase_row.status
    phase_row.status = EntryStatus.WITHDRAWN
    phase_row.updated_at = now

    await _write_transition_event(
        session,
        entry=entry,
        phase=phase,
        from_status=prev,
        to_status=EntryStatus.WITHDRAWN,
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        reason=reason,
        audit_event_type="entry.withdrawn_admin",
        ctx=ctx,
    )
    await session.flush()
    return entry


async def admin_reinstate_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    admin: User,
    reason: str,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    """Admin-only reinstatement. `WITHDRAWN → SUBMITTED`. Reason mandatory.

    Use case: user filled all predictions but forgot to click Submit before the
    deadline; admin reviews evidence and reinstates. Captures the previous
    withdrawal event's ID in audit metadata.
    """
    if not reason or not reason.strip():
        raise EntryValidationError("Reinstatement reason is required")
    if entry.withdrawn_at is None:
        raise EntryStateError("Entry is not withdrawn — nothing to reinstate")
    if entry.is_disabled:
        raise EntryStateError("Cannot reinstate a disabled entry")

    phase = PredictionPhase.PHASE_1
    phase_row = _phase_record(entry, phase)
    _check_transition_allowed(
        phase_row.status, EntryStatus.SUBMITTED, ActorRole.ADMIN
    )

    # Most recent withdrawal event for audit context.
    last_withdrawal = (
        await session.execute(
            select(PredictionEntryEvent)
            .where(
                PredictionEntryEvent.entry_id == entry.id,
                PredictionEntryEvent.to_status == EntryStatus.WITHDRAWN.value,
            )
            .order_by(PredictionEntryEvent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    now = utc_now()
    entry.withdrawn_at = None
    entry.withdrawn_reason = None
    entry.updated_at = now

    prev = phase_row.status
    phase_row.status = EntryStatus.SUBMITTED
    phase_row.submitted_at = now
    phase_row.updated_at = now

    extra_meta: dict[str, Any] = {}
    if last_withdrawal is not None:
        extra_meta["previous_withdrawal_event_id"] = str(last_withdrawal.id)
        extra_meta["previous_withdrawal_reason"] = last_withdrawal.reason or ""

    await _write_transition_event(
        session,
        entry=entry,
        phase=phase,
        from_status=prev,
        to_status=EntryStatus.SUBMITTED,
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        reason=reason,
        audit_event_type="entry.admin_reinstated",
        ctx=ctx,
        extra_metadata=extra_meta,
    )
    await session.flush()
    return entry


async def withdraw_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    competition: Competition,
    reason: str | None = None,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    """User-initiated withdrawal. All active phases → WITHDRAWN.

    Gated by the `allow_user_withdrawal` competition setting. Only allowed
    before the phase deadline (same guard as submit/edit). The user can
    reinstate at any time before the deadline via `reinstate_entry`.
    `reason` is optional — stored as `withdrawn_reason` when provided.
    """
    await _ensure_owner(entry, user)
    if not competition.allow_user_withdrawal:
        raise EntryValidationError("User withdrawal is not enabled for this competition")
    if entry.withdrawn_at is not None:
        raise EntryStateError("Entry is already withdrawn")
    if entry.is_disabled:
        raise EntryStateError("Cannot withdraw a disabled entry")

    # Use phase 1 as the guard for deadline check — if it's locked no withdraws.
    phase1_row = _phase_record(entry, PredictionPhase.PHASE_1)
    if _phase_is_locked(phase1_row, competition):
        raise EntryStateError("Competition has started — withdrawal no longer possible")

    now = utc_now()
    stored_reason = reason.strip() if reason else "user_requested"
    entry.withdrawn_at = now
    entry.withdrawn_reason = stored_reason
    entry.updated_at = now

    # Mark every phase row as WITHDRAWN (both PHASE_1 and PHASE_2).
    for phase_row in entry.phases:
        _check_transition_allowed(phase_row.status, EntryStatus.WITHDRAWN, ActorRole.USER)
        prev = phase_row.status
        phase_row.status = EntryStatus.WITHDRAWN
        phase_row.updated_at = now
        await _write_transition_event(
            session,
            entry=entry,
            phase=phase_row.phase,
            from_status=prev,
            to_status=EntryStatus.WITHDRAWN,
            actor_user_id=user.id,
            actor_role=ActorRole.USER,
            reason=stored_reason,
            audit_event_type="entry.withdrawn_user",
            ctx=ctx,
        )

    await session.flush()
    return entry


async def reinstate_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    competition: Competition,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    """User-initiated reinstatement. `WITHDRAWN → DRAFT`.

    Returns the entry to DRAFT (not SUBMITTED) so the user can review
    their predictions and explicitly re-submit before the deadline.
    Blocked once the phase deadline has passed.
    """
    await _ensure_owner(entry, user)
    if entry.withdrawn_at is None:
        raise EntryStateError("Entry is not withdrawn — nothing to reinstate")
    if entry.is_disabled:
        raise EntryStateError("Cannot reinstate a disabled entry")

    phase1_row = _phase_record(entry, PredictionPhase.PHASE_1)
    if _phase_is_locked(phase1_row, competition):
        raise EntryStateError("Competition has started — reinstatement no longer possible")

    now = utc_now()
    entry.withdrawn_at = None
    entry.withdrawn_reason = None
    entry.updated_at = now

    # Restore every WITHDRAWN phase row back to DRAFT.
    for phase_row in entry.phases:
        if phase_row.status != EntryStatus.WITHDRAWN:
            continue
        _check_transition_allowed(phase_row.status, EntryStatus.DRAFT, ActorRole.USER)
        prev = phase_row.status
        phase_row.status = EntryStatus.DRAFT
        phase_row.updated_at = now
        await _write_transition_event(
            session,
            entry=entry,
            phase=phase_row.phase,
            from_status=prev,
            to_status=EntryStatus.DRAFT,
            actor_user_id=user.id,
            actor_role=ActorRole.USER,
            reason=None,
            audit_event_type="entry.reinstated_user",
            ctx=ctx,
        )

    await session.flush()
    return entry


async def flip_drafts_past_deadline(session: AsyncSession) -> int:
    """`DRAFT → WITHDRAWN` for every entry whose phase deadline has passed.

    Idempotent — runs every 60s from the scheduler tick. Returns the number of
    entries flipped. Writes one audit event per transitioned entry with
    actor_role=SYSTEM, reason='competition_started'.
    """
    now = utc_now()
    competitions = (
        await session.execute(
            select(Competition).where(
                Competition.is_active == True,  # noqa: E712
                Competition.phase1_deadline.is_not(None),
            )
        )
    ).scalars().all()

    flipped = 0
    for competition in competitions:
        deadline = competition.phase1_deadline
        if deadline is None or aware_utc(now) < aware_utc(deadline):
            continue

        rows = (
            await session.execute(
                select(PredictionEntryPhase, PredictionEntry)
                .join(PredictionEntry, PredictionEntry.id == PredictionEntryPhase.entry_id)
                .where(
                    PredictionEntry.competition_id == competition.id,
                    PredictionEntry.withdrawn_at.is_(None),
                    PredictionEntryPhase.phase == PredictionPhase.PHASE_1,
                    PredictionEntryPhase.status == EntryStatus.DRAFT,
                )
            )
        ).all()

        for phase_row, entry in rows:
            entry.withdrawn_at = now
            entry.withdrawn_reason = "competition_started"
            entry.updated_at = now

            prev = phase_row.status
            phase_row.status = EntryStatus.WITHDRAWN
            phase_row.updated_at = now

            await _write_transition_event(
                session,
                entry=entry,
                phase=PredictionPhase.PHASE_1,
                from_status=prev,
                to_status=EntryStatus.WITHDRAWN,
                actor_user_id=entry.user_id,
                actor_role=ActorRole.SYSTEM,
                reason="competition_started",
                audit_event_type="entry.auto_withdrawn_at_start",
                ctx=None,
            )
            flipped += 1

    if flipped > 0:
        await session.flush()
    return flipped


# ---------------------------------------------------------------------------
# Completion summary — how many predictions has each entry filled in?
# ---------------------------------------------------------------------------
async def get_completion_summary(
    session: AsyncSession,
    *,
    user: User,
    competition: Competition,
) -> list[dict]:
    """Return per-entry completion counts for all entries owned by `user`.

    Three buckets:
    - groups:  match predictions for group-stage fixtures
    - bracket: team advancement picks (R32 excluded — those are derived)
    - bonus:   answered bonus questions (non-empty answer strings)

    Group total is the global fixture count (same for every entry).
    Bracket total is hardcoded 31: R16(16)+QF(8)+SF(4)+F(2)+winner(1).
    Bonus total is the length of the YAML-loaded question list.
    """
    from app.models.fixture import Fixture
    from app.services.bonus import get_questions as get_bonus_questions

    # All entries for this user in this competition.
    entries = await list_user_entries(session, user=user, competition=competition)
    if not entries:
        return []

    entry_ids = [e.id for e in entries]

    # ---------- group totals (global — identical for every entry) ----------
    groups_total = int(
        (
            await session.execute(
                select(func.count(Fixture.id)).where(Fixture.stage == "group")
            )
        ).scalar_one()
    )

    # ---------- group done: one row per entry ----------
    group_done_rows = (
        await session.execute(
            select(
                MatchPrediction.entry_id,
                func.count(MatchPrediction.id).label("done"),
            )
            .join(Fixture, Fixture.id == MatchPrediction.fixture_id)
            .where(
                MatchPrediction.entry_id.in_(entry_ids),
                Fixture.stage == "group",
            )
            .group_by(MatchPrediction.entry_id)
        )
    ).all()
    group_done_map: dict[uuid.UUID, int] = {r[0]: r[1] for r in group_done_rows}

    # ---------- bracket total (hardcoded — R32 picks are auto-derived) -----
    bracket_total = 31  # R16=16 + QF=8 + SF=4 + F=2 + winner=1

    # ---------- bracket done: one row per entry ----------------------------
    bracket_done_rows = (
        await session.execute(
            select(
                TeamPrediction.entry_id,
                func.count(TeamPrediction.id).label("done"),
            )
            .where(
                TeamPrediction.entry_id.in_(entry_ids),
                TeamPrediction.stage != "round_of_32",
            )
            .group_by(TeamPrediction.entry_id)
        )
    ).all()
    bracket_done_map: dict[uuid.UUID, int] = {r[0]: r[1] for r in bracket_done_rows}

    # ---------- bonus totals -----------------------------------------------
    bonus_total = len(get_bonus_questions())

    # ---------- bonus done: one row per entry (non-empty answers only) -----
    bonus_done_rows = (
        await session.execute(
            select(
                BonusPrediction.entry_id,
                func.count(BonusPrediction.id).label("done"),
            )
            .where(
                BonusPrediction.entry_id.in_(entry_ids),
                BonusPrediction.answer != "",
            )
            .group_by(BonusPrediction.entry_id)
        )
    ).all()
    bonus_done_map: dict[uuid.UUID, int] = {r[0]: r[1] for r in bonus_done_rows}

    # ---------- predicted winner: at most one row per entry ----------------
    # Surfaced on the entries list/card view so users can see their champion
    # pick at a glance. Maps entry_id → team name; absent when not predicted.
    winner_rows = (
        await session.execute(
            select(TeamPrediction.entry_id, TeamPrediction.team)
            .where(
                TeamPrediction.entry_id.in_(entry_ids),
                TeamPrediction.stage == "winner",
            )
        )
    ).all()
    winner_map: dict[uuid.UUID, str] = {r[0]: r[1] for r in winner_rows}

    return [
        {
            "entry_id": e.id,
            "groups": {
                "done": group_done_map.get(e.id, 0),
                "total": groups_total,
            },
            "bracket": {
                "done": bracket_done_map.get(e.id, 0),
                "total": bracket_total,
            },
            "bonus": {
                "done": bonus_done_map.get(e.id, 0),
                "total": bonus_total,
            },
            "predicted_winner": winner_map.get(e.id),
        }
        for e in entries
    ]


# ---------------------------------------------------------------------------
# Duplicate-submission check
# ---------------------------------------------------------------------------
async def _find_duplicate_eligible_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    phase: PredictionPhase,
) -> str | None:
    """Return the reference of another eligible entry (same user, same
    competition) whose predictions are identical to `entry`'s for the
    given phase. Returns None if no duplicate exists.

    "Eligible" = status == submitted, not withdrawn, not disabled.

    "Identical" =
      - same set of (fixture_id, home_score, away_score) for the phase
      - same set of (team, stage, group_position) for the phase
      - same set of (question_id, answer) for bonus picks
    """
    # Find candidate other entries owned by the same user in the same
    # competition with a submitted/locked phase row matching `phase`.
    candidates_q = (
        select(PredictionEntry)
        .join(
            PredictionEntryPhase,
            PredictionEntry.id == PredictionEntryPhase.entry_id,
        )
        .where(
            PredictionEntry.user_id == entry.user_id,
            PredictionEntry.competition_id == entry.competition_id,
            PredictionEntry.id != entry.id,
            PredictionEntry.withdrawn_at.is_(None),
            PredictionEntry.is_disabled.is_(False),
            PredictionEntryPhase.phase == phase,
            PredictionEntryPhase.status == EntryStatus.SUBMITTED,
        )
    )
    candidates = (await session.execute(candidates_q)).scalars().all()
    if not candidates:
        return None

    my_matches = await _match_pred_signature(session, entry.id, phase)
    my_teams = await _team_pred_signature(session, entry.id, phase)
    my_bonus = await _bonus_pred_signature(session, entry.id)

    for other in candidates:
        o_matches = await _match_pred_signature(session, other.id, phase)
        if o_matches != my_matches:
            continue
        o_teams = await _team_pred_signature(session, other.id, phase)
        if o_teams != my_teams:
            continue
        o_bonus = await _bonus_pred_signature(session, other.id)
        if o_bonus != my_bonus:
            continue
        return other.reference
    return None


async def _match_pred_signature(
    session: AsyncSession, entry_id: uuid.UUID, phase: PredictionPhase
) -> frozenset[tuple[uuid.UUID, int, int]]:
    rows = (
        await session.execute(
            select(
                MatchPrediction.fixture_id,
                MatchPrediction.home_score,
                MatchPrediction.away_score,
            ).where(
                MatchPrediction.entry_id == entry_id,
                MatchPrediction.phase == phase,
            )
        )
    ).all()
    return frozenset((r[0], r[1], r[2]) for r in rows)


async def _team_pred_signature(
    session: AsyncSession, entry_id: uuid.UUID, phase: PredictionPhase
) -> frozenset[tuple[str, str, int | None]]:
    rows = (
        await session.execute(
            select(
                TeamPrediction.team,
                TeamPrediction.stage,
                TeamPrediction.group_position,
            ).where(
                TeamPrediction.entry_id == entry_id,
                TeamPrediction.phase == phase,
            )
        )
    ).all()
    return frozenset((r[0], r[1], r[2]) for r in rows)


async def _bonus_pred_signature(
    session: AsyncSession, entry_id: uuid.UUID
) -> frozenset[tuple[str, str]]:
    """Bonus picks are not phase-scoped; same signature for any phase check."""
    rows = (
        await session.execute(
            select(BonusPrediction.question_id, BonusPrediction.answer).where(
                BonusPrediction.entry_id == entry_id
            )
        )
    ).all()
    return frozenset((r[0], r[1]) for r in rows)


# ---------------------------------------------------------------------------
# Admin actions
# ---------------------------------------------------------------------------
async def admin_disable_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    admin: User,
    reason: str,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    """Set the `is_disabled` overlay. Does NOT mutate phase status —
    locked phases stay locked (the brief is explicit: `is_disabled`
    is an overlay, not a status change)."""
    if entry.is_disabled:
        raise EntryStateError("Entry already disabled")
    if not reason or not reason.strip():
        raise EntryValidationError("Reason is required to disable an entry")

    now = utc_now()
    entry.is_disabled = True
    entry.disabled_reason = reason.strip()
    entry.disabled_at = now
    entry.disabled_by_user_id = admin.id
    entry.updated_at = now

    record_audit_event(
        session,
        event_type="entry.disabled",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata={"reference": entry.reference},
        reason=reason,
    )
    await session.flush()
    return entry


async def admin_enable_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    admin: User,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    """Clear the `is_disabled` overlay."""
    if not entry.is_disabled:
        raise EntryStateError("Entry is not disabled")
    entry.is_disabled = False
    entry.disabled_reason = None
    entry.disabled_at = None
    entry.disabled_by_user_id = None
    entry.updated_at = utc_now()

    record_audit_event(
        session,
        event_type="entry.enabled",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata={"reference": entry.reference},
    )
    await session.flush()
    return entry


async def admin_set_paid(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    admin: User,
    paid: bool,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    old = entry.paid
    entry.paid = paid
    entry.updated_at = utc_now()
    record_audit_event(
        session,
        event_type="entry.paid_updated",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata={
            "reference": entry.reference,
            "old_paid": old,
            "new_paid": paid,
        },
    )
    await session.flush()
    return entry


async def admin_set_prize_eligible(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    admin: User,
    prize_eligible: bool,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    old = entry.prize_eligible
    entry.prize_eligible = prize_eligible
    entry.updated_at = utc_now()
    record_audit_event(
        session,
        event_type="entry.prize_eligible_updated",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata={
            "reference": entry.reference,
            "old_prize_eligible": old,
            "new_prize_eligible": prize_eligible,
        },
    )
    await session.flush()
    return entry


@dataclass
class Phase2OpenSummary:
    entries_opened: int
    entries_skipped_withdrawn: int
    entries_skipped_disabled: int
    entries_already_open: int


async def admin_open_phase2(
    session: AsyncSession,
    *,
    admin: User,
    competition: Competition,
    ctx: AuditContext | None = None,
) -> Phase2OpenSummary:
    """Globally trigger Phase II for every eligible entry.

    Idempotent: entries with phase_2 already in draft (or further) are
    counted as `entries_already_open`.

    Eligibility: not withdrawn AND not disabled. Withdrawn/disabled
    entries are skipped and counted separately for visibility.

    Currently phase_2 rows are created in `create_entry()`. This
    handler ensures that:
    - Withdrawn entries don't get their phase_2 re-armed.
    - Disabled entries don't get their phase_2 re-armed.
    - Any entry whose phase_2 was somehow missing gets one.
    - We mark the competition's `is_phase2_active=True` and stamp
      `phase2_activated_at`.
    """
    # Mark the competition first so subsequent phase access is allowed.
    competition.is_phase2_active = True
    competition.phase2_activated_at = utc_now()
    competition.updated_at = utc_now()

    # Load all entries in the competition with their phase rows.
    entries = (
        await session.execute(
            select(PredictionEntry)
            .options(selectinload(PredictionEntry.phases))
            .where(PredictionEntry.competition_id == competition.id)
        )
    ).scalars().all()

    summary = Phase2OpenSummary(0, 0, 0, 0)
    for entry in entries:
        if entry.withdrawn_at is not None:
            summary.entries_skipped_withdrawn += 1
            continue
        if entry.is_disabled:
            summary.entries_skipped_disabled += 1
            continue
        phase2 = next(
            (p for p in entry.phases if p.phase == PredictionPhase.PHASE_2),
            None,
        )
        if phase2 is None:
            # Create a missing phase_2 row.
            phase2 = PredictionEntryPhase(
                entry_id=entry.id,
                phase=PredictionPhase.PHASE_2,
                status=EntryStatus.DRAFT,
            )
            session.add(phase2)
            summary.entries_opened += 1
            await _write_transition_event(
                session,
                entry=entry,
                phase=PredictionPhase.PHASE_2,
                from_status=EntryStatus.DRAFT,
                to_status=EntryStatus.DRAFT,
                actor_user_id=admin.id,
                actor_role=ActorRole.ADMIN,
                reason="Phase II opened",
                audit_event_type="entry.phase_opened",
                ctx=ctx,
                extra_metadata={"created_missing_phase_row": True},
            )
            continue
        if phase2.status == EntryStatus.DRAFT:
            summary.entries_already_open += 1
            continue
        # If it had been set to some non-draft state (e.g. locked from
        # a previous cycle), don't reset it — admin-recovery is a
        # different action. Count as already open conservatively.
        summary.entries_already_open += 1

    # Top-level competition-scope audit event.
    record_audit_event(
        session,
        event_type="competition.phase2_opened",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="competition",
        subject_id=competition.id,
        ctx=ctx,
        metadata={
            "entries_opened": summary.entries_opened,
            "entries_skipped_withdrawn": summary.entries_skipped_withdrawn,
            "entries_skipped_disabled": summary.entries_skipped_disabled,
            "entries_already_open": summary.entries_already_open,
        },
    )
    await session.flush()
    return summary


_ADMIN_LIST_MODIFIED_WINDOWS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


async def admin_list_entries(
    session: AsyncSession,
    *,
    competition: Competition,
    user_id: uuid.UUID | None = None,
    reference: str | None = None,
    search: str | None = None,
    status: EntryStatus | None = None,
    paid: bool | None = None,
    disabled: bool | None = None,
    modified_within: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[PredictionEntry], int]:
    """Admin list with filters and pagination.

    Returns ``(items, total)`` where ``total`` is the count of rows
    matching the filters before pagination. Pass ``limit=None`` (the
    default) to return every match — preserves the pre-pagination API
    for callers that don't paginate (CSV export, tests).

    ``search`` is the user-facing free-text filter — case-insensitive
    substring matched against ``User.email`` OR ``User.name`` OR
    ``PredictionEntry.reference``. Joins ``User`` only when set, so
    the common-case query plan is unchanged. ``User.name`` was added in
    v2.156.0 — admins typically remember names, not emails, so this
    lifts a common pain point.

    ``modified_within`` (added v2.156.0) is one of ``"1h"``, ``"24h"``,
    ``"7d"``, ``"30d"`` — filters to entries with
    ``updated_at >= utc_now() - delta``. Powers the "modified within"
    chip set on /admin/entries. Unknown values are ignored (treated as
    no filter) so the API stays forgiving against typos / stale URLs.

    ``reference`` is the legacy exact-match path preserved for
    bookmarked URLs.
    """
    base = (
        select(PredictionEntry)
        .where(PredictionEntry.competition_id == competition.id)
    )
    if user_id is not None:
        base = base.where(PredictionEntry.user_id == user_id)
    if reference is not None:
        base = base.where(PredictionEntry.reference == reference)
    if search is not None and search.strip():
        # OR-match on user email, user name, or entry reference. ilike
        # with %…% gives substring + case-insensitive semantics admins
        # expect when typing "vin", "bob", "000020", or "@gmail".
        # User.name added in v2.156.0 (was email + reference only).
        like_pattern = f"%{search.strip()}%"
        base = base.join(User, User.id == PredictionEntry.user_id).where(
            or_(
                User.email.ilike(like_pattern),
                User.name.ilike(like_pattern),
                PredictionEntry.reference.ilike(like_pattern),
            )
        )
    if paid is not None:
        base = base.where(PredictionEntry.paid == paid)
    if disabled is not None:
        base = base.where(PredictionEntry.is_disabled == disabled)
    if modified_within is not None:
        # Unknown tokens silently become no-filter — defensive against
        # accidental ?modified_within=foo from typos / stale URLs.
        delta = _ADMIN_LIST_MODIFIED_WINDOWS.get(modified_within)
        if delta is not None:
            cutoff = utc_now() - delta
            base = base.where(PredictionEntry.updated_at >= cutoff)
    if status is not None:
        # WITHDRAWN is an entry-level overlay (entry.withdrawn_at), not a
        # phase status — entries' phase rows don't transition to WITHDRAWN
        # in the lifecycle code. Special-case it.
        if status == EntryStatus.WITHDRAWN:
            base = base.where(PredictionEntry.withdrawn_at.is_not(None))
        else:
            # DRAFT / SUBMITTED filter must scope to PHASE_1. Every entry
            # carries a phase_2 = DRAFT row (Phase 2 is dormant in
            # production but the rows exist from creation), so a naive
            # join-and-match would return every entry for status=draft.
            # Also exclude withdrawn entries — they have phase_1=DRAFT
            # but the user-facing "Draft" category never includes them
            # (the frontend stat-card derivation has the same exclusion).
            base = base.join(
                PredictionEntryPhase,
                PredictionEntry.id == PredictionEntryPhase.entry_id,
            ).where(
                PredictionEntryPhase.phase == PredictionPhase.PHASE_1,
                PredictionEntryPhase.status == status,
                PredictionEntry.withdrawn_at.is_(None),
            )

    # Count the filtered set BEFORE paginating, against the same query
    # graph (so joins added by the status filter are honoured). The
    # PHASE_1 scope above guarantees at most one phase row per entry, so
    # DISTINCT isn't strictly required — but use distinct() defensively
    # in case future code adds another join.
    total_q = select(func.count()).select_from(base.distinct().subquery())
    total = int((await session.execute(total_q)).scalar_one())

    items_q = (
        base.options(
            selectinload(PredictionEntry.phases),
            # v2.157.0 — admin Entries page needs owner display name, email
            # and paid_to per row. Eager-loaded here so the page renders
            # without an N+1 hit. User-facing endpoints use the same
            # service but their response schemas (EntryRead) drop owner.
            selectinload(PredictionEntry.user),
        )
        .order_by(PredictionEntry.entry_number)
        .offset(offset)
    )
    if limit is not None:
        items_q = items_q.limit(limit)
    items = list((await session.execute(items_q)).scalars().unique().all())
    return items, total


async def admin_get_events(
    session: AsyncSession, *, entry: PredictionEntry
) -> list[PredictionEntryEvent]:
    rows = (
        await session.execute(
            select(PredictionEntryEvent)
            .where(PredictionEntryEvent.entry_id == entry.id)
            .order_by(PredictionEntryEvent.created_at)
        )
    ).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
_SETTINGS_FIELDS: tuple[str, ...] = (
    "max_entries_per_user",
    "auto_create_first_entry",
    "allow_duplicate_from_existing",
    "allow_user_rename",
    "payment_mode",
    "block_unpaid_entry_submission",
    "show_entry_reference_publicly",
    "phase_scoped_status_enabled",
)
# Note: `allow_user_withdrawal`, `require_ready_before_submit`, and
# `bonus_questions_required_for_ready` were removed in the lifecycle
# simplification (READY status and user-initiated withdrawal are gone).
# The columns remain in the DB schema for backward compat but are no
# longer exposed via the entry-settings API.


def settings_dict(competition: Competition) -> dict[str, Any]:
    """Extract the 11 entry-settings fields from a competition."""
    return {f: getattr(competition, f) for f in _SETTINGS_FIELDS}


async def update_entry_settings(
    session: AsyncSession,
    *,
    competition: Competition,
    admin: User,
    updates: dict[str, Any],
    ctx: AuditContext | None = None,
) -> Competition:
    """Apply partial updates. Validates `max_entries_per_user` against
    current usage. Writes an audit event with the before/after diff."""
    # Validate max_entries_per_user against current highest active count.
    if "max_entries_per_user" in updates:
        new_max = updates["max_entries_per_user"]
        if new_max is not None and new_max < 1:
            raise EntryConfigError("max_entries_per_user must be ≥ 1")
        # Per the brief, can't reduce below the highest existing
        # active entry count per user. Compute that max.
        if new_max is not None:
            highest = (
                await session.execute(
                    select(func.count(PredictionEntry.id))
                    .where(
                        PredictionEntry.competition_id == competition.id,
                        PredictionEntry.withdrawn_at.is_(None),
                    )
                    .group_by(PredictionEntry.user_id)
                    .order_by(func.count(PredictionEntry.id).desc())
                    .limit(1)
                )
            ).scalar()
            if highest is not None and new_max < highest:
                raise EntryConfigError(
                    f"max_entries_per_user ({new_max}) cannot be below "
                    f"highest current active count per user ({highest})"
                )

    diff: dict[str, dict[str, Any]] = {}
    for field, value in updates.items():
        if value is None or field not in _SETTINGS_FIELDS:
            continue
        old = getattr(competition, field)
        if old == value:
            continue
        diff[field] = {"old": _serialize_for_audit(old), "new": _serialize_for_audit(value)}
        setattr(competition, field, value)
    competition.updated_at = utc_now()

    record_audit_event(
        session,
        event_type="competition.settings_updated",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="competition",
        subject_id=competition.id,
        ctx=ctx,
        metadata={"changes": diff},
    )
    await session.flush()
    return competition


def _serialize_for_audit(value: Any) -> Any:
    """Coerce enum / non-JSON-native values to a JSONB-safe representation."""
    if hasattr(value, "value"):  # Enum
        return value.value
    return value


# ---------------------------------------------------------------------------
# Active competition shortcut — used by API layer when caller didn't supply
# ---------------------------------------------------------------------------
async def get_active_competition(session: AsyncSession) -> Competition:
    """Return the single active competition (the one with is_active=True).

    Raises `EntryConfigError` if zero or multiple are active. The system
    is single-tournament for now; this is the boundary at which that
    assumption is enforced.
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active.is_(True))
    )
    rows = list(result.scalars().all())
    if not rows:
        raise EntryConfigError("No active competition")
    if len(rows) > 1:
        raise EntryConfigError(
            f"Multiple active competitions ({len(rows)}); expected exactly one"
        )
    return rows[0]
