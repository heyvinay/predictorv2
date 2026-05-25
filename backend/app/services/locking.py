"""Prediction locking service."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase

# Lock predictions 5 minutes before kickoff
LOCK_MINUTES = 5


async def get_active_competition(session: AsyncSession) -> Competition | None:
    """Get the currently active competition.

    Returns:
        The active competition, or None if no active competition exists.
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)
    )
    return result.scalar_one_or_none()


def check_fixture_locked(fixture: Fixture, lock_minutes: int = LOCK_MINUTES) -> bool:
    """Check if a fixture is locked for predictions.

    Args:
        fixture: The fixture to check
        lock_minutes: Minutes before kickoff to lock (default 5)

    Returns:
        True if predictions are locked, False otherwise
    """
    # aware_utc() guards against aiosqlite dropping tzinfo on read (the
    # SQLite quirk noted in CLAUDE.md). Postgres preserves tzinfo so this
    # is a defensive no-op in production.
    kickoff = aware_utc(fixture.kickoff)
    lock_time = kickoff - timedelta(minutes=lock_minutes)
    return aware_utc(utc_now()) >= lock_time


def get_time_until_lock(fixture: Fixture, lock_minutes: int = LOCK_MINUTES) -> timedelta | None:
    """Get time remaining until predictions lock.

    Args:
        fixture: The fixture to check
        lock_minutes: Minutes before kickoff to lock

    Returns:
        Time remaining as timedelta, or None if already locked
    """
    kickoff = aware_utc(fixture.kickoff)
    lock_time = kickoff - timedelta(minutes=lock_minutes)
    remaining = lock_time - aware_utc(utc_now())
    return remaining if remaining.total_seconds() > 0 else None


async def get_current_phase(session: AsyncSession) -> PredictionPhase:
    """Determine the current prediction phase based on competition state.

    Phase 2 is active when an admin has explicitly activated it via
    the is_phase2_active flag on the competition.

    Args:
        session: Database session

    Returns:
        PHASE_2 if Phase 2 is active, otherwise PHASE_1
    """
    competition = await get_active_competition(session)
    if competition and competition.is_phase2_active:
        return PredictionPhase.PHASE_2
    return PredictionPhase.PHASE_1


async def is_phase1_locked(session: AsyncSession) -> bool:
    """Whether Phase 1 predictions (group matches, bracket, bonus questions)
    are locked for the active competition.

    Returns True iff the active competition has a `phase1_deadline` and the
    current time is at or past it. Returns False when no competition is
    active or no deadline has been set.
    """
    competition = await get_active_competition(session)
    if not competition or not competition.phase1_deadline:
        return False
    return aware_utc(utc_now()) >= aware_utc(competition.phase1_deadline)


async def is_phase2_bracket_locked(session: AsyncSession) -> bool:
    """Check if the Phase 2 bracket prediction deadline has passed.

    The Phase 2 bracket locks at the phase2_bracket_deadline, which is
    set by the admin when activating Phase 2.

    Args:
        session: Database session

    Returns:
        True if Phase 2 bracket is locked, False otherwise
    """
    competition = await get_active_competition(session)
    if not competition:
        return False
    if not competition.is_phase2_active:
        return False
    if not competition.phase2_bracket_deadline:
        return False
    return aware_utc(utc_now()) >= aware_utc(competition.phase2_bracket_deadline)


async def lock_predictions(session: AsyncSession, fixture_id: str) -> int:
    """Lock all predictions for a fixture.

    This is called when a match is about to start (5 min before kickoff)
    to permanently lock all predictions.

    Args:
        session: Database session
        fixture_id: The fixture ID to lock predictions for

    Returns:
        Number of predictions locked
    """
    result = await session.execute(
        select(MatchPrediction).where(
            MatchPrediction.fixture_id == fixture_id,
            MatchPrediction.locked_at.is_(None),
        )
    )
    predictions = result.scalars().all()

    locked_count = 0
    now = utc_now()

    for prediction in predictions:
        prediction.locked_at = now
        locked_count += 1

    await session.commit()
    return locked_count


async def check_and_lock_upcoming_fixtures(session: AsyncSession) -> dict[str, int]:
    """Check all fixtures and lock predictions for those about to start.

    This should be called periodically (e.g., every minute via cron/scheduler).

    Returns:
        Dict mapping fixture_id to number of locked predictions
    """
    # Get fixtures within lock window that haven't started
    lock_threshold = utc_now() + timedelta(minutes=LOCK_MINUTES)

    result = await session.execute(
        select(Fixture).where(
            Fixture.kickoff <= lock_threshold,
            Fixture.status == "scheduled",
        )
    )
    fixtures = result.scalars().all()

    results = {}
    for fixture in fixtures:
        locked = await lock_predictions(session, str(fixture.id))
        if locked > 0:
            results[str(fixture.id)] = locked

    return results
