"""Post-deadline pool close-out (v2.166.0).

One admin-triggered action: disable the account of every user who ended
the competition without a single *counting* submission. "Counting"
means an entry with a SUBMITTED phase-1 row that is neither withdrawn
nor admin-disabled — the same eligibility shape the scoring engine
uses, NOT the looser broadcast-segment predicate (a user whose only
submitted entry was later withdrawn has no stake in the pool).

Hard rules:
* Admins are NEVER disabled (mirrors the API lockout guards — no
  sequence of clicks may leave production without an admin login).
* Refuses to run before the deadline — closing early would lock out
  people who are still allowed to submit.
* Idempotent — a second run finds nothing left to disable.
* One audit event carries the disabled user ids, so the action is
  fully reconstructable (and reversible per-user from /admin/users).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.models.entry import ActorRole, EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.models.user import User
from app.services.audit import AuditContext, record_audit_event
from app.services.entries import count_eligible_submitted_entries


class PoolCloseError(Exception):
    """Raised when the close-out cannot run (deadline not passed)."""


def _has_counting_submission_predicate(competition_id):
    """User owns ≥1 entry that actually counts: SUBMITTED phase-1 row,
    not withdrawn, not disabled, in this competition."""
    return (
        select(PredictionEntry.id)
        .join(
            PredictionEntryPhase,
            PredictionEntryPhase.entry_id == PredictionEntry.id,
        )
        .where(PredictionEntry.user_id == User.id)
        .where(PredictionEntry.competition_id == competition_id)
        .where(PredictionEntry.withdrawn_at.is_(None))
        .where(PredictionEntry.is_disabled.is_(False))
        .where(PredictionEntryPhase.phase == PredictionPhase.PHASE_1)
        .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
        .exists()
    )


def _deadline_passed(competition: Competition) -> bool:
    if competition.phase1_deadline is None:
        return False
    return aware_utc(utc_now()) >= aware_utc(competition.phase1_deadline)


@dataclass(frozen=True)
class PoolClosePreview:
    """Dry-run counts shown on the admin card before the real run."""

    deadline_passed: bool
    accounts_to_disable: int
    submitters_kept: int
    admins_exempt: int
    already_inactive: int
    drafts_withdrawn: int
    eligible_submitted_entries: int


@dataclass(frozen=True)
class PoolCloseResult:
    disabled_count: int
    disabled_user_ids: list[UUID]


async def _count(session: AsyncSession, *clauses) -> int:
    return int(
        (await session.execute(select(func.count(User.id)).where(*clauses)))
        .scalar_one()
    )


async def preview_pool_close(
    session: AsyncSession, competition: Competition
) -> PoolClosePreview:
    """Counts only — no writes. Safe to call any time."""
    has_submission = _has_counting_submission_predicate(competition.id)

    accounts_to_disable = await _count(
        session,
        User.is_active.is_(True),
        User.is_admin.is_(False),
        ~has_submission,
    )
    submitters_kept = await _count(
        session, User.is_active.is_(True), has_submission
    )
    admins_exempt = await _count(
        session, User.is_active.is_(True), User.is_admin.is_(True)
    )
    already_inactive = await _count(session, User.is_active.is_(False))

    drafts_withdrawn = int(
        (
            await session.execute(
                select(func.count(PredictionEntry.id)).where(
                    PredictionEntry.competition_id == competition.id,
                    PredictionEntry.withdrawn_reason == "competition_started",
                )
            )
        ).scalar_one()
    )
    eligible = await count_eligible_submitted_entries(
        session, competition=competition
    )

    return PoolClosePreview(
        deadline_passed=_deadline_passed(competition),
        accounts_to_disable=accounts_to_disable,
        submitters_kept=submitters_kept,
        admins_exempt=admins_exempt,
        already_inactive=already_inactive,
        drafts_withdrawn=drafts_withdrawn,
        eligible_submitted_entries=int(eligible),
    )


async def close_pool(
    session: AsyncSession,
    *,
    competition: Competition,
    admin: User,
    ctx: AuditContext | None = None,
) -> PoolCloseResult:
    """Disable every active, non-admin account without a counting
    submission. Commits. One `admin.pool_closed` audit event carries
    the affected user ids."""
    if not _deadline_passed(competition):
        raise PoolCloseError(
            "The deadline has not passed yet — closing the pool now would "
            "disable accounts that are still allowed to submit."
        )

    rows = (
        (
            await session.execute(
                select(User).where(
                    User.is_active.is_(True),
                    User.is_admin.is_(False),
                    ~_has_counting_submission_predicate(competition.id),
                )
            )
        )
        .scalars()
        .all()
    )

    now = utc_now()
    disabled_ids: list[UUID] = []
    for user in rows:
        user.is_active = False
        user.updated_at = now
        disabled_ids.append(user.id)

    record_audit_event(
        session,
        event_type="admin.pool_closed",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="competition",
        subject_id=competition.id,
        ctx=ctx,
        metadata={
            "disabled_count": len(disabled_ids),
            "disabled_user_ids": [str(uid) for uid in disabled_ids],
        },
    )
    await session.commit()
    return PoolCloseResult(
        disabled_count=len(disabled_ids), disabled_user_ids=disabled_ids
    )
