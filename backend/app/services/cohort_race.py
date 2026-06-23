"""Cohort race service — median rank per employer-cohort over time.

Atlas vs JMFA vs Guests is the tribal angle of the race-tab redesign.
Median (not mean) is used because cohort sizes are uneven and outliers
matter less. Cohorts with fewer than 3 entries are suppressed from the
response (statistical-noise floor).

All datetimes returned are aware-UTC per CLAUDE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import median
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entry import PredictionEntry
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.user import User
from app.models._datetime import utc_now
from app.services.scoring import eligible_entry_ids_select


MIN_COHORT_SIZE = 3

CohortKey = Literal["atlas", "jmfa", "guests", "all"]


def _classify(employer: str | None) -> CohortKey:
    """Map raw ``User.employer`` to the cohort key the API exposes.

    ``"atlas"`` and ``"jmfa"`` map directly; anything else (including
    ``None``, ``"neither"``, or any unknown value) maps to ``"guests"``.
    """
    if employer == "atlas":
        return "atlas"
    if employer == "jmfa":
        return "jmfa"
    return "guests"


@dataclass
class CohortPoint:
    captured_date: date
    median_rank: float


@dataclass
class CohortItem:
    cohort: CohortKey
    entry_count: int
    points: list[CohortPoint]
    current_median_rank: float


@dataclass
class CohortAnnotation:
    cohort: CohortKey
    captured_date: date
    caption: str


@dataclass
class CohortTrailResult:
    cohorts: list[CohortItem]
    annotations: list[CohortAnnotation]
    generated_at: datetime


async def compute_cohort_trail(
    session: AsyncSession,
    *,
    days: int = 30,
) -> CohortTrailResult:
    """Return median-rank-per-day trails for cohorts with >= MIN_COHORT_SIZE entries.

    Pre-deadline (blind-pool not open) returns empty cohorts + annotations.
    """
    from app.services.locking import is_phase1_locked

    if not await is_phase1_locked(session):
        return CohortTrailResult(cohorts=[], annotations=[], generated_at=utc_now())

    today = date.today()
    earliest = today - timedelta(days=days - 1)

    # Single join query: snapshot rows for eligible entries in the window.
    stmt = (
        select(
            LeaderboardSnapshot.captured_date,
            LeaderboardSnapshot.position,
            User.employer,
            PredictionEntry.id,
        )
        .join(PredictionEntry, PredictionEntry.id == LeaderboardSnapshot.entry_id)
        .join(User, User.id == PredictionEntry.user_id)
        .where(LeaderboardSnapshot.entry_id.in_(eligible_entry_ids_select()))
        .where(LeaderboardSnapshot.captured_date >= earliest)
    )
    rows = (await session.execute(stmt)).all()

    # bucket: cohort → date → list of positions (lower = better).
    # 'all' is the pool-wide baseline — every eligible entry, regardless of
    # employer. Displayed first; never min-size-suppressed (the whole pool
    # is by definition the pool).
    bucket: dict[CohortKey, dict[date, list[int]]] = {
        "all": {},
        "atlas": {},
        "jmfa": {},
        "guests": {},
    }
    entry_ids_per_cohort: dict[CohortKey, set[str]] = {
        "all": set(),
        "atlas": set(),
        "jmfa": set(),
        "guests": set(),
    }

    for captured_date, position, employer, entry_id in rows:
        cohort = _classify(employer)
        entry_ids_per_cohort[cohort].add(str(entry_id))
        bucket[cohort].setdefault(captured_date, []).append(position)
        # Every row also contributes to the pool-wide 'all' baseline.
        entry_ids_per_cohort["all"].add(str(entry_id))
        bucket["all"].setdefault(captured_date, []).append(position)

    cohorts: list[CohortItem] = []
    # 'all' rendered first so it reads as the baseline in the chart legend.
    for cohort_key in ("all", "atlas", "jmfa", "guests"):
        by_date = bucket[cohort_key]
        entry_count = len(entry_ids_per_cohort[cohort_key])
        # 'all' is exempt from the min-size threshold.
        if cohort_key != "all" and entry_count < MIN_COHORT_SIZE:
            continue
        points = [
            CohortPoint(
                captured_date=d,
                median_rank=float(median(ranks)),
            )
            for d, ranks in sorted(by_date.items())
        ]
        if not points:
            continue
        cohorts.append(
            CohortItem(
                cohort=cohort_key,
                entry_count=entry_count,
                points=points,
                current_median_rank=points[-1].median_rank,
            )
        )

    annotations = _derive_annotations(cohorts)

    return CohortTrailResult(
        cohorts=cohorts,
        annotations=annotations,
        generated_at=utc_now(),
    )


def _derive_annotations(cohorts: list[CohortItem]) -> list[CohortAnnotation]:
    """Pin a 'broke clear of #75' annotation the first day a cohort's median drops
    below #75 in the visible window. At most one pin per cohort, capped at 3 total.
    """
    out: list[CohortAnnotation] = []
    for c in cohorts:
        prev_above = True
        for p in c.points:
            if prev_above and p.median_rank < 75:
                out.append(
                    CohortAnnotation(
                        cohort=c.cohort,
                        captured_date=p.captured_date,
                        caption=f"{c.cohort.title()} broke clear of #75",
                    )
                )
                break
            prev_above = p.median_rank >= 75
    return out[:3]
