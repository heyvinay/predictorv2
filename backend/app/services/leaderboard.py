"""Leaderboard service with caching.

Provides cached leaderboard calculations with position tracking.
Supports filtering by phase (overall, phase_1, phase_2).

Entries — not users — are the unit of ranking. A user with two eligible
entries shows up on the leaderboard twice. Eligibility is computed from
the entry's phase records:

- `is_disabled` must be false
- `withdrawn_at` must be null
- At least one `PredictionEntryPhase` for the entry must be in SUBMITTED
  or LOCKED (when `phase` filter is None — overall)
- When filtering to a specific phase, that phase's status must be in
  SUBMITTED or LOCKED for the entry to appear
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.models._datetime import utc_now
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardResponse, PointBreakdown
from app.services.scoring import calculate_entry_points


PhaseFilter = Literal["overall", "phase_1", "phase_2"] | None


@dataclass
class CachedLeaderboard:
    """Cached leaderboard data with TTL."""

    entries: list[LeaderboardEntry]
    last_calculated: datetime
    total_participants: int
    phase: str | None
    # Previous positions keyed by entry_id for movement tracking
    previous_positions: dict[uuid.UUID, int] = field(default_factory=dict)


# In-memory cache - keyed by phase
_cache: dict[str, CachedLeaderboard] = {}
_cache_ttl = timedelta(seconds=30)


def _get_phase_points(breakdown: PointBreakdown, phase: PhaseFilter) -> int:
    """Get points for a specific phase from a breakdown."""
    if phase == "phase_1":
        return breakdown.phase1.total
    elif phase == "phase_2":
        return breakdown.phase2.total
    else:
        return breakdown.total


async def get_entry_match_stats(
    session: AsyncSession, entry_id: uuid.UUID
) -> tuple[int, int]:
    """Return (correct_outcomes, exact_scores) counts for one entry's
    match predictions against finished fixtures."""
    result = await session.execute(
        select(MatchPrediction, Score)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(
            MatchPrediction.entry_id == entry_id,
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    rows = result.all()

    correct_outcomes = 0
    exact_scores = 0

    for prediction, score in rows:
        if not score:
            continue
        if prediction.predicted_outcome == score.outcome:
            correct_outcomes += 1
            if (
                prediction.home_score == score.final_home_score
                and prediction.away_score == score.final_away_score
            ):
                exact_scores += 1

    return correct_outcomes, exact_scores


async def _list_eligible_entries(
    session: AsyncSession, phase: PhaseFilter
) -> list[PredictionEntry]:
    """All entries eligible to appear on the leaderboard for `phase`.

    `phase=None` (overall): any phase row in SUBMITTED or LOCKED qualifies.
    `phase="phase_1"` / `"phase_2"`: that specific phase row must be
    SUBMITTED or LOCKED.
    """
    stmt = (
        select(PredictionEntry)
        .join(PredictionEntryPhase, PredictionEntryPhase.entry_id == PredictionEntry.id)
        .options(selectinload(PredictionEntry.user))
        .where(
            PredictionEntry.is_disabled == False,  # noqa: E712
            PredictionEntry.withdrawn_at.is_(None),
            PredictionEntryPhase.status == EntryStatus.SUBMITTED,
        )
        .distinct()
    )

    if phase == "phase_1":
        stmt = stmt.where(PredictionEntryPhase.phase == PredictionPhase.PHASE_1)
    elif phase == "phase_2":
        stmt = stmt.where(PredictionEntryPhase.phase == PredictionPhase.PHASE_2)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def calculate_leaderboard(
    session: AsyncSession,
    force_refresh: bool = False,
    phase: PhaseFilter = None,
) -> LeaderboardResponse:
    """Calculate leaderboard with caching.

    Args:
        session: Database session
        force_refresh: If True, bypass cache
        phase: Filter by phase ("phase_1", "phase_2", or None for overall)

    Returns:
        LeaderboardResponse with one row per eligible entry, sorted by
        the chosen phase's points. Ties are broken by exact_scores.
    """
    global _cache

    now = utc_now()
    cache_key = phase or "overall"

    # Return cached data if valid
    if not force_refresh and cache_key in _cache:
        cached = _cache[cache_key]
        if (now - cached.last_calculated) < _cache_ttl:
            return LeaderboardResponse(
                entries=cached.entries,
                last_calculated=cached.last_calculated,
                total_participants=cached.total_participants,
                phase=cached.phase,
            )

    # Previous positions keyed by entry_id (used for movement deltas)
    previous_positions: dict[uuid.UUID, int] = {}
    if cache_key in _cache:
        previous_positions = {
            e.entry_id: e.position for e in _cache[cache_key].entries
        }

    eligible = await _list_eligible_entries(session, phase)

    entries: list[LeaderboardEntry] = []
    for entry in eligible:
        breakdown = await calculate_entry_points(session, entry.id)
        correct_outcomes, exact_scores = await get_entry_match_stats(session, entry.id)
        phase_points = _get_phase_points(breakdown, phase)

        entries.append(
            LeaderboardEntry(
                entry_id=entry.id,
                entry_reference=entry.reference,
                entry_name=entry.display_name,
                user_id=entry.user_id,
                user_name=entry.user.name if entry.user else "Unknown",
                position=0,  # Set after sorting
                total_points=phase_points,
                breakdown=breakdown,
                correct_outcomes=correct_outcomes,
                exact_scores=exact_scores,
                movement=0,  # Calculated after positioning
            )
        )

    # Sort by points then exact-scores tiebreaker
    entries.sort(key=lambda e: (e.total_points, e.exact_scores), reverse=True)

    # Assign positions (handle ties — same points + same exact_scores share a place)
    current_position = 1
    for i, entry in enumerate(entries):
        if i > 0 and (
            entry.total_points < entries[i - 1].total_points
            or (
                entry.total_points == entries[i - 1].total_points
                and entry.exact_scores < entries[i - 1].exact_scores
            )
        ):
            current_position = i + 1
        entry.position = current_position

        prev_pos = previous_positions.get(entry.entry_id)
        if prev_pos is not None:
            entry.movement = prev_pos - entry.position  # Positive = moved up

    total_participants = len(entries)

    # Update cache
    _cache[cache_key] = CachedLeaderboard(
        entries=entries,
        last_calculated=now,
        total_participants=total_participants,
        phase=phase,
        previous_positions={e.entry_id: e.position for e in entries},
    )

    return LeaderboardResponse(
        entries=entries,
        last_calculated=now,
        total_participants=total_participants,
        phase=phase,
    )


def invalidate_cache() -> None:
    """Invalidate the leaderboard cache.

    Call this when scores are updated to force recalculation.
    """
    global _cache
    _cache = {}


def set_cache_ttl(seconds: int) -> None:
    """Set the cache TTL in seconds."""
    global _cache_ttl
    _cache_ttl = timedelta(seconds=seconds)
