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

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.models._datetime import utc_now
from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score
from app.services.bonus import answer_in, get_questions
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardResponse, PointBreakdown
from app.services.scoring import (
    calculate_entry_points,
    get_actual_advancement,
    get_all_outcome_counts,
)


PhaseFilter = Literal["overall", "phase_1", "phase_2"] | None

logger = logging.getLogger(__name__)


@dataclass
class CachedLeaderboard:
    """Cached leaderboard data with TTL."""

    entries: list[LeaderboardEntry]
    last_calculated: datetime
    total_participants: int
    phase: str | None
    # Previous positions keyed by entry_id for movement tracking
    previous_positions: dict[uuid.UUID, int] = field(default_factory=dict)
    # Marked by expire_cache() (score sync) — a stale board is still
    # servable via stale-while-revalidate, unlike a dropped one.
    stale: bool = False


# In-memory cache - keyed by phase.
# NOTE: this cache is per-process. Correct for the current single-worker
# deployment; if uvicorn is ever run with --workers>1 each worker keeps its
# own cache and invalidation signal, so move this to a shared store (Redis /
# a DB last-invalidated timestamp) before scaling out.
_cache: dict[str, CachedLeaderboard] = {}
_cache_ttl = timedelta(seconds=30)

# Per-key locks for single-flight rebuilds (see calculate_leaderboard).
_cache_locks: dict[str, asyncio.Lock] = {}

# Strong references to in-flight background refresh tasks, keyed like
# _cache. asyncio only weak-refs tasks, so without these a refresh could
# be garbage-collected mid-run; presence of a live task also acts as the
# "refresh already scheduled" guard.
_refresh_tasks: dict[str, "asyncio.Task[None]"] = {}

# Session factory for background refreshes. Overridable in tests (point
# it at the test engine's factory); production lazily resolves the app's
# global async_session_maker so this module keeps zero import-time
# dependency on app.database.
_background_session_factory: Callable[[], AsyncSession] | None = None


def _make_background_session() -> AsyncSession:
    if _background_session_factory is not None:
        return _background_session_factory()
    from app.database import async_session_maker

    return async_session_maker()


def _lock_for(cache_key: str) -> asyncio.Lock:
    lock = _cache_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _cache_locks[cache_key] = lock
    return lock


def _is_fresh(cached: CachedLeaderboard, now: datetime) -> bool:
    return not cached.stale and (now - cached.last_calculated) < _cache_ttl


def _schedule_background_refresh(phase: PhaseFilter, cache_key: str) -> None:
    """Kick off (at most one) off-request rebuild for `cache_key`.

    Part of the stale-while-revalidate path: the caller has already been
    served the expired board, so the rebuild's seconds-long cost lands
    here instead of on a user request.
    """
    existing = _refresh_tasks.get(cache_key)
    if existing is not None and not existing.done():
        return

    async def _refresh() -> None:
        async with _lock_for(cache_key):
            now = utc_now()
            cached = _cache.get(cache_key)
            if cached is not None and _is_fresh(cached, now):
                return  # rebuilt by someone else while we waited
            async with _make_background_session() as session:
                await _rebuild_leaderboard(session, phase, cache_key, now)

    def _log_failure(task: "asyncio.Task[None]") -> None:
        if not task.cancelled() and task.exception() is not None:
            logger.warning(
                "background leaderboard refresh for %r failed: %s",
                cache_key,
                task.exception(),
            )

    task = asyncio.create_task(_refresh())
    task.add_done_callback(_log_failure)
    _refresh_tasks[cache_key] = task


def _response_from_cache(cached: CachedLeaderboard) -> LeaderboardResponse:
    # Local import keeps app.services.sheets_sync (and its lazy gspread
    # dependency surface) off the leaderboard's hot-path imports.
    from app.services.sheets_sync import get_published_sheet_url  # noqa: PLC0415

    return LeaderboardResponse(
        entries=cached.entries,
        last_calculated=cached.last_calculated,
        total_participants=cached.total_participants,
        phase=cached.phase,
        published_sheet_url=get_published_sheet_url(),
    )


def _get_phase_points(breakdown: PointBreakdown, phase: PhaseFilter) -> int:
    """Get points for a specific phase from a breakdown."""
    if phase == "phase_1":
        return breakdown.phase1.total
    elif phase == "phase_2":
        return breakdown.phase2.total
    else:
        return breakdown.total


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

    # Fast path: return cached data if valid (no lock needed).
    if not force_refresh and cache_key in _cache:
        cached = _cache[cache_key]
        if _is_fresh(cached, now):
            return _response_from_cache(cached)
        # Stale-while-revalidate: the rebuild takes seconds against the
        # live pool (183 entries × full scoring), and with score-sync
        # expiring the cache every minute during matches it used to land
        # on a user request almost every page load — the dashboard's
        # first paint blocked on it. Serve the expired board instantly
        # and rebuild off-request; the next call gets the fresh one.
        _schedule_background_refresh(phase, cache_key)
        return _response_from_cache(cached)

    # Cold cache (or force_refresh): block on the rebuild — there is
    # nothing stale to serve. Single-flight: only one coroutine rebuilds
    # per cache key; the rest wait here and serve the re-checked cache.
    async with _lock_for(cache_key):
        now = utc_now()
        if not force_refresh and cache_key in _cache:
            cached = _cache[cache_key]
            if _is_fresh(cached, now):
                return _response_from_cache(cached)

        return await _rebuild_leaderboard(session, phase, cache_key, now)


async def _load_team_picks(
    session: AsyncSession, entry_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, list[str]]]:
    """Champion ("winner") and finalist ("final") picks per entry.

    PHASE_1 ONLY — every entry carries a dormant phase_2 row set; joining
    without the phase filter double-counts (★ CLAUDE.md invariant).

    Returns {entry_id: {"winner": [team], "final": [team, team]}}.
    """
    if not entry_ids:
        return {}
    result = await session.execute(
        select(TeamPrediction.entry_id, TeamPrediction.stage, TeamPrediction.team)
        .where(TeamPrediction.entry_id.in_(entry_ids))
        .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
        .where(TeamPrediction.stage.in_(["winner", "final"]))
    )
    picks: dict[uuid.UUID, dict[str, list[str]]] = {}
    for entry_id, stage, team in result.all():
        picks.setdefault(entry_id, {"winner": [], "final": []})[stage].append(team)
    return picks


async def _load_bonus_splits(
    session: AsyncSession, entry_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """Settled bonus points per entry split by category — (group, knockout).

    group_stage questions land in the Group column, everything else
    (top_flop / awards) in the Knockout column. Uses the same answer_in
    matcher as calculate_bonus_points so the split always sums to
    breakdown.bonus_question_points.
    """
    if not entry_ids:
        return {}
    ans_rows = (await session.execute(select(BonusAnswer))).scalars().all()
    if not ans_rows:
        return {}
    correct_by_qid: dict[str, list[str]] = {}
    for a in ans_rows:
        correct_by_qid.setdefault(a.question_id, []).append(a.correct_answer)

    questions = {q.id: q for q in get_questions()}
    pred_rows = (
        await session.execute(
            select(BonusPrediction)
            .where(BonusPrediction.entry_id.in_(entry_ids))
            .where(BonusPrediction.question_id.in_(list(correct_by_qid.keys())))
        )
    ).scalars().all()

    splits: dict[uuid.UUID, tuple[int, int]] = {}
    for pred in pred_rows:
        question = questions.get(pred.question_id)
        if question is None:
            continue
        if not answer_in(pred.answer, correct_by_qid[pred.question_id]):
            continue
        group, knockout = splits.get(pred.entry_id, (0, 0))
        if question.category == "group_stage":
            group += question.points
        else:
            knockout += question.points
        splits[pred.entry_id] = (group, knockout)
    return splits


async def get_eliminated_teams(session: AsyncSession) -> set[str]:
    """Teams provably out of the tournament. Conservative: alive until
    elimination is certain.

    Two elimination paths:
    1. Lost a FINISHED knockout match (`Score.outcome` resolves the winner
       after ET/pens — the level-knockout guard forbids drawn KO scores).
    2. Failed to qualify from the group: only once EVERY round_of_32
       fixture is fully seeded with real teams (each lineup name must be a
       team we saw in a group fixture — Football-Data placeholders like
       "Winner of Match 32" don't qualify, which keeps a half-seeded round
       from wrongly eliminating qualified teams).
    """
    result = await session.execute(
        select(Fixture, Score).outerjoin(Score, Fixture.id == Score.fixture_id)
    )
    rows = result.all()

    group_teams: set[str] = set()
    ko_lineup_teams: set[str] = set()
    eliminated: set[str] = set()
    r32_fixtures: list[Fixture] = []

    for fixture, score in rows:
        teams = [t for t in (fixture.home_team, fixture.away_team) if t]
        if fixture.stage == "group":
            group_teams.update(teams)
            continue

        ko_lineup_teams.update(teams)
        if fixture.stage == "round_of_32":
            r32_fixtures.append(fixture)

        # Path 1: loser of a finished knockout match is out.
        if fixture.status == MatchStatus.FINISHED and score:
            if score.outcome == "1" and fixture.away_team:
                eliminated.add(fixture.away_team)
            elif score.outcome == "2" and fixture.home_team:
                eliminated.add(fixture.home_team)

    # Path 2: group-stage non-qualifiers, once the R32 lineup is real.
    r32_fully_seeded = bool(r32_fixtures) and all(
        f.home_team
        and f.away_team
        and f.home_team in group_teams
        and f.away_team in group_teams
        for f in r32_fixtures
    )
    if r32_fully_seeded:
        eliminated.update(group_teams - ko_lineup_teams)

    return eliminated


async def _load_yesterday_positions(
    session: AsyncSession,
) -> dict[uuid.UUID, int]:
    """Most recent pre-today snapshot position per entry (one query).

    Drives `daily_movement`. Entries with no prior-day snapshot are absent
    from the result (→ daily_movement stays None).
    """
    today = utc_now().date()
    result = await session.execute(
        select(
            LeaderboardSnapshot.entry_id,
            LeaderboardSnapshot.position,
            LeaderboardSnapshot.captured_date,
        ).where(LeaderboardSnapshot.captured_date < today)
    )
    latest: dict[uuid.UUID, tuple] = {}
    for entry_id, position, captured_date in result.all():
        prev = latest.get(entry_id)
        if prev is None or captured_date > prev[1]:
            latest[entry_id] = (position, captured_date)
    return {entry_id: pos for entry_id, (pos, _d) in latest.items()}


async def _rebuild_leaderboard(
    session: AsyncSession,
    phase: PhaseFilter,
    cache_key: str,
    now: datetime,
) -> LeaderboardResponse:
    """Recompute the leaderboard and refresh the cache. Caller holds the
    single-flight lock for `cache_key`."""
    # Previous positions keyed by entry_id (used for movement deltas)
    previous_positions: dict[uuid.UUID, int] = {}
    if cache_key in _cache:
        previous_positions = {
            e.entry_id: e.position for e in _cache[cache_key].entries
        }

    eligible = await _list_eligible_entries(session, phase)

    # Shared inputs computed ONCE per rebuild, not once per entry — this
    # is what takes the cold rebuild from O(entries × fixtures) queries
    # down to a handful.
    outcome_counts_by_fixture = await get_all_outcome_counts(session)
    actual_advancement = await get_actual_advancement(session)

    # V4 row inputs — each one bulk query per rebuild (v2.164.0).
    team_picks = await _load_team_picks(session, [e.id for e in eligible])
    eliminated_teams = await get_eliminated_teams(session)
    yesterday_positions = await _load_yesterday_positions(session)
    bonus_splits = await _load_bonus_splits(session, [e.id for e in eligible])

    entries: list[LeaderboardEntry] = []
    for entry in eligible:
        breakdown = await calculate_entry_points(
            session,
            entry.id,
            outcome_counts_by_fixture=outcome_counts_by_fixture,
            actual_advancement=actual_advancement,
        )
        phase_points = _get_phase_points(breakdown, phase)

        picks = team_picks.get(entry.id, {"winner": [], "final": []})
        champion_pick = picks["winner"][0] if picks["winner"] else None
        finalist_picks = picks["final"]
        employer = (
            entry.user.employer.value
            if entry.user and entry.user.employer
            else None
        )

        entries.append(
            LeaderboardEntry(
                entry_id=entry.id,
                entry_reference=entry.reference,
                entry_name=entry.display_name,
                user_id=entry.user_id,
                # Magic-link sign-ups may still have name=None until they
                # complete /onboarding. Fall back to the email-prefix so
                # the leaderboard never renders a blank cell.
                user_name=(
                    (entry.user.name or entry.user.email.split("@")[0])
                    if entry.user
                    else "Unknown"
                ),
                position=0,  # Set after sorting
                total_points=phase_points,
                breakdown=breakdown,
                # The breakdown already counts these while scoring each
                # finished match — no separate per-entry stats query.
                correct_outcomes=breakdown.correct_outcomes,
                exact_scores=breakdown.exact_scores,
                movement=0,  # Calculated after positioning
                employer=employer,
                champion_pick=champion_pick,
                champion_alive=(
                    champion_pick is not None
                    and champion_pick not in eliminated_teams
                ),
                finalist_picks=finalist_picks,
                finalists_alive=sum(
                    1 for t in finalist_picks if t not in eliminated_teams
                ),
                daily_movement=None,  # Set after positioning
                bonus_group_points=bonus_splits.get(entry.id, (0, 0))[0],
                bonus_knockout_points=bonus_splits.get(entry.id, (0, 0))[1],
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

        snap_pos = yesterday_positions.get(entry.entry_id)
        if snap_pos is not None:
            entry.daily_movement = snap_pos - entry.position  # Positive = climbed

    total_participants = len(entries)

    # Update cache
    _cache[cache_key] = CachedLeaderboard(
        entries=entries,
        last_calculated=now,
        total_participants=total_participants,
        phase=phase,
        previous_positions={e.entry_id: e.position for e in entries},
    )

    from app.services.sheets_sync import get_published_sheet_url  # noqa: PLC0415

    return LeaderboardResponse(
        entries=entries,
        last_calculated=now,
        total_participants=total_participants,
        phase=phase,
        published_sheet_url=get_published_sheet_url(),
    )


def invalidate_cache() -> None:
    """Drop the leaderboard cache entirely.

    The next consumer BLOCKS on a full rebuild — read-your-write
    semantics. Right for tests and the admin force-refresh endpoint;
    for the score-sync loop prefer expire_cache(), which keeps serving
    the last-known board while the rebuild happens off-request.
    """
    global _cache
    _cache = {}


def expire_cache() -> None:
    """Mark every cached board stale WITHOUT dropping it.

    Used by the score-sync loop after a score lands: consumers keep
    getting instant responses from the last-known board while the
    stale-while-revalidate path rebuilds with the new score in the
    background. Worst-case staleness is one rebuild + one poll cycle.
    """
    for cached in _cache.values():
        cached.stale = True


def set_cache_ttl(seconds: int) -> None:
    """Set the cache TTL in seconds."""
    global _cache_ttl
    _cache_ttl = timedelta(seconds=seconds)
