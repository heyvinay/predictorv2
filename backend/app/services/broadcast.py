"""Broadcast audience queries — three segments for the admin nudge tool.

v2.160.0. Powers the broadcast email card on /admin (Overview tab) and
the three POST /admin/broadcasts* endpoints.

Segments target distinct points in the engagement funnel so the admin
can send a tailored message to each:

* SUBMITTERS    — has ≥1 SUBMITTED entry phase. "Thanks; add another?"
* NO_ENTRY      — has zero PredictionEntry rows. "Come back and play."
* DRAFT_HOLDERS — has ≥1 DRAFT phase AND zero SUBMITTED phases.
                   "Finish your picks."

Mutually-exclusive by construction: a user with one DRAFT and one
SUBMITTED entry is a SUBMITTER (not a draft-holder), because the
DRAFT_HOLDERS predicate excludes any user with a SUBMITTED phase.
SUBMITTERS sends a "thanks" message regardless of any drafts still
floating around — the user has already converted, drafts are tinkering.

All three queries are bounded to onboarded, active users
(``name IS NOT NULL AND is_active = TRUE``). Magic-link / OAuth users
who never confirmed sit in the inactive cohorts handled separately by
:func:`app.services.users.list_inactive_emails` for the re-engagement
CSV export.

Entry status lives on :class:`PredictionEntryPhase`, not
:class:`PredictionEntry`. The predicates below correlate via a join on
``entry_id`` rather than reading a status column on PredictionEntry
itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.user import User


class BroadcastSegment(str, Enum):
    """Audience filter for the broadcast email tool."""

    SUBMITTERS = "submitters"
    NO_ENTRY = "no_entry"
    DRAFT_HOLDERS = "draft_holders"


@dataclass(frozen=True)
class AudienceRow:
    """One recipient.

    ``name`` is guaranteed non-None (every segment filters on
    ``User.name IS NOT NULL``) — but we still tolerate empty string in
    the email template's salutation fallback.
    """

    user_id: UUID
    email: str
    name: str


# ---------------------------------------------------------------------------
# Segment predicates — correlated EXISTS sub-selects against User.id.
# ---------------------------------------------------------------------------
def _has_submitted_phase_predicate():
    """User has ≥1 entry whose phase row is SUBMITTED."""
    return (
        select(PredictionEntry.id)
        .join(
            PredictionEntryPhase,
            PredictionEntryPhase.entry_id == PredictionEntry.id,
        )
        .where(PredictionEntry.user_id == User.id)
        .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
        .exists()
    )


def _no_entries_predicate():
    """User has zero PredictionEntry rows."""
    return ~(
        select(PredictionEntry.id)
        .where(PredictionEntry.user_id == User.id)
        .exists()
    )


def _has_draft_phase_predicate():
    """User has ≥1 entry whose phase row is DRAFT."""
    return (
        select(PredictionEntry.id)
        .join(
            PredictionEntryPhase,
            PredictionEntryPhase.entry_id == PredictionEntry.id,
        )
        .where(PredictionEntry.user_id == User.id)
        .where(PredictionEntryPhase.status == EntryStatus.DRAFT)
        .exists()
    )


def _segment_predicate(segment: BroadcastSegment):
    """Map a segment enum value to its where-clause predicate."""
    if segment == BroadcastSegment.SUBMITTERS:
        return _has_submitted_phase_predicate()
    if segment == BroadcastSegment.NO_ENTRY:
        return _no_entries_predicate()
    if segment == BroadcastSegment.DRAFT_HOLDERS:
        # Has a draft, has NOT submitted anything. The "started but
        # didn't ship" segment. Once they submit any entry they
        # graduate to SUBMITTERS.
        return _has_draft_phase_predicate() & ~_has_submitted_phase_predicate()
    raise ValueError(f"Unknown segment: {segment!r}")


def _base_clauses():
    """Shared filters: onboarding-complete AND active."""
    return (User.name.is_not(None), User.is_active.is_(True))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def count_audience(
    session: AsyncSession, segment: BroadcastSegment
) -> int:
    """How many users would receive this broadcast?

    Single COUNT query, no row fetch. Used by the audience-counts
    endpoint that feeds the live count badges on the broadcast card.
    """
    stmt = (
        select(func.count(User.id))
        .where(*_base_clauses())
        .where(_segment_predicate(segment))
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def count_all_audiences(
    session: AsyncSession,
) -> dict[BroadcastSegment, int]:
    """Convenience wrapper — counts every segment.

    Used by ``GET /admin/broadcasts/audience`` to populate the three
    count badges on page load with a single round-trip from the admin's
    perspective (the three queries run sequentially server-side, but
    that's three fast index lookups, not three full table scans).
    """
    return {seg: await count_audience(session, seg) for seg in BroadcastSegment}


async def query_audience(
    session: AsyncSession, segment: BroadcastSegment
) -> list[AudienceRow]:
    """Return every matching user (user_id, email, name).

    Used both by:
    * the dry-run preview path (first 5 emails surfaced to the
      confirmation modal so the admin sees who they're about to nudge), and
    * the real broadcast loop (one Resend call per row, paced ~50ms).

    Ordered by ``User.created_at`` desc — newest signups first — to
    mirror the admin Users-list convention. The order doesn't affect
    recipients (everyone gets the same email), but it makes the
    sample-of-5 preview surface the most-recently-joined users, which
    is usually the most useful sanity check.
    """
    stmt = (
        select(User)
        .where(*_base_clauses())
        .where(_segment_predicate(segment))
        .order_by(User.created_at.desc())
    )
    users = (await session.execute(stmt)).scalars().all()
    return [
        AudienceRow(user_id=u.id, email=u.email, name=u.name or "")
        for u in users
    ]
