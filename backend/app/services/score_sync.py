"""Score-sync service: pull live scores from external API and write to DB.

Extracted from the admin endpoint so the same code path can be invoked by:
- The admin sync endpoint (manual trigger)
- The background scheduler (automatic polling during match windows)

Returns counts + errors as a dataclass (no FastAPI types here).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource
from app.services.external_scores import ExternalScore, get_score_provider
from app.services.leaderboard import expire_cache, invalidate_cache
from app.services.win_probability import (
    expire_win_probability_cache,
    invalidate_win_probability_cache,
)

logger = logging.getLogger(__name__)


@dataclass
class ScoreSyncResult:
    synced: int = 0       # newly created Score rows
    updated: int = 0      # existing Score rows updated
    # Score writes at FINISHED status — a finish transition or a correction
    # to an already-finished match. Only these can move leaderboard points
    # (the scoring engine ignores in-play scores), so only these expire the
    # leaderboard cache. Live 1-0 → 2-0 paints update Score rows but leave
    # the board untouched.
    points_relevant: int = 0
    # Subset of points_relevant that were KNOCKOUT-stage finishes. These
    # hard-invalidate the leaderboard cache (vs the soft-expire used for
    # group finishes) so the live-projection handoff at full time is
    # seamless — see docs/superpowers/plans/2026-07-06-live-projected-leaderboard.md.
    points_relevant_ko: int = 0
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

    if result.points_relevant_ko > 0:
        # A knockout match just finished: hard-invalidate so the banked
        # board reflects the real advancement credit on the very next
        # read, keeping the live-projection handoff seamless (no dip at
        # full time). Blocks one request on a rebuild — rare + acceptable.
        invalidate_cache()
        # A KO finish changes both m (one fewer unresolved match) and
        # every entry's banked base — the win-probability cache is stale
        # in exactly the same way the leaderboard's is.
        invalidate_win_probability_cache()
    elif result.points_relevant > 0:
        # Group-stage finish or a correction: soft-expire (stale-while-
        # revalidate) as before — no live projection is involved.
        expire_cache()
        expire_win_probability_cache()

    return result


async def _find_unresolved_fixtures(
    session: AsyncSession,
    competition_id,
    seen_fixture_ids: set,
    *,
    now: datetime | None = None,
) -> list[Fixture]:
    """Fixtures that need per-fixture resolution fetches.

    Three shapes:
    (A) status LIVE/HALFTIME — almost certainly just finished.
    (B) status SCHEDULED with a kickoff in the recent past — a transition
        we missed entirely (e.g. the backend was down through the match).
    (C) status FINISHED, KO stage, null home_penalties, kicked off within
        12h — a fixture whose pens data was stale when it finished (e.g.
        NED-MAR: null pens written at FINISHED time, FD has since corrected).
        Sorted last so A+B take priority in the 8-slot cap.
    """
    now = now or utc_now()

    # Shapes A + B
    ab_q = await session.execute(
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
    ab = [f for f in ab_q.scalars().all() if f.id not in seen_fixture_ids]

    # Shape C: FINISHED KO fixtures with null pens, kicked off within 12h
    c_q = await session.execute(
        select(Fixture)
        .join(Score, Score.fixture_id == Fixture.id)
        .where(
            Fixture.competition_id == competition_id,
            Fixture.external_id.is_not(None),  # type: ignore[union-attr]
            Fixture.status == MatchStatus.FINISHED,
            Fixture.stage != "group",
            Fixture.kickoff >= now - timedelta(hours=12),
            Score.home_penalties.is_(None),
            Score.verified.is_(False),
        )
    )
    c = [f for f in c_q.scalars().all() if f.id not in seen_fixture_ids]

    return ab + c  # A+B first (higher priority within the 8-slot cap)


# Statuses for which the provider's score payload is meaningful. For a
# match that hasn't started (or won't be played) Football-Data reports
# nulls, which _to_external_score coerces to 0 — writing that would
# fabricate a 0-0 result, so we only touch the Score row in these states.
_SCORE_BEARING_STATUSES = frozenset(
    {MatchStatus.LIVE, MatchStatus.HALFTIME, MatchStatus.FINISHED}
)


def _score_fields_for(
    fixture: Fixture,
    ext: ExternalScore,
    existing: Score | None,
) -> tuple[int | None, int | None, int | None, int | None, int | None, int | None]:
    """Compute (home, away, home_et, away_et, home_pen, away_pen) to persist.

    Applies the 90-minute freeze for knockout matches past regulation when
    ESPN is the source. ESPN folds ET goals into the running home_score/
    away_score total (period > 2), so we must NOT overwrite the stored 90'
    score once ET starts — the freeze keeps the regulation values in
    home_score/away_score and puts the running total into home_score_et.

    This freeze only activates when ALL of these are true:
      - fixture.stage != "group" (knockout match)
      - ext.period > 2 (ESPN says match is past regulation)
      - ext.home_score_et is None (provider has NOT already split it out)

    If the provider already supplies a split (FD or ESPN summary enrichment),
    pass through directly without freezing.
    """
    provider_split = ext.home_score_et is not None and ext.away_score_et is not None
    past_regulation = (
        fixture.stage not in ("group", "third_place")
        and not provider_split
        and ext.period is not None
        and ext.period > 2
    )

    if not past_regulation:
        return (
            ext.home_score,
            ext.away_score,
            ext.home_score_et,
            ext.away_score_et,
            ext.home_penalties,
            ext.away_penalties,
        )

    # Past regulation with bare running total. Freeze at whatever was
    # captured before ET started; the running total becomes home_score_et.
    if existing is not None:
        reg_home: int | None = existing.home_score
        reg_away: int | None = existing.away_score
    else:
        # Polling gap — never saw this match during regulation.
        reg_home = ext.home_score
        reg_away = ext.away_score
        logger.warning(
            "score_sync: knockout fixture %s first seen past regulation "
            "(period=%s) — no captured 90' score; using running total %s-%s, "
            "admin should verify",
            fixture.id,
            ext.period,
            ext.home_score,
            ext.away_score,
        )

    # Running total IS the cumulative after-ET score for a bare provider.
    home_et = ext.home_score
    away_et = ext.away_score

    # Self-heal: frozen reg score must never exceed the ET total (goals
    # only accumulate). A reg score higher than ET means a corrupted live
    # capture — clamp it back.
    if home_et is not None and reg_home is not None and reg_home > home_et:
        logger.warning(
            "score_sync: fixture %s frozen 90' home %s > ET total %s "
            "— healing to ET total",
            fixture.id, reg_home, home_et,
        )
        reg_home = home_et
    if away_et is not None and reg_away is not None and reg_away > away_et:
        logger.warning(
            "score_sync: fixture %s frozen 90' away %s > ET total %s "
            "— healing to ET total",
            fixture.id, reg_away, away_et,
        )
        reg_away = away_et

    return (reg_home, reg_away, home_et, away_et, ext.home_penalties, ext.away_penalties)


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

    # If this score came from Football-Data (non-empty external_id) and the
    # fixture still holds slot-placeholder team names, write the real names
    # back so ESPN's team-name fallback can match from the next tick onward.
    if ext.external_id:
        if fixture.home_team and fixture.home_team.startswith("slot:") and ext.home_team:
            fixture.home_team = ext.home_team
        if fixture.away_team and fixture.away_team.startswith("slot:") and ext.away_team:
            fixture.away_team = ext.away_team

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

    # Non-authoritative ESPN final on a KO fixture within the live window:
    # treat as LIVE so the FD resolution pass can land the authoritative split
    # (FT/ET/pens). Beyond the live window, accept as final to prevent the
    # fixture staying LIVE forever if FD never resolves it.
    needs_resolution = False
    if (
        ext.status == MatchStatus.FINISHED
        and not ext.final_authoritative
        and fixture.stage not in ("group", "third_place")
        and utc_now() < aware_utc(fixture.kickoff) + _LIVE_MATCH_WINDOW
    ):
        ext.status = MatchStatus.LIVE
        needs_resolution = True

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

    # Compute the fields to write (applies 90-min freeze when relevant).
    home, away, home_et, away_et, home_pen, away_pen = _score_fields_for(
        fixture, ext, score
    )

    # Change detection: identical data must be a no-op — otherwise each
    # tick rewrites rows, bumps updated_at, and invalidates the leaderboard
    # cache for nothing.
    unchanged = (
        fixture_unchanged
        and score is not None
        and score.home_score == home
        and score.away_score == away
        and score.home_score_et == home_et
        and score.away_score_et == away_et
        and score.home_penalties == home_pen
        and score.away_penalties == away_pen
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
                home_score=home,
                away_score=away,
                home_score_et=home_et,
                away_score_et=away_et,
                home_penalties=home_pen,
                away_penalties=away_pen,
                source=ScoreSource.API,
            )
        )
        result.synced += 1
        if ext.status == MatchStatus.FINISHED:
            result.points_relevant += 1
            if fixture.stage in ("round_of_32", "round_of_16", "quarter_final", "semi_final", "final"):
                result.points_relevant_ko += 1
        return None if needs_resolution else fixture.id

    score.home_score = home
    score.away_score = away
    score.home_score_et = home_et
    score.away_score_et = away_et
    score.home_penalties = home_pen
    score.away_penalties = away_pen
    score.source = ScoreSource.API
    score.updated_at = utc_now()
    result.updated += 1
    if ext.status == MatchStatus.FINISHED:
        result.points_relevant += 1
        if fixture.stage in ("round_of_32", "round_of_16", "quarter_final", "semi_final", "final"):
            result.points_relevant_ko += 1
    return None if needs_resolution else fixture.id


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
