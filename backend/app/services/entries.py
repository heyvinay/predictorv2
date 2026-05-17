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
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
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
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
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
    (EntryStatus.DRAFT, EntryStatus.READY): {ActorRole.USER, ActorRole.ADMIN},
    (EntryStatus.READY, EntryStatus.DRAFT): {ActorRole.USER, ActorRole.ADMIN},
    (EntryStatus.READY, EntryStatus.SUBMITTED): {ActorRole.USER, ActorRole.ADMIN},
    (EntryStatus.SUBMITTED, EntryStatus.DRAFT): {ActorRole.USER, ActorRole.ADMIN},
    (EntryStatus.SUBMITTED, EntryStatus.LOCKED): {ActorRole.SYSTEM, ActorRole.ADMIN},
    # Whole-entry withdraw and admin disable do not transition the phase
    # status directly — they go through `withdraw_entry` and
    # `admin_disable_entry` respectively. Locked is terminal for edits.
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

    - Admins: always allowed.
    - Owner: always allowed (even for own withdrawn/disabled entries).
    - Non-owner / unauthenticated: allowed iff the competition's Phase 1
      deadline has passed AND the entry is eligible (not disabled, not
      withdrawn).

    The lock signal is :func:`app.services.locking.is_phase1_locked`. Once
    that passes, all prediction contents are public knowledge and rank
    standings can be shared without compromising the blind pool.
    """
    if viewer is not None:
        if viewer.is_admin:
            return
        if entry.user_id == viewer.id:
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
    """A phase is locked when its status is `locked` OR the deadline passed."""
    if phase_row.status == EntryStatus.LOCKED:
        return True
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
    """All entries owned by `user` in `competition`, with phases."""
    result = await session.execute(
        select(PredictionEntry)
        .options(selectinload(PredictionEntry.phases))
        .where(
            PredictionEntry.user_id == user.id,
            PredictionEntry.competition_id == competition.id,
        )
        .order_by(PredictionEntry.entry_number)
    )
    return list(result.scalars().all())


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


async def mark_phase_ready(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    phase: PredictionPhase,
    competition: Competition,
    actor_role: ActorRole = ActorRole.USER,
    ctx: AuditContext | None = None,
) -> PredictionEntryPhase:
    """`draft → ready`. Requires entry active, phase not locked."""
    if actor_role == ActorRole.USER:
        await _ensure_owner(entry, user)
    if not _entry_is_active(entry):
        raise EntryStateError("Entry is withdrawn or disabled")

    phase_row = _phase_record(entry, phase)
    if _phase_is_locked(phase_row, competition):
        raise EntryStateError(f"Phase {phase.value} is locked")
    _check_transition_allowed(phase_row.status, EntryStatus.READY, actor_role)

    # Bonus-completeness gate. Bonus questions live with Phase 1 (locked
    # alongside the group stage in the brief), so we only enforce this on
    # PHASE_1 transitions. When the competition flag is off, this is a
    # no-op — users may go ready without answering bonus questions.
    if (
        competition.bonus_questions_required_for_ready
        and phase == PredictionPhase.PHASE_1
    ):
        # Lazy import keeps the entries module independent of the bonus
        # YAML loader at import time (helpful for the test stack).
        from app.services.bonus import get_questions

        all_qids = {q.id for q in get_questions()}
        answered_qids = {
            qid
            for (qid,) in (
                await session.execute(
                    select(BonusPrediction.question_id).where(
                        BonusPrediction.entry_id == entry.id,
                        BonusPrediction.answer.isnot(None),
                        BonusPrediction.answer != "",
                    )
                )
            ).all()
        }
        missing = all_qids - answered_qids
        if missing:
            raise EntryValidationError(
                f"Bonus answers required: {len(missing)} of "
                f"{len(all_qids)} questions still blank"
            )

    # Optional duplicate check at ready time (recommended by brief).
    conflict = await _find_duplicate_eligible_entry(
        session, entry=entry, phase=phase
    )
    if conflict is not None:
        raise EntryDuplicateError(
            f"Predictions identical to entry {conflict}",
            conflict_reference=conflict,
        )

    prev = phase_row.status
    phase_row.status = EntryStatus.READY
    phase_row.ready_at = utc_now()
    phase_row.updated_at = utc_now()

    await _write_transition_event(
        session,
        entry=entry,
        phase=phase,
        from_status=prev,
        to_status=EntryStatus.READY,
        actor_user_id=user.id,
        actor_role=actor_role,
        reason=None,
        audit_event_type="entry.phase_ready",
        ctx=ctx,
    )
    await session.flush()
    return phase_row


async def submit_phase(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    phase: PredictionPhase,
    competition: Competition,
    actor_role: ActorRole = ActorRole.USER,
    ctx: AuditContext | None = None,
) -> PredictionEntryPhase:
    """`ready → submitted`. Enforces payment + duplicate-submission rules."""
    if actor_role == ActorRole.USER:
        await _ensure_owner(entry, user)
    if not _entry_is_active(entry):
        raise EntryStateError("Entry is withdrawn or disabled")

    phase_row = _phase_record(entry, phase)
    if _phase_is_locked(phase_row, competition):
        raise EntryStateError(f"Phase {phase.value} is locked")

    # If require_ready_before_submit is true, the from-status MUST be
    # ready. If false, a direct draft → submitted is permitted.
    if competition.require_ready_before_submit:
        if phase_row.status != EntryStatus.READY:
            raise EntryStateError(
                f"Phase must be ready before submit; current: {phase_row.status.value}"
            )
    elif phase_row.status not in {EntryStatus.DRAFT, EntryStatus.READY}:
        raise EntryStateError(
            f"Cannot submit from {phase_row.status.value}"
        )

    # Payment rule: when per-entry payment is configured and the
    # competition blocks unpaid submission, the entry must be paid.
    if (
        competition.block_unpaid_entry_submission
        and not entry.paid
    ):
        raise EntryValidationError("Entry is unpaid; submission blocked")

    # Duplicate-submission check — must run on submit per brief.
    conflict = await _find_duplicate_eligible_entry(
        session, entry=entry, phase=phase
    )
    if conflict is not None:
        raise EntryDuplicateError(
            f"Predictions identical to entry {conflict}",
            conflict_reference=conflict,
        )

    prev = phase_row.status
    # If the transition is draft → submitted (when ready-gate is off),
    # mark the transition as ready→submitted in the audit log to keep
    # the lifecycle representation consistent. For the entry-event row
    # we record the actual from-state.
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
        audit_event_type="entry.phase_submitted",
        ctx=ctx,
    )
    await session.flush()
    return phase_row


async def reopen_phase(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    phase: PredictionPhase,
    competition: Competition,
    actor_role: ActorRole = ActorRole.USER,
    ctx: AuditContext | None = None,
) -> PredictionEntryPhase:
    """`submitted → draft`. Blocked once the phase has locked."""
    if actor_role == ActorRole.USER:
        await _ensure_owner(entry, user)
    if not _entry_is_active(entry):
        raise EntryStateError("Entry is withdrawn or disabled")

    phase_row = _phase_record(entry, phase)
    if _phase_is_locked(phase_row, competition):
        raise EntryStateError(
            f"Phase {phase.value} is locked; reopen no longer possible"
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
        audit_event_type="entry.phase_reopened",
        ctx=ctx,
    )
    await session.flush()
    return phase_row


async def withdraw_entry(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    competition: Competition,
    reason: str | None = None,
    actor_role: ActorRole = ActorRole.USER,
    ctx: AuditContext | None = None,
) -> PredictionEntry:
    """Mark the whole entry as withdrawn. All phases get a `withdrawn`
    event written. The phase status itself stays untouched if locked
    (locked is terminal), otherwise we move it to `withdrawn`."""
    if actor_role == ActorRole.USER:
        await _ensure_owner(entry, user)
        if not competition.allow_user_withdrawal:
            raise EntryValidationError("Withdrawal is disabled for this competition")
    if entry.withdrawn_at is not None:
        raise EntryStateError("Entry already withdrawn")
    if entry.is_disabled:
        raise EntryStateError("Cannot withdraw a disabled entry")

    now = utc_now()
    entry.withdrawn_at = now
    entry.withdrawn_reason = reason
    entry.updated_at = now

    for phase_row in entry.phases:
        if phase_row.status == EntryStatus.LOCKED:
            # Locked is terminal; record the audit but don't mutate status.
            await _write_transition_event(
                session,
                entry=entry,
                phase=phase_row.phase,
                from_status=phase_row.status,
                to_status=phase_row.status,
                actor_user_id=user.id,
                actor_role=actor_role,
                reason=reason,
                audit_event_type="entry.withdrawn",
                ctx=ctx,
                extra_metadata={"phase_locked": True},
            )
            continue
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
            actor_role=actor_role,
            reason=reason,
            audit_event_type="entry.withdrawn",
            ctx=ctx,
        )
    await session.flush()
    return entry


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

    "Eligible" = status ∈ {submitted, locked}, not withdrawn, not disabled.

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
            PredictionEntryPhase.status.in_(
                [EntryStatus.SUBMITTED, EntryStatus.LOCKED]
            ),
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


async def admin_list_entries(
    session: AsyncSession,
    *,
    competition: Competition,
    user_id: uuid.UUID | None = None,
    reference: str | None = None,
    status: EntryStatus | None = None,
    paid: bool | None = None,
    disabled: bool | None = None,
) -> list[PredictionEntry]:
    """Admin list with filters."""
    q = (
        select(PredictionEntry)
        .options(selectinload(PredictionEntry.phases))
        .where(PredictionEntry.competition_id == competition.id)
    )
    if user_id is not None:
        q = q.where(PredictionEntry.user_id == user_id)
    if reference is not None:
        q = q.where(PredictionEntry.reference == reference)
    if paid is not None:
        q = q.where(PredictionEntry.paid == paid)
    if disabled is not None:
        q = q.where(PredictionEntry.is_disabled == disabled)
    if status is not None:
        # Filter on whether the entry has at least one phase with this
        # status. Status is per-phase, not per-entry, so this is the
        # most useful semantic for admin search.
        q = q.join(
            PredictionEntryPhase,
            PredictionEntry.id == PredictionEntryPhase.entry_id,
        ).where(PredictionEntryPhase.status == status)
    q = q.order_by(PredictionEntry.entry_number)
    return list((await session.execute(q)).scalars().unique().all())


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
    "allow_user_withdrawal",
    "require_ready_before_submit",
    "payment_mode",
    "block_unpaid_entry_submission",
    "show_entry_reference_publicly",
    "phase_scoped_status_enabled",
    "bonus_questions_required_for_ready",
)


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
