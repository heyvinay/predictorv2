"""Landing-page stats API (v2.160.x).

Powers the social-proof card on the landing page:
  • total predictors signed up (onboarding-complete users)
  • signups in the last hour

Both counts are deliberately public (no auth) — they're the same numbers
we'd happily print on a marketing landing page, and the social-proof
treatment is most useful for *unauthenticated* visitors who are deciding
whether to sign up. Authenticated users see the same numbers from the
welcome-card sibling.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.dependencies import DbSession
from app.models._datetime import utc_now
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
    """

    predictors_signed_up: int
    joined_in_last_hour: int


@router.get("/stats", response_model=LandingStats)
async def get_landing_stats(session: DbSession) -> LandingStats:
    """Total signed-up predictors + recent-joiner delta.

    Single round-trip, two cheap COUNT queries. No PII surfaced.
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
    return LandingStats(
        predictors_signed_up=int(total or 0),
        joined_in_last_hour=int(recent or 0),
    )
