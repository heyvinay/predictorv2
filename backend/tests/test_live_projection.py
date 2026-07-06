"""Live projected-leaderboard overlay service tests (v2.198.0).

Conventions mirror test_leaderboard_v4.py: in-memory aiosqlite,
self-contained fixtures. `project_rows` is pure — no DB needed for those
two tests. The remaining tests exercise the DB-backed helpers directly
against a real in-memory session.
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models
from app.models.competition import Competition
from app.models.entry import PredictionEntry
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import TeamPrediction
from app.models.score import Score
from app.models.user import AuthProvider, User
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardResponse, PointBreakdown
from app.services.live_projection import (
    _deltas_by_entry,
    _has_live_ko,
    _live_ko_advances,
    apply_live_projection,
    project_rows,
)
from app.services.scoring import get_actual_advancement, get_scoring_config


def _entry(name: str, total: int, exact: int = 0) -> LeaderboardEntry:
    return LeaderboardEntry(
        entry_id=uuid.uuid4(),
        entry_name=name,
        user_id=uuid.uuid4(),
        user_name=name,
        position=0,
        total_points=total,
        breakdown=PointBreakdown(),
        exact_scores=exact,
    )


def test_project_rows_reranks_and_leaves_banked_untouched():
    james = _entry("James", 512)
    sarah = _entry("Sarah", 498)
    kevin = _entry("Kevin", 470)
    banked = [james, sarah, kevin]  # banked order: James, Sarah, Kevin
    deltas = {kevin.entry_id: 30}  # Kevin's live pick advances → +30 → 500

    out = project_rows(banked, deltas)

    # New list of copies — inputs untouched (cache protection).
    assert banked[0].total_points == 512 and banked[0].projected_total is None
    # Re-ranked by projected total: James 512, Kevin 500, Sarah 498.
    assert [r.entry_name for r in out] == ["James", "Kevin", "Sarah"]
    kevin_out = next(r for r in out if r.entry_name == "Kevin")
    assert kevin_out.projected_total == 500
    assert kevin_out.live_delta == 30
    assert kevin_out.projected_position == 2
    assert kevin_out.total_points == 470  # banked stays banked


def test_project_rows_zero_delta_keeps_banked_order():
    rows = [_entry("A", 300), _entry("B", 200)]
    out = project_rows(rows, {})
    assert [r.projected_total for r in out] == [300, 200]
    assert [r.projected_position for r in out] == [1, 2]
    assert all(r.live_delta == 0 for r in out)


# ---------------------------------------------------------------------------
# Service-level integration tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(db_session: AsyncSession) -> Competition:
    comp = Competition(
        name="Test World Cup",
        external_id="WC",
        is_active=True,
        phase1_deadline=datetime(2020, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
        knockout_scoring_enabled=True,
        live_projection_enabled=True,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


def _fixture(
    competition: Competition,
    *,
    home: str,
    away: str,
    stage: str,
    status: MatchStatus = MatchStatus.SCHEDULED,
) -> Fixture:
    return Fixture(
        competition_id=competition.id,
        home_team=home,
        away_team=away,
        kickoff=datetime(2026, 6, 15, 18, tzinfo=timezone.utc),
        stage=stage,
        status=status,
    )


async def _make_entry(
    db_session: AsyncSession,
    competition: Competition,
    *,
    email: str,
    entry_number: int = 1,
) -> PredictionEntry:
    user = User(
        email=email,
        name=email.split("@")[0].title(),
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6]}",
        display_name=f"{user.name}'s Entry",
        entry_number=entry_number,
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_live_advance_uses_penalty_blind_scoreline(db_session, competition):
    fx = _fixture(
        competition,
        home="Brazil",
        away="Ghana",
        stage="round_of_32",
        status=MatchStatus.LIVE,
    )
    db_session.add(fx)
    await db_session.commit()
    await db_session.refresh(fx)

    # Regular-time scoreline favours Brazil, but a bogus in-progress
    # penalty tally (simulating a stray partial pen count while still
    # LIVE) favours Ghana. The decision must ignore the pens.
    db_session.add(
        Score(
            fixture_id=fx.id,
            home_score=1,
            away_score=0,
            home_penalties=1,
            away_penalties=2,
        )
    )
    await db_session.commit()

    advances = await _live_ko_advances(db_session)

    assert len(advances) == 1
    assert advances[0].team == "Brazil"
    assert advances[0].next_stage == "round_of_16"


@pytest.mark.asyncio
async def test_level_live_match_projects_nothing(db_session, competition):
    fx = _fixture(
        competition,
        home="Japan",
        away="Spain",
        stage="round_of_32",
        status=MatchStatus.LIVE,
    )
    db_session.add(fx)
    await db_session.commit()
    await db_session.refresh(fx)

    db_session.add(Score(fixture_id=fx.id, home_score=1, away_score=1))
    await db_session.commit()

    assert await _has_live_ko(db_session) is True
    assert await _live_ko_advances(db_session) == []


@pytest.mark.asyncio
async def test_gates_closed_returns_response_untouched(db_session):
    comp = Competition(
        name="Gated World Cup",
        is_active=True,
        knockout_scoring_enabled=False,
        live_projection_enabled=True,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)

    response = LeaderboardResponse(
        entries=[],
        last_calculated=datetime(2026, 6, 20, tzinfo=timezone.utc),
        total_participants=0,
    )

    out = await apply_live_projection(db_session, response)

    assert out.live_projection_active is False
    assert out is response


@pytest.mark.asyncio
async def test_apply_live_projection_credits_matching_team_prediction(
    db_session, competition
):
    """End-to-end happy path: gates open + a live, decisive KO match +
    a real TeamPrediction on the NEXT stage → the owning entry's row in
    the banked LeaderboardResponse gets projected_total/live_delta, and
    the response is marked live_projection_active. This is the only test
    that actually exercises _deltas_by_entry's TeamPrediction query
    against a real row — the highest-risk path in the whole service
    (a phase filter or team-name mismatch here would silently zero out
    every projection)."""
    entry = await _make_entry(db_session, competition, email="entrant@example.com")

    fx = _fixture(
        competition,
        home="Brazil",
        away="Ghana",
        stage="round_of_32",
        status=MatchStatus.LIVE,
    )
    db_session.add(fx)
    await db_session.commit()
    await db_session.refresh(fx)
    db_session.add(Score(fixture_id=fx.id, home_score=1, away_score=0))
    await db_session.commit()

    # Entry picked Brazil to reach the round_of_16 (the stage the R32
    # winner advances to) — this is the pick the live match should credit.
    db_session.add(
        TeamPrediction(entry_id=entry.id, team="Brazil", stage="round_of_16")
    )
    await db_session.commit()

    expected_delta = int(get_scoring_config()["advancement"]["round_of_16"])

    response = LeaderboardResponse(
        entries=[
            LeaderboardEntry(
                entry_id=entry.id,
                entry_name=entry.display_name,
                user_id=entry.user_id,
                user_name="Entrant",
                position=1,
                total_points=200,
                breakdown=PointBreakdown(),
            )
        ],
        last_calculated=datetime(2026, 6, 20, tzinfo=timezone.utc),
        total_participants=1,
    )

    out = await apply_live_projection(db_session, response)

    assert out is not response
    assert out.live_projection_active is True
    row = out.entries[0]
    assert row.live_delta == expected_delta
    assert row.projected_total == 200 + expected_delta
    assert row.projected_position == 1
    # Banked fields on the returned row stay banked.
    assert row.total_points == 200


@pytest.mark.asyncio
async def test_deltas_by_entry_skips_already_banked_advancement(db_session, competition):
    """Reproduces the race the whole-feature review caught: a downstream
    fixture's real team name is seeded (Football-Data lineup publish, or an
    admin manual correction via /admin/sync) BEFORE the feeding match's
    status has caught up to FINISHED in our DB. get_actual_advancement()
    already credits the team's backers with the real, banked next-stage
    points — purely from the downstream fixture's seeding, independent of
    the feeding match's status (v2.161.0 lineup-based timing). If
    _deltas_by_entry blindly credited the still-LIVE feeding match's
    provisional advance on top of that, the entry would be double-counted,
    then silently drop back down the moment the feeding match's status
    catches up to FINISHED — the exact visible-dip failure mode this
    feature exists to prevent, arriving via a different path than the one
    the original plan anticipated."""
    entry = await _make_entry(db_session, competition, email="racer@example.com")

    # Feeding match: R16 Brazil vs Ghana, still LIVE, Brazil leading 1-0.
    feeding = _fixture(
        competition,
        home="Brazil",
        away="Ghana",
        stage="round_of_16",
        status=MatchStatus.LIVE,
    )
    db_session.add(feeding)
    await db_session.commit()
    await db_session.refresh(feeding)
    db_session.add(Score(fixture_id=feeding.id, home_score=1, away_score=0))
    await db_session.commit()

    # Downstream match: QF fixture already has Brazil seeded as a REAL name
    # — simulating FD (or an admin) publishing this lineup ahead of the
    # feeding match's FINISHED transition. Still SCHEDULED (hasn't kicked
    # off) — irrelevant to get_actual_advancement's "reached this stage"
    # crediting, which only cares about the team being seeded, not the
    # fixture's own status.
    downstream = _fixture(
        competition,
        home="Brazil",
        away="slot:quarter_final:999:away",
        stage="quarter_final",
        status=MatchStatus.SCHEDULED,
    )
    db_session.add(downstream)
    await db_session.commit()

    # Entry picked Brazil to reach the quarter_final — the exact pick that
    # both the banked path AND the live path would credit.
    db_session.add(
        TeamPrediction(entry_id=entry.id, team="Brazil", stage="quarter_final")
    )
    await db_session.commit()

    # 1. Confirm the banked path already credits Brazil at quarter_final —
    #    proving the race precondition is genuinely reproduced.
    actual_advancement = await get_actual_advancement(db_session)
    assert actual_advancement.get("Brazil") == "quarter_final"

    # 2. Confirm the live path ALSO thinks it should credit this — proving
    #    both paths independently believe they own the credit.
    advances = await _live_ko_advances(db_session)
    assert len(advances) == 1
    assert advances[0].team == "Brazil"
    assert advances[0].next_stage == "quarter_final"

    # 3. The gap-check must suppress the live credit: delta should be 0 /
    #    entry absent, NOT the quarter_final points value again.
    deltas = await _deltas_by_entry(db_session, advances)
    assert deltas.get(entry.id, 0) == 0

    # 4. End-to-end: banked total already reflects the QF credit (simulated
    #    here as a hardcoded banked total) — projected_total must equal
    #    total_points exactly, with zero live_delta reaching the overlay.
    qf_points = int(get_scoring_config()["advancement"]["quarter_final"])
    banked_total_including_qf_credit = 200 + qf_points
    response = LeaderboardResponse(
        entries=[
            LeaderboardEntry(
                entry_id=entry.id,
                entry_name=entry.display_name,
                user_id=entry.user_id,
                user_name="Racer",
                position=1,
                total_points=banked_total_including_qf_credit,
                breakdown=PointBreakdown(),
            )
        ],
        last_calculated=datetime(2026, 6, 20, tzinfo=timezone.utc),
        total_participants=1,
    )

    out = await apply_live_projection(db_session, response)

    row = out.entries[0]
    assert row.live_delta == 0
    assert row.projected_total == row.total_points == banked_total_including_qf_credit


@pytest.mark.asyncio
async def test_deltas_by_entry_still_credits_normal_unbanked_advance(
    db_session, competition
):
    """Non-race control case: the downstream fixture is STILL
    placeholder-seeded (no real team name yet) while the feeding match is
    LIVE. get_actual_advancement has nothing to bank for this team at this
    stage, so _already_banked must return False and the normal live delta
    must still be credited — proving the gap-check doesn't overcorrect and
    silently kill the feature's actual purpose."""
    entry = await _make_entry(db_session, competition, email="normal@example.com")

    feeding = _fixture(
        competition,
        home="Brazil",
        away="Ghana",
        stage="round_of_16",
        status=MatchStatus.LIVE,
    )
    db_session.add(feeding)
    await db_session.commit()
    await db_session.refresh(feeding)
    db_session.add(Score(fixture_id=feeding.id, home_score=1, away_score=0))
    await db_session.commit()

    # Downstream QF fixture is STILL placeholder-seeded — no real team name
    # for either side yet, so get_actual_advancement cannot have banked
    # Brazil at quarter_final via this path.
    downstream = _fixture(
        competition,
        home="slot:quarter_final:999:home",
        away="slot:quarter_final:999:away",
        stage="quarter_final",
        status=MatchStatus.SCHEDULED,
    )
    db_session.add(downstream)
    await db_session.commit()

    db_session.add(
        TeamPrediction(entry_id=entry.id, team="Brazil", stage="quarter_final")
    )
    await db_session.commit()

    actual_advancement = await get_actual_advancement(db_session)
    assert actual_advancement.get("Brazil") != "quarter_final"

    advances = await _live_ko_advances(db_session)
    deltas = await _deltas_by_entry(db_session, advances)

    expected_delta = int(get_scoring_config()["advancement"]["quarter_final"])
    assert deltas.get(entry.id) == expected_delta
