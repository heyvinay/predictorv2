"""Score-sync service: pull live scores from external API and write to DB.

Extracted from the admin endpoint so the same code path can be invoked by:
- The admin sync endpoint (manual trigger)
- The background scheduler (automatic polling during match windows)

Returns counts + errors as a dataclass (no FastAPI types here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource
from app.services.external_scores import ExternalScore, get_score_provider
from app.services.leaderboard import invalidate_cache


@dataclass
class ScoreSyncResult:
    synced: int = 0       # newly created Score rows
    updated: int = 0      # existing Score rows updated
    skipped_verified: int = 0  # rows left alone because an admin verified them
    errors: list[str] = field(default_factory=list)
    skipped_reason: str | None = None  # set if sync was a no-op (e.g. no live matches)


# Window during which we consider a match worth polling for.
# Pre-kickoff buffer catches kick-off transitions; post-finish buffer
# catches final whistle and any AET / penalty resolution.
_PRE_KICKOFF_BUFFER = timedelta(minutes=10)
_POST_FINISH_BUFFER = timedelta(minutes=10)
_LIVE_MATCH_WINDOW = timedelta(hours=4)  # generous upper bound (group + ET + pens)


async def has_active_or_imminent_match(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> bool:
    """Return True if there's any reason to poll the API right now.

    Cheap DB query; no external calls. The scheduler uses this to decide
    whether to skip a tick (saves API quota during off-windows).
    """
    now = now or utc_now()

    # 1. Anything currently live? Always poll.
    live_q = await session.execute(
        select(Fixture.id)
        .where(Fixture.status.in_([MatchStatus.LIVE, MatchStatus.HALFTIME]))
        .limit(1)
    )
    if live_q.scalar_one_or_none() is not None:
        return True

    # 2. Anything scheduled to kick off within the pre-kickoff buffer? Poll.
    upcoming_q = await session.execute(
        select(Fixture.id)
        .where(
            Fixture.status == MatchStatus.SCHEDULED,
            Fixture.kickoff <= now + _PRE_KICKOFF_BUFFER,
            Fixture.kickoff >= now - _LIVE_MATCH_WINDOW,
        )
        .limit(1)
    )
    if upcoming_q.scalar_one_or_none() is not None:
        return True

    # 3. Anything scheduled but in the live-match window (in case status didn't
    # update from SCHEDULED → LIVE due to a polling miss)? Poll.
    return False


async def sync_scores_once(session: AsyncSession) -> ScoreSyncResult:
    """Fetch live scores from the configured provider and update DB.

    Returns counts + any errors encountered. Idempotent: re-running on
    unchanged data results in zero new rows.
    """
    result = ScoreSyncResult()

    comp_q = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = comp_q.scalar_one_or_none()

    if not competition or not competition.external_id:
        result.errors.append("No active competition with external_id configured")
        return result

    provider = get_score_provider()

    try:
        external_scores = await provider.fetch_live_scores(competition.external_id)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Provider error: {exc}")
        return result

    if not external_scores:
        result.skipped_reason = "no live matches returned by provider"
        return result

    for ext in external_scores:
        try:
            await _apply_external_score(session, competition.id, ext, result)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                f"Error applying {ext.home_team} vs {ext.away_team}: {exc}"
            )

    await session.commit()

    if result.synced > 0 or result.updated > 0:
        invalidate_cache()

    return result


async def _apply_external_score(
    session: AsyncSession,
    competition_id,
    ext: ExternalScore,
    result: ScoreSyncResult,
) -> None:
    """Match an ExternalScore to a Fixture by external_id (or team-name fallback)
    and create/update the corresponding Score row."""
    fixture = await _find_fixture(session, competition_id, ext)
    if fixture is None:
        return

    score_q = await session.execute(select(Score).where(Score.fixture_id == fixture.id))
    score = score_q.scalar_one_or_none()

    # Admin-verified scores are locked against the API: a manual
    # correction entered via the /admin/sync editor must survive the
    # 60-second scheduler re-applying a wrong upstream value. The fixture
    # status/minute are left alone too — the admin save already set
    # FINISHED. Un-verify the score to hand control back to the API.
    if score is not None and score.verified:
        result.skipped_verified += 1
        return

    # Change detection: the live filter includes FINISHED, so every poll
    # during a match window re-delivers already-finished matches. Identical
    # data must be a no-op — otherwise each tick rewrites rows, bumps
    # updated_at, and invalidates the leaderboard cache for nothing.
    unchanged = (
        score is not None
        and fixture.status == ext.status
        and fixture.minute == ext.minute
        and score.home_score == ext.home_score
        and score.away_score == ext.away_score
        and score.home_score_et == ext.home_score_et
        and score.away_score_et == ext.away_score_et
        and score.home_penalties == ext.home_penalties
        and score.away_penalties == ext.away_penalties
    )
    if unchanged:
        return

    fixture.status = ext.status
    fixture.minute = ext.minute
    fixture.updated_at = utc_now()

    if score is None:
        session.add(
            Score(
                fixture_id=fixture.id,
                home_score=ext.home_score,
                away_score=ext.away_score,
                home_score_et=ext.home_score_et,
                away_score_et=ext.away_score_et,
                home_penalties=ext.home_penalties,
                away_penalties=ext.away_penalties,
                source=ScoreSource.API,
            )
        )
        result.synced += 1
        return

    score.home_score = ext.home_score
    score.away_score = ext.away_score
    score.home_score_et = ext.home_score_et
    score.away_score_et = ext.away_score_et
    score.home_penalties = ext.home_penalties
    score.away_penalties = ext.away_penalties
    score.source = ScoreSource.API
    score.updated_at = utc_now()
    result.updated += 1


async def _find_fixture(
    session: AsyncSession, competition_id, ext: ExternalScore
) -> Fixture | None:
    """Match by external_id first; fall back to (home_team, away_team) within competition."""
    if ext.external_id:
        q = await session.execute(
            select(Fixture).where(Fixture.external_id == ext.external_id)
        )
        f = q.scalar_one_or_none()
        if f is not None:
            return f

    if ext.home_team and ext.away_team:
        q = await session.execute(
            select(Fixture).where(
                Fixture.home_team == ext.home_team,
                Fixture.away_team == ext.away_team,
                Fixture.competition_id == competition_id,
            )
        )
        return q.scalar_one_or_none()

    return None
