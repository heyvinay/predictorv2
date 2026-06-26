"""Broadcast audience queries — five segments for the admin nudge tool.

v2.176.0. Powers the broadcast email card on /admin (Overview tab) and
the POST /admin/broadcasts* endpoints.

Five segments target distinct points in the engagement funnel:

* SUBMITTERS    — has ≥1 SUBMITTED entry phase. "Thanks; add another?"
* NO_ENTRY      — has zero PredictionEntry rows. "Come back and play."
* DRAFT_HOLDERS — has ≥1 DRAFT phase AND zero SUBMITTED phases.
                   "Finish your picks."
* POOL_GHOST    — has ≥1 ELIGIBLE-SUBMITTED phase-1 entry AND no
                   engagement signal since TOURNAMENT_START. "Come see
                   how your picks are doing." [NEW v2.176.0]
* LAPSING       — has ≥1 ELIGIBLE-SUBMITTED phase-1 entry AND latest
                   engagement signal is 3-7 days ago. "Matchday tomorrow."
                   [NEW v2.176.0]

The first three segments are mutually exclusive by construction.
POOL_GHOST and LAPSING are SUBSETS of SUBMITTERS (every ghost is also
a submitter). The admin picks one segment per broadcast; if you send
both "Thank submitters" and "Wake up Pool Ghosts" back-to-back, the
ghosts get both emails. This is intentional — the existing UX is
one-segment-per-send and the audit log + audience-count display make
mistakes recoverable.

Engagement signal architecture (Pool Ghost / Lapsing only): HYBRID.
Two sources, max-of-both is the user's "last seen":

  A. User.last_seen_at column — primary, updated by the
     get_current_user dependency on each authenticated request,
     throttled to once per LAST_SEEN_THROTTLE_S.
  B. PostHog $pageview events — fallback for users with persistent
     sessions that don't tick the column AND for client-side-only
     navigation. Fetched best-effort; any failure (network, timeout,
     missing key, malformed response) degrades silently to A alone.

Entry status lives on :class:`PredictionEntryPhase`, not
:class:`PredictionEntry`. The predicates correlate via a join.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    LAPSING_FRESH_DAYS,
    LAPSING_STALE_DAYS,
    TOURNAMENT_START,
)
from app.models._datetime import utc_now
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.models.user import User

# NOTE: posthog_read is imported lazily inside _build_engagement_input
# to break a circular dependency:
#   schemas/admin.py imports BroadcastSegment from this module
#   posthog_read.py imports EngagementSummary from schemas/admin.py
# A top-level `from app.services import posthog_read` here would close
# the loop and crash the backend at startup with a partial-init
# ImportError. The lazy import inside the one async function that needs
# it sidesteps the cycle entirely.

logger = logging.getLogger(__name__)


class BroadcastSegment(str, Enum):
    """Audience filter for the broadcast email tool."""

    SUBMITTERS = "submitters"
    NO_ENTRY = "no_entry"
    DRAFT_HOLDERS = "draft_holders"
    POOL_GHOST = "pool_ghost"        # NEW v2.176.0
    LAPSING = "lapsing"              # NEW v2.176.0
    # NEW v2.178.0 — one-off round-recap broadcast. Audience reuses the
    # SUBMITTERS predicate (everyone with ≥1 SUBMITTED entry phase), but
    # the email body is a tournament-progress recap rather than a
    # "thanks; add another?" pre-deadline nudge. The CTA points at the
    # leaderboard (post-deadline destination), UTM-tagged so PostHog can
    # attribute click-throughs.
    GROUP_R1_RECAP = "group_r1_recap"
    # NEW v2.180.0 — Round 2 recap. Same audience predicate as R1 (every
    # submitter), but the body anchors on standings highlights + the
    # Sunday-28 close. Mirror twin of R1 with one deliberate difference:
    # the R2 CTA is NOT UTM-tagged. R1's URL carried utm_source=email +
    # utm_campaign=group_r1_recap which contributed to Gmail's
    # promotional-bin classification; R2 ships clean to maximise inbox
    # placement. Trade-off: PostHog can no longer attribute per-round
    # click-throughs — deliverability beats analytics.
    GROUP_R2_RECAP = "group_r2_recap"
    # NEW v2.181.0 — Group Stage Final / winner announcement. Same
    # audience as the recap segments (every submitter). Body announces
    # the group-stage champion with their 4-part points breakdown
    # (outcome / exact / rarity / bonus) and the €183 group-stage prize.
    # Gated behind Competition.group_stage_winner_released — the email
    # template populates dynamic placeholders from the same service
    # that backs the dashboard's GroupStageWinnerCard, so the card
    # and the email are guaranteed to agree on the numbers. Subject
    # avoids "winner+announced" pair to stay spam-friendly.
    GROUP_STAGE_FINAL = "group_stage_final"


# Segments that need the engagement-signal fetch (PostHog + column).
# The other three predicates are pure SQL.
_ENGAGEMENT_DEPENDENT: frozenset[BroadcastSegment] = frozenset({
    BroadcastSegment.POOL_GHOST,
    BroadcastSegment.LAPSING,
})


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


@dataclass(frozen=True)
class EngagementInput:
    """One-shot engagement-signal snapshot used by POOL_GHOST and
    LAPSING predicate factories.

    ``posthog_last_seen[user_id]`` is the user's MAX(`$pageview`.timestamp)
    since the lookback cutoff. Empty dict ⇒ PostHog is disabled,
    unreachable, or returned no rows — predicates fall back to
    ``User.last_seen_at`` alone.
    """

    posthog_last_seen: dict[UUID, datetime] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engagement-input builder — best-effort PostHog fetch, silent degradation
# ---------------------------------------------------------------------------
async def _build_engagement_input() -> EngagementInput:
    """Best-effort PostHog fetch. ANY failure → empty input + WARN log.

    Predicates that consume this input MUST tolerate the empty case
    (they do — IN-empty-list resolves to literal False and the
    ``User.last_seen_at`` clauses still work). The audience count is
    computed from the column alone in that case.

    Hard rule: this function NEVER raises. The user-facing request
    path that calls it MUST NOT see PostHog errors.
    """
    # Pull a window slightly wider than the 7d lapsing window so the
    # Lapsing predicate has data for the [stale, fresh) bucket. We
    # subtract LAPSING_STALE_DAYS + a small safety margin, and clamp
    # so we never query before TOURNAMENT_START - 14 days (which is
    # enough headroom for the "since kickoff" Pool Ghost rule too).
    # Lazy import — see module-top NOTE for the circular-import reason.
    from app.services import posthog_read

    lookback = utc_now() - timedelta(days=LAPSING_STALE_DAYS + 7)
    cutoff = min(lookback, TOURNAMENT_START - timedelta(days=1))
    try:
        ph = await posthog_read.get_last_pageview_for_users_since(cutoff)
    except Exception as exc:  # noqa: BLE001 — explicit silent degradation
        logger.warning(
            "PostHog engagement fetch failed; degrading to column-only: %s",
            exc,
        )
        ph = {}
    return EngagementInput(posthog_last_seen=ph)


# ---------------------------------------------------------------------------
# Segment predicates — correlated EXISTS sub-selects against User.id.
# ---------------------------------------------------------------------------
def _has_submitted_phase_predicate():
    """User has ≥1 entry whose phase row is SUBMITTED.

    Existing pattern (pre-v2.176.0) — kept for SUBMITTERS audience
    stability. Does NOT filter by eligibility or phase=PHASE_1; in
    practice phase_2 rows stay DRAFT permanently so this still
    behaves correctly.
    """
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


def _eligible_submitted_predicate():
    """User has ≥1 ELIGIBLE submitted phase-1 entry.

    Tighter than _has_submitted_phase_predicate — adds the rarity-pool
    eligibility filter (is_disabled=False, withdrawn_at IS NULL) plus
    explicit phase=PHASE_1 (per CLAUDE.md "always filter to PHASE_1"
    rule). Shared base for POOL_GHOST and LAPSING. v2.176.0.
    """
    return (
        select(PredictionEntry.id)
        .join(
            PredictionEntryPhase,
            PredictionEntryPhase.entry_id == PredictionEntry.id,
        )
        .where(PredictionEntry.user_id == User.id)
        .where(PredictionEntry.is_disabled.is_(False))
        .where(PredictionEntry.withdrawn_at.is_(None))
        .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
        .where(PredictionEntryPhase.phase == PredictionPhase.PHASE_1)
        .exists()
    )


def _pool_ghost_predicate(eng: EngagementInput):
    """Eligible-submitted AND no engagement signal since TOURNAMENT_START.

    Engagement is computed from the max of A (User.last_seen_at) and B
    (PostHog $pageview). NULL last_seen_at counts as "no column signal"
    (handled via the is_not(None) guard — SQL three-valued logic would
    otherwise turn the whole predicate NULL).
    """
    column_active = and_(
        User.last_seen_at.is_not(None),
        User.last_seen_at >= TOURNAMENT_START,
    )
    posthog_active_ids = [
        uid for uid, ts in eng.posthog_last_seen.items()
        if ts >= TOURNAMENT_START
    ]
    posthog_active = (
        User.id.in_(posthog_active_ids)
        if posthog_active_ids
        else literal(False)
    )
    return (
        _eligible_submitted_predicate()
        & ~or_(column_active, posthog_active)
    )


def _lapsing_predicate(eng: EngagementInput):
    """Eligible-submitted AND last signal (max of A + B) in [stale, fresh) ago.

    Lapsing window today is [3d, 7d) ago. The user must have:
      (a) at least one signal — column or PostHog — falling in the
          [stale, fresh) window, AND
      (b) no signal more recent than ``fresh`` (otherwise they're still
          active and don't need a nudge).

    Users with no engagement at all are NOT lapsing — they're Pool Ghost
    candidates (handled by the other predicate). The mutual-exclusivity
    test in test_broadcast.py pins this contract.
    """
    now = utc_now()
    fresh_cutoff = now - timedelta(days=LAPSING_FRESH_DAYS)
    stale_cutoff = now - timedelta(days=LAPSING_STALE_DAYS)

    col_in_window = and_(
        User.last_seen_at.is_not(None),
        User.last_seen_at >= stale_cutoff,
        User.last_seen_at < fresh_cutoff,
    )
    col_fresh = and_(
        User.last_seen_at.is_not(None),
        User.last_seen_at >= fresh_cutoff,
    )

    ph_in_window_ids = [
        uid for uid, ts in eng.posthog_last_seen.items()
        if stale_cutoff <= ts < fresh_cutoff
    ]
    ph_fresh_ids = [
        uid for uid, ts in eng.posthog_last_seen.items()
        if ts >= fresh_cutoff
    ]
    ph_in_window = (
        User.id.in_(ph_in_window_ids)
        if ph_in_window_ids
        else literal(False)
    )
    ph_fresh = (
        User.id.in_(ph_fresh_ids) if ph_fresh_ids else literal(False)
    )

    return (
        _eligible_submitted_predicate()
        & or_(col_in_window, ph_in_window)
        & ~or_(col_fresh, ph_fresh)
    )


def _segment_predicate(
    segment: BroadcastSegment,
    eng: EngagementInput | None = None,
):
    """Map a segment enum to its where-clause predicate.

    ``eng`` is required for POOL_GHOST and LAPSING (the
    engagement-dependent segments). Callers should pre-fetch via
    ``_build_engagement_input()`` once per request and pass it in.
    """
    if segment == BroadcastSegment.SUBMITTERS:
        return _has_submitted_phase_predicate()
    if segment == BroadcastSegment.GROUP_R1_RECAP:
        # v2.178.0 — same audience as SUBMITTERS (≥1 SUBMITTED entry
        # phase). Distinct segment value purely so the email template
        # branches on a recap-specific body. Sharing the predicate
        # guarantees both broadcasts always agree on who counts as a
        # participant.
        return _has_submitted_phase_predicate()
    if segment == BroadcastSegment.GROUP_R2_RECAP:
        # v2.180.0 — same audience as R1 and SUBMITTERS. Shared predicate
        # so the three counts stay locked together; a recipient who got
        # the R1 recap is exactly the audience for R2.
        return _has_submitted_phase_predicate()
    if segment == BroadcastSegment.GROUP_STAGE_FINAL:
        # v2.181.0 — same audience as R1/R2/SUBMITTERS. The group-stage
        # winner announcement is celebratory not transactional; everyone
        # who entered the pool deserves to hear who won.
        return _has_submitted_phase_predicate()
    if segment == BroadcastSegment.NO_ENTRY:
        return _no_entries_predicate()
    if segment == BroadcastSegment.DRAFT_HOLDERS:
        # Has a draft, has NOT submitted anything. The "started but
        # didn't ship" segment. Once they submit any entry they
        # graduate to SUBMITTERS.
        return _has_draft_phase_predicate() & ~_has_submitted_phase_predicate()
    if segment == BroadcastSegment.POOL_GHOST:
        if eng is None:
            raise ValueError(
                "POOL_GHOST predicate requires EngagementInput — "
                "call _build_engagement_input() first"
            )
        return _pool_ghost_predicate(eng)
    if segment == BroadcastSegment.LAPSING:
        if eng is None:
            raise ValueError(
                "LAPSING predicate requires EngagementInput — "
                "call _build_engagement_input() first"
            )
        return _lapsing_predicate(eng)
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

    Engagement-dependent segments (POOL_GHOST / LAPSING) trigger one
    PostHog fetch per call. The fetch is cached for 5 minutes via
    ``posthog_read.py`` so repeated admin clicks don't hammer PostHog.
    """
    eng = (
        await _build_engagement_input()
        if segment in _ENGAGEMENT_DEPENDENT
        else None
    )
    stmt = (
        select(func.count(User.id))
        .where(*_base_clauses())
        .where(_segment_predicate(segment, eng))
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def count_all_audiences(
    session: AsyncSession,
) -> dict[BroadcastSegment, int]:
    """Counts for every segment. Engagement input fetched ONCE.

    Used by ``GET /admin/broadcasts/audience`` to populate the five
    count badges on page load with a single PostHog fetch covering
    both engagement-dependent segments.
    """
    eng = await _build_engagement_input()
    out: dict[BroadcastSegment, int] = {}
    for seg in BroadcastSegment:
        stmt = (
            select(func.count(User.id))
            .where(*_base_clauses())
            .where(_segment_predicate(seg, eng))
        )
        out[seg] = int((await session.execute(stmt)).scalar_one() or 0)
    return out


async def query_audience(
    session: AsyncSession, segment: BroadcastSegment
) -> list[AudienceRow]:
    """Return every matching user (user_id, email, name).

    Used both by:
    * the dry-run preview path (first 5 emails surfaced to the
      confirmation modal so the admin sees who they're about to nudge), and
    * the real broadcast loop (one Resend call per row, paced ~50ms).

    Ordered by ``User.created_at`` desc — newest signups first — to
    mirror the admin Users-list convention.
    """
    eng = (
        await _build_engagement_input()
        if segment in _ENGAGEMENT_DEPENDENT
        else None
    )
    stmt = (
        select(User)
        .where(*_base_clauses())
        .where(_segment_predicate(segment, eng))
        .order_by(User.created_at.desc())
    )
    users = (await session.execute(stmt)).scalars().all()
    return [
        AudienceRow(user_id=u.id, email=u.email, name=u.name or "")
        for u in users
    ]
