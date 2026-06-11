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

# Cap on per-fixture resolution fetches in a single sync. Each costs one
# API call on top of the bulk live call; Free tier allows 10/min, so 8
# keeps a worst-case tick (1 bulk + 8 singles) inside the budget.
_MAX_RESOLVE_FETCHES = 8


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

    # Fixtures the live response actually touched this tick (by row id, NOT
    # external id — the ESPN provider matches by team name and carries no
    # Football-Data id, so id-string bookkeeping would mark everything
    # unresolved and let a laggier source overwrite fresh live scores).
    seen_fixture_ids: set = set()
    for ext in external_scores:
        try:
            touched = await _apply_external_score(session, competition.id, ext, result)
            if touched is not None:
                seen_fixture_ids.add(touched)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                f"Error applying {ext.home_team} vs {ext.away_team}: {exc}"
            )

    # Resolution pass. The live feed only covers pre/in-play matches (ESPN
    # drops finished ones by design; Football-Data's bulk call filters on
    # LIVE/IN_PLAY/PAUSED) — so the moment a match ends it vanishes from
    # the response, and without this pass its fixture would sit at LIVE
    # with the last in-play score forever (blocking scoring + pushes).
    # Any fixture we believe is in-play (or that kicked off recently but
    # never transitioned, e.g. after backend downtime) that the live
    # response did not touch gets fetched from Football-Data by external
    # id — landing the authoritative final with the FT/ET/pens split.
    unresolved = await _find_unresolved_fixtures(session, competition.id, seen_fixture_ids)
    for fixture in unresolved[:_MAX_RESOLVE_FETCHES]:
        try:
            ext = await provider.fetch_fixture_score(
                fixture.external_id,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                f"Resolve error for {fixture.home_team} vs {fixture.away_team}: {exc}"
            )
            continue
        if ext is None:
            continue
        try:
            await _apply_external_score(session, competition.id, ext, result)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                f"Error applying {ext.home_team} vs {ext.away_team}: {exc}"
            )

    if not external_scores and not unresolved:
        result.skipped_reason = "no live matches returned by provider"
        return result

    await session.commit()

    if result.synced > 0 or result.updated > 0:
        invalidate_cache()

    return result


async def _find_unresolved_fixtures(
    session: AsyncSession,
    competition_id,
    seen_fixture_ids: set,
    *,
    now: datetime | None = None,
) -> list[Fixture]:
    """Fixtures that should be in the live response but weren't.

    Two shapes: (a) status LIVE/HALFTIME — almost certainly just finished;
    (b) status SCHEDULED with a kickoff in the recent past — a transition
    we missed entirely (e.g. the backend was down through the match).
    """
    now = now or utc_now()
    q = await session.execute(
        select(Fixture).where(
            Fixture.competition_id == competition_id,
            Fixture.external_id.is_not(None),  # type: ignore[union-attr]
            (
                Fixture.status.in_([MatchStatus.LIVE, MatchStatus.HALFTIME])
                | (
                    (Fixture.status == MatchStatus.SCHEDULED)
                    & (Fixture.kickoff <= now)
                    & (Fixture.kickoff >= now - _LIVE_MATCH_WINDOW)
                )
            ),
        )
    )
    return [f for f in q.scalars().all() if f.id not in seen_fixture_ids]


# Statuses for which the provider's score payload is meaningful. For a
# match that hasn't started (or won't be played) Football-Data reports
# nulls, which _to_external_score coerces to 0 — writing that would
# fabricate a 0-0 result, so we only touch the Score row in these states.
_SCORE_BEARING_STATUSES = frozenset(
    {MatchStatus.LIVE, MatchStatus.HALFTIME, MatchStatus.FINISHED}
)


async def _apply_external_score(
    session: AsyncSession,
    competition_id,
    ext: ExternalScore,
    result: ScoreSyncResult,
):
    """Match an ExternalScore to a Fixture by external_id (or team-name fallback)
    and create/update the corresponding Score row.

    Returns the touched fixture's id (or None if no fixture matched) so the
    caller can exclude it from the resolution pass this tick."""
    fixture = await _find_fixture(session, competition_id, ext)
    if fixture is None:
        return None

    score_q = await session.execute(select(Score).where(Score.fixture_id == fixture.id))
    score = score_q.scalar_one_or_none()

    # Admin-verified scores are locked against the API: a manual
    # correction entered via the /admin/sync editor must survive the
    # 60-second scheduler re-applying a wrong upstream value. The fixture
    # status/minute are left alone too — the admin save already set
    # FINISHED. Un-verify the score to hand control back to the API.
    # This guard runs BEFORE any fixture mutation on purpose; it also
    # returns the fixture id so the resolution pass won't re-fetch it.
    if score is not None and score.verified:
        result.skipped_verified += 1
        return fixture.id

    # Demotion guard: a FINISHED fixture can only be touched by another
    # FINISHED payload (score corrections). Football-Data flapped
    # FINISHED → TIMED at the WC2026 opener; letting that through would
    # un-finish a played match and claw back paid leaderboard points.
    if fixture.status == MatchStatus.FINISHED and ext.status != MatchStatus.FINISHED:
        return fixture.id

    # Null-score guard: a score-bearing status whose payload carried no
    # actual score values (has_score=False — nulls coerced to 0) must not
    # be applied. Writing it would fabricate a 0-0 FINISHED result; doing
    # nothing leaves the fixture in-play so the resolution pass retries
    # next tick until a provider serves a real final.
    if ext.status in _SCORE_BEARING_STATUSES and not ext.has_score:
        return fixture.id

    fixture_unchanged = fixture.status == ext.status and fixture.minute == ext.minute

    # Non-score-bearing statuses (SCHEDULED / POSTPONED / CANCELLED): sync
    # the fixture status but never write a Score row — null scores coerce
    # to 0 and would fabricate a 0-0 result for an unplayed match.
    if ext.status not in _SCORE_BEARING_STATUSES:
        if not fixture_unchanged:
            fixture.status = ext.status
            fixture.minute = ext.minute
            fixture.updated_at = utc_now()
        return fixture.id

    # Change detection: ESPN repaints the same in-play score every tick and
    # the resolution pass can re-deliver a finished match. Identical data
    # must be a no-op — otherwise each tick rewrites rows, bumps
    # updated_at, and invalidates the leaderboard cache for nothing.
    unchanged = (
        fixture_unchanged
        and score is not None
        and score.home_score == ext.home_score
        and score.away_score == ext.away_score
        and score.home_score_et == ext.home_score_et
        and score.away_score_et == ext.away_score_et
        and score.home_penalties == ext.home_penalties
        and score.away_penalties == ext.away_penalties
    )
    if unchanged:
        return fixture.id

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
        return fixture.id

    score.home_score = ext.home_score
    score.away_score = ext.away_score
    score.home_score_et = ext.home_score_et
    score.away_score_et = ext.away_score_et
    score.home_penalties = ext.home_penalties
    score.away_penalties = ext.away_penalties
    score.source = ScoreSource.API
    score.updated_at = utc_now()
    result.updated += 1
    return fixture.id


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
