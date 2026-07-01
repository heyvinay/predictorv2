"""Tests for score_sync: windowing logic and the external-score apply path."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource
from app.services.external_scores import ExternalScore
from app.services.score_sync import (
    ScoreSyncResult,
    _apply_external_score,
    _find_unresolved_fixtures,
    _score_fields_for,
    has_active_or_imminent_match,
    sync_scores_once,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), external_id="WC")
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


def _fixture(competition_id, *, kickoff: datetime, status: MatchStatus, ext: str) -> Fixture:
    return Fixture(
        competition_id=competition_id,
        external_id=ext,
        home_team="Mexico",
        away_team="South Africa",
        kickoff=kickoff,
        stage="group",
        group="A",
        status=status,
    )


NOW = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_returns_false_when_db_empty(session, competition) -> None:
    assert await has_active_or_imminent_match(session, now=NOW) is False


@pytest.mark.asyncio
async def test_returns_true_when_match_is_live(session, competition) -> None:
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(hours=1), status=MatchStatus.LIVE, ext="1"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_true_when_match_is_at_halftime(session, competition) -> None:
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(minutes=45), status=MatchStatus.HALFTIME, ext="2"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_true_for_imminent_kickoff_within_buffer(session, competition) -> None:
    # Kickoff in 9 minutes — within the 10-minute pre-kickoff buffer
    session.add(_fixture(competition.id, kickoff=NOW + timedelta(minutes=9), status=MatchStatus.SCHEDULED, ext="3"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_false_when_kickoff_is_far_away(session, competition) -> None:
    # Kickoff in 2 hours — outside the buffer
    session.add(_fixture(competition.id, kickoff=NOW + timedelta(hours=2), status=MatchStatus.SCHEDULED, ext="4"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is False


@pytest.mark.asyncio
async def test_returns_true_for_potentially_overrunning_match(session, competition) -> None:
    # Status still SCHEDULED but kickoff was 2 hours ago — could be a match
    # whose status didn't update from a missed poll. Buffer says yes-poll.
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(hours=2), status=MatchStatus.SCHEDULED, ext="5"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is True


@pytest.mark.asyncio
async def test_returns_false_when_match_finished_long_ago(session, competition) -> None:
    session.add(_fixture(competition.id, kickoff=NOW - timedelta(days=1), status=MatchStatus.FINISHED, ext="6"))
    await session.commit()
    assert await has_active_or_imminent_match(session, now=NOW) is False


# ---------------------------------------------------------------------------
# _apply_external_score: status transitions + idempotence
# ---------------------------------------------------------------------------


def _ext(
    status: MatchStatus,
    *,
    ext_id: str = "100",
    home: int = 1,
    away: int = 0,
    minute: int | None = None,
) -> ExternalScore:
    return ExternalScore(
        external_id=ext_id,
        home_team="Mexico",
        away_team="South Africa",
        home_score=home,
        away_score=away,
        status=status,
        minute=minute,
    )


@pytest_asyncio.fixture
async def live_fixture(session: AsyncSession, competition: Competition) -> Fixture:
    f = _fixture(competition.id, kickoff=NOW - timedelta(hours=1), status=MatchStatus.LIVE, ext="100")
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


@pytest.mark.asyncio
async def test_apply_creates_score_and_flips_status_to_live(session, competition) -> None:
    f = _fixture(competition.id, kickoff=NOW, status=MatchStatus.SCHEDULED, ext="100")
    session.add(f)
    await session.commit()

    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.LIVE, minute=12), result)
    await session.commit()

    assert result.synced == 1
    assert f.status == MatchStatus.LIVE
    assert f.minute == 12
    score = (await session.execute(select(Score).where(Score.fixture_id == f.id))).scalar_one()
    assert (score.home_score, score.away_score) == (1, 0)


@pytest.mark.asyncio
async def test_apply_finished_transition_lands(session, competition, live_fixture) -> None:
    """LIVE → FINISHED with the same scoreline must still be applied — the
    status change alone is what releases scoring for the match."""
    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.LIVE, minute=88), result)
    await session.commit()

    result2 = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.FINISHED), result2)
    await session.commit()

    assert result2.updated == 1
    assert live_fixture.status == MatchStatus.FINISHED


@pytest.mark.asyncio
async def test_apply_identical_data_is_a_noop(session, competition, live_fixture) -> None:
    """Re-delivered FINISHED matches (the filter includes them every poll)
    must not count as updates or rewrite rows."""
    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.FINISHED), result)
    await session.commit()
    assert result.synced + result.updated == 1

    result2 = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.FINISHED), result2)
    await session.commit()

    assert result2.synced == 0
    assert result2.updated == 0


@pytest.mark.asyncio
async def test_apply_skips_verified_score(session, competition, live_fixture) -> None:
    session.add(Score(fixture_id=live_fixture.id, home_score=2, away_score=2, verified=True))
    live_fixture.status = MatchStatus.FINISHED
    await session.commit()

    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.LIVE, home=0, away=0), result)
    await session.commit()

    assert result.skipped_verified == 1
    score = (await session.execute(select(Score).where(Score.fixture_id == live_fixture.id))).scalar_one()
    assert (score.home_score, score.away_score) == (2, 2)
    assert live_fixture.status == MatchStatus.FINISHED


@pytest.mark.asyncio
async def test_apply_verified_lock_survives_non_score_bearing_status(
    session, competition, live_fixture
) -> None:
    """The admin lock beats every inbound status — including non-score-bearing
    ones like POSTPONED, which take the early fixture-status path."""
    session.add(Score(fixture_id=live_fixture.id, home_score=2, away_score=2, verified=True))
    live_fixture.status = MatchStatus.FINISHED
    await session.commit()

    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.POSTPONED), result)
    await session.commit()

    assert result.skipped_verified == 1
    assert live_fixture.status == MatchStatus.FINISHED


# ---------------------------------------------------------------------------
# sync_scores_once: live apply + the per-fixture resolution pass
# ---------------------------------------------------------------------------


class FakeProvider:
    """Score provider double: a canned live response + per-id lookups."""

    def __init__(self, live: list[ExternalScore], by_id: dict[str, ExternalScore] | None = None):
        self.live = live
        self.by_id = by_id or {}
        self.fixture_fetches: list[str] = []

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        return self.live

    async def fetch_fixture_score(
        self,
        fixture_id: str,
        *,
        home_team: str | None = None,
        away_team: str | None = None,
    ) -> ExternalScore | None:
        self.fixture_fetches.append(str(fixture_id))
        return self.by_id.get(str(fixture_id))


async def _get_score(session: AsyncSession, fixture_id) -> Score | None:
    q = await session.execute(select(Score).where(Score.fixture_id == fixture_id))
    return q.scalar_one_or_none()


@pytest.mark.asyncio
async def test_live_fixture_absent_from_response_is_resolved_to_finished(
    session, competition, monkeypatch
) -> None:
    # DB says LIVE, but the live-filtered response no longer contains the
    # match — Football-Data marked it FINISHED. The resolution pass must
    # fetch it individually and land the final score + status.
    fx = _fixture(competition.id, kickoff=NOW - timedelta(hours=2), status=MatchStatus.LIVE, ext="100")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    provider = FakeProvider(live=[], by_id={"100": _ext(MatchStatus.FINISHED, home=2, away=1)})
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    result = await sync_scores_once(session)

    assert provider.fixture_fetches == ["100"]
    assert result.synced == 1 and not result.errors
    await session.refresh(fx)
    assert fx.status == MatchStatus.FINISHED
    score = await _get_score(session, fx.id)
    assert score is not None and (score.home_score, score.away_score) == (2, 1)


@pytest.mark.asyncio
async def test_scheduled_fixture_past_kickoff_is_resolved(
    session, competition, monkeypatch
) -> None:
    # Backend was down through the whole match: status never left SCHEDULED.
    # The resolution pass picks it up from the recent-kickoff window. Unlike
    # the LIVE-status cases, this window is evaluated against the real clock
    # inside sync_scores_once, so the kickoff must be relative to utc_now().
    fx = _fixture(competition.id, kickoff=utc_now() - timedelta(hours=3), status=MatchStatus.SCHEDULED, ext="101")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    provider = FakeProvider(live=[], by_id={"101": _ext(MatchStatus.FINISHED, ext_id="101", home=0, away=3)})
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    await sync_scores_once(session)

    await session.refresh(fx)
    assert fx.status == MatchStatus.FINISHED
    score = await _get_score(session, fx.id)
    assert score is not None and (score.home_score, score.away_score) == (0, 3)


@pytest.mark.asyncio
async def test_resolution_does_not_fabricate_score_for_unstarted_match(
    session, competition, monkeypatch
) -> None:
    # Delayed kickoff: our DB thinks the match should have started, but the
    # API still reports TIMED (→ SCHEDULED). Status syncs back, yet no 0-0
    # Score row may be written for a match that hasn't been played.
    fx = _fixture(competition.id, kickoff=NOW - timedelta(minutes=30), status=MatchStatus.LIVE, ext="102")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    provider = FakeProvider(live=[], by_id={"102": _ext(MatchStatus.SCHEDULED, ext_id="102", home=0, away=0)})
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    result = await sync_scores_once(session)

    assert result.synced == 0 and result.updated == 0
    await session.refresh(fx)
    assert fx.status == MatchStatus.SCHEDULED
    assert await _get_score(session, fx.id) is None


@pytest.mark.asyncio
async def test_espn_style_score_without_external_id_matches_by_name(
    session, competition, monkeypatch
) -> None:
    # The ESPN provider carries no Football-Data external_id — the fixture
    # must match via team names, and once touched it must NOT be re-fetched
    # by the resolution pass (which would let a laggier source overwrite
    # the fresh live score on the same tick).
    fx = _fixture(competition.id, kickoff=NOW - timedelta(minutes=30), status=MatchStatus.LIVE, ext="104")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    live = _ext(MatchStatus.LIVE, ext_id="", home=2, away=1, minute=67)
    provider = FakeProvider(live=[live])
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    result = await sync_scores_once(session)

    assert provider.fixture_fetches == []  # touched by name-match → no resolve call
    assert result.synced == 1
    await session.refresh(fx)
    assert fx.status == MatchStatus.LIVE and fx.minute == 67
    score = await _get_score(session, fx.id)
    assert score is not None and (score.home_score, score.away_score) == (2, 1)


@pytest.mark.asyncio
async def test_fixture_present_in_live_response_is_not_fetched_individually(
    session, competition, monkeypatch
) -> None:
    # Normal in-play tick: bulk response covers the match, so the resolution
    # pass must not spend an extra API call on it.
    fx = _fixture(competition.id, kickoff=NOW - timedelta(minutes=30), status=MatchStatus.LIVE, ext="103")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    provider = FakeProvider(live=[_ext(MatchStatus.LIVE, ext_id="103", home=1, away=0)])
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    result = await sync_scores_once(session)

    assert provider.fixture_fetches == []
    assert result.synced == 1
    await session.refresh(fx)
    assert fx.status == MatchStatus.LIVE
    score = await _get_score(session, fx.id)
    assert score is not None and (score.home_score, score.away_score) == (1, 0)


@pytest.mark.asyncio
async def test_finished_with_null_scores_is_not_applied(
    session, competition, monkeypatch
) -> None:
    # Regression for the WC2026 opener: Football-Data transiently served
    # status FINISHED with null fullTime (has_score=False, 0-coerced).
    # Writing it fabricated a 0-0 result. The null-score guard must leave
    # the fixture in-play so resolution retries next tick.
    fx = _fixture(competition.id, kickoff=NOW - timedelta(hours=2), status=MatchStatus.LIVE, ext="106")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)

    garbage = ExternalScore(
        external_id="106",
        home_team="Mexico",
        away_team="South Africa",
        home_score=0,
        away_score=0,
        status=MatchStatus.FINISHED,
        has_score=False,
    )
    provider = FakeProvider(live=[], by_id={"106": garbage})
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    result = await sync_scores_once(session)

    assert result.synced == 0 and result.updated == 0
    await session.refresh(fx)
    assert fx.status == MatchStatus.LIVE  # untouched — retry next tick
    assert await _get_score(session, fx.id) is None


@pytest.mark.asyncio
async def test_finished_fixture_is_not_demoted_by_stale_status(
    session, competition, live_fixture
) -> None:
    # Regression for the WC2026 opener: FD flapped FINISHED → TIMED after
    # the final whistle. A non-FINISHED payload must never un-finish a
    # played match (that would claw back paid leaderboard points).
    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.FINISHED, home=2, away=0), result)
    await session.commit()
    assert live_fixture.status == MatchStatus.FINISHED

    result2 = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.SCHEDULED, home=0, away=0), result2)
    await session.commit()

    assert result2.synced == 0 and result2.updated == 0
    assert live_fixture.status == MatchStatus.FINISHED
    score = (await session.execute(select(Score).where(Score.fixture_id == live_fixture.id))).scalar_one()
    assert (score.home_score, score.away_score) == (2, 0)


@pytest.mark.asyncio
async def test_finished_score_correction_still_applies(
    session, competition, live_fixture
) -> None:
    # The demotion guard must NOT block a FINISHED→FINISHED correction
    # (e.g. FD revising a wrong final).
    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.FINISHED, home=1, away=0), result)
    await session.commit()

    result2 = ScoreSyncResult()
    await _apply_external_score(session, competition.id, _ext(MatchStatus.FINISHED, home=2, away=0), result2)
    await session.commit()

    assert result2.updated == 1
    score = (await session.execute(select(Score).where(Score.fixture_id == live_fixture.id))).scalar_one()
    assert (score.home_score, score.away_score) == (2, 0)


@pytest.mark.asyncio
async def test_resolution_skips_verified_fixture_without_refetch_loop(
    session, competition, monkeypatch
) -> None:
    # An admin-verified score on a fixture the live response re-delivers:
    # the verified guard must hold through a full sync_scores_once pass and
    # the fixture must not be re-fetched individually.
    fx = _fixture(competition.id, kickoff=NOW - timedelta(hours=1), status=MatchStatus.FINISHED, ext="105")
    session.add(fx)
    await session.commit()
    await session.refresh(fx)
    session.add(Score(fixture_id=fx.id, home_score=3, away_score=1, verified=True))
    await session.commit()

    provider = FakeProvider(live=[_ext(MatchStatus.LIVE, ext_id="105", home=0, away=0)])
    monkeypatch.setattr("app.services.score_sync.get_score_provider", lambda: provider)

    result = await sync_scores_once(session)

    assert result.skipped_verified == 1
    assert provider.fixture_fetches == []
    await session.refresh(fx)
    assert fx.status == MatchStatus.FINISHED
    score = await _get_score(session, fx.id)
    assert (score.home_score, score.away_score) == (3, 1) and score.verified


# ---------------------------------------------------------------------------
# points_relevant: only FINISHED score writes may expire the leaderboard
# cache (v2.173.0). In-play paints update Score rows but cannot move
# points — the scoring engine ignores non-FINISHED fixtures.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_score_paint_is_not_points_relevant(session, live_fixture) -> None:
    result = ScoreSyncResult()
    await _apply_external_score(session, live_fixture.competition_id, _ext(MatchStatus.LIVE, minute=30), result)
    assert result.updated + result.synced == 1
    assert result.points_relevant == 0

    # Score moves while still live — board still can't change.
    result2 = ScoreSyncResult()
    await _apply_external_score(
        session, live_fixture.competition_id, _ext(MatchStatus.LIVE, home=2, away=0, minute=55), result2
    )
    assert result2.updated == 1
    assert result2.points_relevant == 0


@pytest.mark.asyncio
async def test_finish_transition_is_points_relevant(session, live_fixture) -> None:
    result = ScoreSyncResult()
    await _apply_external_score(session, live_fixture.competition_id, _ext(MatchStatus.LIVE, minute=88), result)
    assert result.points_relevant == 0

    result2 = ScoreSyncResult()
    await _apply_external_score(session, live_fixture.competition_id, _ext(MatchStatus.FINISHED), result2)
    assert result2.points_relevant == 1


@pytest.mark.asyncio
async def test_finished_score_correction_is_points_relevant(session, live_fixture) -> None:
    result = ScoreSyncResult()
    await _apply_external_score(session, live_fixture.competition_id, _ext(MatchStatus.FINISHED, home=1, away=0), result)
    assert result.points_relevant == 1

    # Resolution pass re-delivers a corrected final score — points moved.
    result2 = ScoreSyncResult()
    await _apply_external_score(session, live_fixture.competition_id, _ext(MatchStatus.FINISHED, home=2, away=0), result2)
    assert result2.points_relevant == 1


@pytest.mark.asyncio
async def test_identical_finished_redelivery_is_not_points_relevant(session, live_fixture) -> None:
    result = ScoreSyncResult()
    await _apply_external_score(session, live_fixture.competition_id, _ext(MatchStatus.FINISHED, home=1, away=0), result)
    assert result.points_relevant == 1

    # Same final score again — change-detection no-op, no expiry signal.
    result2 = ScoreSyncResult()
    await _apply_external_score(session, live_fixture.competition_id, _ext(MatchStatus.FINISHED, home=1, away=0), result2)
    assert result2.points_relevant == 0
    assert result2.synced == 0 and result2.updated == 0


# ---------------------------------------------------------------------------
# _score_fields_for: 90-minute freeze for ESPN past-regulation events
# ---------------------------------------------------------------------------


def test_score_fields_for_passthrough_when_provider_has_split() -> None:
    """When the provider already carries an ET split, pass through without freeze."""
    fixture = Fixture(stage="round_of_32", status=MatchStatus.FINISHED)
    ext = ExternalScore(
        external_id="1", home_team="A", away_team="B",
        home_score=1, away_score=1,
        home_score_et=2, away_score_et=1,
        home_penalties=4, away_penalties=3,
        status=MatchStatus.FINISHED,
        period=5,
    )
    home, away, home_et, away_et, home_pen, away_pen = _score_fields_for(fixture, ext, None)
    assert (home, away, home_et, away_et, home_pen, away_pen) == (1, 1, 2, 1, 4, 3)


def test_score_fields_for_freeze_preserves_regulation_score() -> None:
    """ESPN period > 2 with no split: freeze the DB regulation score,
    put running total into home_score_et."""
    fixture = Fixture(id=1, stage="round_of_32", status=MatchStatus.LIVE)
    existing = Score(fixture_id=1, home_score=1, away_score=1)
    ext = ExternalScore(
        external_id="", home_team="A", away_team="B",
        home_score=2, away_score=1,   # running total (ESPN folds ET goals in)
        home_score_et=None, away_score_et=None,
        status=MatchStatus.LIVE,
        period=3,
    )
    home, away, home_et, away_et, home_pen, away_pen = _score_fields_for(
        fixture, ext, existing
    )
    assert (home, away) == (1, 1)      # frozen regulation score from DB
    assert (home_et, away_et) == (2, 1)  # running total → ET slot
    assert (home_pen, away_pen) == (None, None)


def test_score_fields_for_no_freeze_for_group_stage() -> None:
    """Group stage fixtures never freeze — no ET/pens in group play."""
    fixture = Fixture(stage="group", status=MatchStatus.LIVE)
    ext = ExternalScore(
        external_id="", home_team="A", away_team="B",
        home_score=2, away_score=1,
        status=MatchStatus.LIVE,
        period=3,   # would trigger freeze for KO — group is excluded
    )
    home, away, home_et, away_et, _, _ = _score_fields_for(fixture, ext, None)
    assert (home, away) == (2, 1)
    assert home_et is None


def test_score_fields_for_no_freeze_for_third_place() -> None:
    """third_place is excluded from the freeze (unscored stage)."""
    fixture = Fixture(stage="third_place", status=MatchStatus.LIVE)
    ext = ExternalScore(
        external_id="", home_team="A", away_team="B",
        home_score=2, away_score=1,
        status=MatchStatus.LIVE,
        period=3,
    )
    home, away, home_et, away_et, _, _ = _score_fields_for(fixture, ext, None)
    assert (home, away) == (2, 1)
    assert home_et is None


# ---------------------------------------------------------------------------
# Shape C: FINISHED KO rows with null penalties auto-enter resolution pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shape_c_finds_finished_ko_with_null_penalties(session, competition) -> None:
    """Shape C: a FINISHED KO fixture with null home_penalties and a Score row
    appears in _find_unresolved_fixtures results."""
    kickoff = datetime.now(timezone.utc) - timedelta(hours=2)
    fixture = Fixture(
        competition_id=competition.id,
        external_id="537418",
        home_team="Netherlands",
        away_team="Morocco",
        kickoff=kickoff,
        stage="round_of_32",
        status=MatchStatus.FINISHED,
        group=None,
        match_number=None,
    )
    session.add(fixture)
    await session.flush()

    score = Score(
        fixture_id=fixture.id,
        home_score=1,
        away_score=1,
        home_score_et=1,
        away_score_et=1,
        home_penalties=None,   # ← Shape C trigger
        away_penalties=None,
        source=ScoreSource.API,
        verified=False,
    )
    session.add(score)
    await session.flush()

    unresolved = await _find_unresolved_fixtures(session, competition.id, set())
    assert fixture.id in [f.id for f in unresolved]


@pytest.mark.asyncio
async def test_shape_c_excludes_verified_scores(session, competition) -> None:
    """Shape C must not re-fetch admin-verified scores (verified=True)."""
    kickoff = datetime.now(timezone.utc) - timedelta(hours=2)
    fixture = Fixture(
        competition_id=competition.id,
        external_id="537419",
        home_team="Germany",
        away_team="Paraguay",
        kickoff=kickoff,
        stage="round_of_32",
        status=MatchStatus.FINISHED,
        group=None,
        match_number=None,
    )
    session.add(fixture)
    await session.flush()

    score = Score(
        fixture_id=fixture.id,
        home_score=1,
        away_score=1,
        home_penalties=None,
        away_penalties=None,
        source=ScoreSource.API,
        verified=True,   # ← admin-locked, must be excluded
    )
    session.add(score)
    await session.flush()

    unresolved = await _find_unresolved_fixtures(session, competition.id, set())
    assert fixture.id not in [f.id for f in unresolved]


@pytest.mark.asyncio
async def test_shape_c_excludes_old_fixtures(session, competition) -> None:
    """Shape C only catches fixtures that kicked off within the last 12 hours."""
    kickoff = datetime.now(timezone.utc) - timedelta(hours=24)  # too old
    fixture = Fixture(
        competition_id=competition.id,
        external_id="537420",
        home_team="Brazil",
        away_team="Japan",
        kickoff=kickoff,
        stage="round_of_32",
        status=MatchStatus.FINISHED,
        group=None,
        match_number=None,
    )
    session.add(fixture)
    await session.flush()

    score = Score(
        fixture_id=fixture.id,
        home_score=1,
        away_score=1,
        home_penalties=None,
        away_penalties=None,
        source=ScoreSource.API,
        verified=False,
    )
    session.add(score)
    await session.flush()

    unresolved = await _find_unresolved_fixtures(session, competition.id, set())
    assert fixture.id not in [f.id for f in unresolved]


# ---------------------------------------------------------------------------
# Slot-placeholder team-name write-back (v2.191.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fd_resolution_writes_real_team_names_back(session, competition) -> None:
    """FD resolution pass writes real names to slot-placeholder fixture rows."""
    fixture = Fixture(
        competition_id=competition.id,
        external_id="537426",
        home_team="slot:round_of_32:537426:home",
        away_team="slot:round_of_32:537426:away",
        kickoff=datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc),
        status=MatchStatus.SCHEDULED,
        stage="round_of_32",
        group=None,
        match_number=None,
    )
    session.add(fixture)
    await session.flush()

    ext = ExternalScore(
        external_id="537426",  # non-empty → came from FD
        home_team="England",
        away_team="Congo DR",
        home_score=1,
        away_score=0,
        status=MatchStatus.LIVE,
        minute=52,
    )

    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, ext, result)

    assert fixture.home_team == "England"
    assert fixture.away_team == "Congo DR"
    assert result.synced == 1
    assert fixture.status == MatchStatus.LIVE
    assert fixture.minute == 52


@pytest.mark.asyncio
async def test_espn_event_cannot_match_slot_placeholder_fixture(session, competition) -> None:
    """ESPN events (external_id='') cannot match slot-placeholder fixtures."""
    fixture = Fixture(
        competition_id=competition.id,
        external_id="537426",
        home_team="slot:round_of_32:537426:home",
        away_team="slot:round_of_32:537426:away",
        kickoff=datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc),
        status=MatchStatus.SCHEDULED,
        stage="round_of_32",
        group=None,
        match_number=None,
    )
    session.add(fixture)
    await session.flush()

    ext = ExternalScore(
        external_id="",  # empty → ESPN, team-name match required
        home_team="England",
        away_team="Congo DR",
        home_score=1,
        away_score=0,
        status=MatchStatus.LIVE,
        minute=52,
    )

    result = ScoreSyncResult()
    touched = await _apply_external_score(session, competition.id, ext, result)

    # _find_fixture returns None (name mismatch) → nothing written
    assert touched is None
    assert result.synced == 0
    assert fixture.home_team.startswith("slot:")


@pytest.mark.asyncio
async def test_fd_resolution_updates_team_names_even_when_score_verified(session, competition) -> None:
    """Team-name write-back fires before the verified guard."""
    fixture = Fixture(
        competition_id=competition.id,
        external_id="537426",
        home_team="slot:round_of_32:537426:home",
        away_team="slot:round_of_32:537426:away",
        kickoff=datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc),
        status=MatchStatus.FINISHED,
        stage="round_of_32",
        group=None,
        match_number=None,
    )
    session.add(fixture)
    await session.flush()

    verified_score = Score(
        fixture_id=fixture.id,
        home_score=1,
        away_score=0,
        source=ScoreSource.MANUAL,
        verified=True,
    )
    session.add(verified_score)
    await session.flush()

    ext = ExternalScore(
        external_id="537426",
        home_team="England",
        away_team="Congo DR",
        home_score=1,
        away_score=0,
        status=MatchStatus.FINISHED,
    )

    result = ScoreSyncResult()
    await _apply_external_score(session, competition.id, ext, result)

    # Score NOT overwritten (admin lock)
    assert result.skipped_verified == 1
    # Team names ARE updated despite the early return
    assert fixture.home_team == "England"
    assert fixture.away_team == "Congo DR"
