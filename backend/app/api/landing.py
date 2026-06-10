"""Landing-page stats API (v2.160.x → v2.160.2).

Powers the social-proof card on the landing page:
  • total predictors signed up (onboarding-complete users)
  • signups in the last hour
  • prize pot = active competition's ``entry_fee × submitted_entries``

All values are deliberately public (no auth) — they're the same numbers
we'd happily print on a marketing landing page, and the social-proof
treatment is most useful for *unauthenticated* visitors deciding whether
to sign up. Authenticated users see the same numbers from the
welcome-card sibling.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.dependencies import DbSession
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.models.user import User


router = APIRouter()


class LandingStats(BaseModel):
    """Public snapshot for the social-proof card.

    ``predictors_signed_up`` — users who have completed onboarding
    (``User.name IS NOT NULL``). Excludes magic-link signups that never
    set a display name; they sit in the "verified-only" cohort and
    aren't really "in the pool" yet.

    ``joined_in_last_hour`` — same definition, filtered to
    ``created_at`` within the last 60 minutes. Drives the green
    "▲ N joined in the last hour" micro-line; the frontend hides
    the micro-line when this is zero.

    ``submitted_entries`` — total entries across all users with at
    least one phase row in ``SUBMITTED``. Drives the "X × €Y" tagline
    under the prize pot.

    ``entry_fee_eur`` — the active competition's entry fee in euros.
    ``0.0`` when there's no active competition (frontend hides the pot
    in that case).

    ``prize_pot_eur`` — ``entry_fee_eur × submitted_entries``. Same
    formula admin uses; computed server-side so the frontend doesn't
    need to know about ``entry_fee`` separately.
    """

    predictors_signed_up: int
    joined_in_last_hour: int
    submitted_entries: int
    entry_fee_eur: float
    prize_pot_eur: float


@router.get("/stats", response_model=LandingStats)
async def get_landing_stats(session: DbSession) -> LandingStats:
    """Total signed-up predictors + recent-joiner delta + prize pot.

    Single round-trip, a handful of cheap COUNT queries. No PII
    surfaced.
    """
    total = await session.scalar(
        select(func.count(User.id)).where(User.name.is_not(None))
    )
    one_hour_ago = utc_now() - timedelta(hours=1)
    recent = await session.scalar(
        select(func.count(User.id))
        .where(User.name.is_not(None))
        .where(User.created_at >= one_hour_ago)
    )
    # Active competition first — every downstream count is scoped to
    # it. None / inactive → empty pot (frontend hides the column).
    active_comp = (
        await session.execute(
            select(Competition).where(Competition.is_active.is_(True)).limit(1)
        )
    ).scalar_one_or_none()

    # Submitted-entries count — must match the admin /admin/entries
    # page's "Submitted" stat-card definition so the landing pot and
    # the admin headline don't disagree.
    #
    # The admin page filters to "actively eligible" entries in the
    # active competition (see admin_list_entries scoping +
    # frontend/src/routes/admin/entries/+page.svelte:161):
    #   • competition_id == active competition  ← critical: without
    #     this, entries from past / test competitions inflate the
    #     count (that was the 89-vs-60 discrepancy beyond the
    #     phase/withdrawn/disabled filters)
    #   • PHASE_1 status === SUBMITTED  (phase_2 is dormant for this
    #     competition; counting any-phase SUBMITTED also inflated by
    #     entries with phase_2 rows that linger from creation)
    #   • NOT withdrawn  (withdrawn_at IS NULL)
    #   • NOT disabled   (is_disabled = false)
    #
    # Withdrawn / disabled entries' phase_1 status is preserved when
    # the lifecycle flag flips, so without these guards they leak in.
    #
    # The admin /stats endpoint at admin.py:181-189 still uses the
    # older broader query — known follow-up; same fix applies there.
    if active_comp is None:
        submitted_entries = 0
    else:
        submitted_entries = (
            await session.scalar(
                select(func.count(func.distinct(PredictionEntry.id)))
                .join(
                    PredictionEntryPhase,
                    PredictionEntryPhase.entry_id == PredictionEntry.id,
                )
                .where(PredictionEntry.competition_id == active_comp.id)
                .where(PredictionEntryPhase.phase == PredictionPhase.PHASE_1)
                .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
                .where(PredictionEntry.withdrawn_at.is_(None))
                .where(PredictionEntry.is_disabled.is_(False))
            )
        ) or 0

    entry_fee = float(active_comp.entry_fee) if active_comp else 0.0
    prize_pot = entry_fee * submitted_entries
    return LandingStats(
        predictors_signed_up=int(total or 0),
        joined_in_last_hour=int(recent or 0),
        submitted_entries=int(submitted_entries),
        entry_fee_eur=entry_fee,
        prize_pot_eur=prize_pot,
    )
