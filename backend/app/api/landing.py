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
    # Submitted-entries count. Same shape as admin.py's overview-stats
    # query — DISTINCT on entry id because the join to phase rows is
    # one-to-many (phase_1 + phase_2 rows per entry); SUBMITTED on
    # either row counts the entry once.
    submitted_entries = (
        await session.scalar(
            select(func.count(func.distinct(PredictionEntry.id)))
            .join(
                PredictionEntryPhase,
                PredictionEntryPhase.entry_id == PredictionEntry.id,
            )
            .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
        )
    ) or 0
    # Active competition's entry fee. None / inactive → 0.0; the
    # frontend renders no pot when the value is zero.
    active_comp = (
        await session.execute(
            select(Competition).where(Competition.is_active.is_(True)).limit(1)
        )
    ).scalar_one_or_none()
    entry_fee = float(active_comp.entry_fee) if active_comp else 0.0
    prize_pot = entry_fee * submitted_entries
    return LandingStats(
        predictors_signed_up=int(total or 0),
        joined_in_last_hour=int(recent or 0),
        submitted_entries=int(submitted_entries),
        entry_fee_eur=entry_fee,
        prize_pot_eur=prize_pot,
    )
