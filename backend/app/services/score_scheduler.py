"""Background scheduler that polls live scores during match windows.

Runs as an asyncio task started during FastAPI lifespan. Each tick:
  1. Cheap DB query to decide if any match is live or imminent.
  2. If yes, call sync_scores_once (one external API call).
  3. Sleep for POLL_INTERVAL_SECONDS.

Outside match windows the scheduler does no API work — saves quota and
keeps us comfortably under Football-Data Free tier's 10 calls/min limit.
A typical match-day burns ~30-90 calls (one per minute over 1.5h);
budget is 14,400/day so we're well below the ceiling.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.services.entries import flip_drafts_past_deadline
from app.services.locking import get_active_competition
from app.services.score_sync import has_active_or_imminent_match, sync_scores_once
from app.services.sheets_sync import is_configured as sheets_sync_configured
from app.services.sheets_sync import sync_to_sheets
from app.services.snapshots import take_daily_snapshots


logger = logging.getLogger(__name__)


# Tunable: 60 s lines up with the frontend's leaderboard poll cadence,
# so users see fresh scores within one frontend refresh.
POLL_INTERVAL_SECONDS = 60.0


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    settings = get_settings()
    db_url = str(settings.database_url).replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(db_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _run_one_tick(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """One iteration of the loop. Wraps each tick in its own session so a
    failure on one tick can't poison subsequent ticks.

    Each tick does two things:
      (a) Take today's leaderboard snapshot if not already taken (idempotent
          per-user-per-day, cheap no-op after the first call of the day).
      (b) If a match is live or imminent, sync scores from Football-Data.

    Snapshot taking is gated by its own try/except so a snapshot failure
    can't break the live-score path.
    """
    async with session_factory() as session:
        try:
            await take_daily_snapshots(session)
        except Exception:  # noqa: BLE001
            logger.exception("score_scheduler: snapshot tick failed")

        # Auto-withdraw any DRAFT entries past competition.phase1_deadline.
        # Idempotent — re-runs are no-ops once all drafts have flipped.
        try:
            flipped = await flip_drafts_past_deadline(session)
            if flipped:
                await session.commit()
                logger.info(
                    "score_scheduler tick: auto-withdrew %d draft entries past deadline",
                    flipped,
                )
        except Exception:  # noqa: BLE001
            await session.rollback()
            logger.exception("score_scheduler: auto-withdraw tick failed")

        if not await has_active_or_imminent_match(session):
            return
        result = await sync_scores_once(session)
        if result.errors:
            for err in result.errors:
                logger.warning("score_scheduler: %s", err)
        if result.synced or result.updated:
            logger.info(
                "score_scheduler tick: synced=%d updated=%d",
                result.synced,
                result.updated,
            )
            # A score moved → refresh the published Google Sheet so the
            # online standings track within one tick. include_predictions
            # backfills the (frozen) picks tab on the first push of the
            # process. No-op when sheets sync isn't configured.
            await _sync_sheets(session)


async def _sync_sheets(session: AsyncSession) -> None:
    """Best-effort Google Sheets push, gated on configuration.

    Wrapped here (not inline) so a sheets failure or a missing active
    competition can never disturb the score-sync path. sync_to_sheets is
    itself non-raising; this guard is belt-and-braces for the lookup.
    """
    if not sheets_sync_configured():
        return
    try:
        competition = await get_active_competition(session)
        if competition is None:
            return
        await sync_to_sheets(session, competition, include_predictions=True)
    except Exception:  # noqa: BLE001
        logger.exception("score_scheduler: sheets sync tick failed")


async def run_scheduler_loop(
    *,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Long-running task: poll forever (until cancelled or stop_event set)."""
    session_factory = _make_session_factory()
    stop_event = stop_event or asyncio.Event()

    logger.info("score_scheduler started (interval=%.1fs)", interval_seconds)

    # Populate the published Google Sheet once at startup so it's current
    # even outside a match window (the per-tick refresh only fires when a
    # score moves). Best-effort, never blocks the loop from starting.
    if sheets_sync_configured():
        async with session_factory() as session:
            try:
                await _sync_sheets(session)
            except Exception:  # noqa: BLE001
                logger.exception("score_scheduler: initial sheets sync failed")

    try:
        while not stop_event.is_set():
            try:
                await _run_one_tick(session_factory)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                # Log but never let one bad tick kill the loop.
                logger.exception("score_scheduler: tick failed")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                # If wait returned, stop_event was set — exit loop.
                return
            except asyncio.TimeoutError:
                # Timed out waiting → another tick is due.
                continue
    except asyncio.CancelledError:
        logger.info("score_scheduler cancelled")
        raise
    finally:
        logger.info("score_scheduler stopped")


@asynccontextmanager
async def scheduler_lifespan():
    """Async context manager that starts the scheduler on enter and
    stops it cleanly on exit. Used by FastAPI's lifespan handler.
    """
    stop_event = asyncio.Event()
    task = asyncio.create_task(run_scheduler_loop(stop_event=stop_event))
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
