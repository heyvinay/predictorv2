"""KO lineup resolver (v2.184.x) — downstream slot resolution.

Extends r32_resolver into a full bracket walker covering R16 / QF / SF / F.
Tests focus on the chained resolution behaviour: when an upstream match
finishes, its winner propagates into the appropriate downstream slot.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource
from app.services.bracket_seeding import (
    FINAL_SOURCES,
    QUARTER_FINAL_SOURCES,
    ROUND_OF_16_SOURCES,
    SEMI_FINAL_SOURCES,
    STAGE_FIRST_MATCH_NUMBER,
    is_downstream_ko_slot_placeholder,
    parse_downstream_ko_slot,
)
from app.services.ko_lineup_resolver import (
    build_ko_lineup_resolver,
    resolve_ko_pair,
)


KICKOFF_R32_BASE = datetime(2026, 6, 28, 19, 0, tzinfo=timezone.utc)
KICKOFF_R16_BASE = datetime(2026, 7, 4, 17, 0, tzinfo=timezone.utc)


# ─── Pure helpers ───────────────────────────────────────────────────────


def test_is_downstream_ko_slot_placeholder_recognises_stages():
    assert is_downstream_ko_slot_placeholder("slot:round_of_16:537376:home") is True
    assert is_downstream_ko_slot_placeholder("slot:quarter_final:537383:away") is True
    assert is_downstream_ko_slot_placeholder("slot:semi_final:1:home") is True
    assert is_downstream_ko_slot_placeholder("slot:final:1:home") is True

    # R32 slots are NOT in scope of this helper — handled by is_r32_slot_placeholder.
    assert is_downstream_ko_slot_placeholder("slot:round_of_32:537417:home") is False

    assert is_downstream_ko_slot_placeholder("Mexico") is False
    assert is_downstream_ko_slot_placeholder(None) is False
    assert is_downstream_ko_slot_placeholder("") is False


def test_parse_downstream_ko_slot_returns_stage_ext_side():
    assert parse_downstream_ko_slot("slot:round_of_16:537376:home") == (
        "round_of_16",
        "537376",
        "home",
    )
    assert parse_downstream_ko_slot("slot:quarter_final:537383:away") == (
        "quarter_final",
        "537383",
        "away",
    )
    # Garbage
    assert parse_downstream_ko_slot("Mexico") is None
    assert parse_downstream_ko_slot("slot:round_of_16:537376") is None


def test_source_maps_have_expected_match_count():
    assert len(ROUND_OF_16_SOURCES) == 8  # M89-M96
    assert len(QUARTER_FINAL_SOURCES) == 4  # M97-M100
    assert len(SEMI_FINAL_SOURCES) == 2  # M101-M102
    assert len(FINAL_SOURCES) == 1  # M104 (M103 = third_place, omitted)
    assert STAGE_FIRST_MATCH_NUMBER == {
        "round_of_16": 89,
        "quarter_final": 97,
        "semi_final": 101,
        "final": 104,
    }


def test_source_maps_reference_only_known_upstream_matches():
    """Every source's match_number must be reachable upstream — sanity check
    against typos when the source maps were ported from frontend."""
    # R16 sources should point to R32 (73-88).
    for sources in ROUND_OF_16_SOURCES.values():
        for src in sources:
            assert 73 <= src["match_number"] <= 88
    # QF sources point to R16 (89-96).
    for sources in QUARTER_FINAL_SOURCES.values():
        for src in sources:
            assert 89 <= src["match_number"] <= 96
    # SF sources point to QF (97-100).
    for sources in SEMI_FINAL_SOURCES.values():
        for src in sources:
            assert 97 <= src["match_number"] <= 100
    # Final sources point to SF (101-102).
    for sources in FINAL_SOURCES.values():
        for src in sources:
            assert 101 <= src["match_number"] <= 102


# ─── Integration — chained resolution against in-memory DB ──────────────


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
    comp = Competition(
        name="WC",
        external_id="WC",
        is_active=True,
        created_at=KICKOFF_R32_BASE,
        updated_at=KICKOFF_R32_BASE,
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _make_fixture(
    session,
    comp_id,
    *,
    home: str,
    away: str,
    stage: str,
    kickoff: datetime,
    ext_id: str | None = None,
    status: MatchStatus = MatchStatus.SCHEDULED,
    score: tuple[int, int, str] | None = None,
) -> Fixture:
    """Add a fixture; optionally attach a Score row with outcome ("1"/"2"/"X")."""
    fx = Fixture(
        competition_id=comp_id,
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        stage=stage,
        group=None,
        status=status,
        external_id=ext_id,
    )
    session.add(fx)
    await session.commit()
    await session.refresh(fx)
    if score is not None:
        home_score, away_score, outcome = score
        session.add(
            Score(
                fixture_id=fx.id,
                home_score=home_score,
                away_score=away_score,
                outcome=outcome,
                source=ScoreSource.MANUAL,
                verified=True,
            )
        )
        await session.commit()
    return fx


async def _seed_r32_full(session, comp_id) -> list[Fixture]:
    """Seed all 16 R32 fixtures with REAL team names (skipping the
    group-stage and r32_resolver wiring) so we can isolate the
    downstream-resolution behaviour.

    Returns the 16 fixtures in FIFA match-number order (M73..M88).
    """
    # Hard-coded mapping ext_id → FIFA match number (real prod data).
    pairs = [
        ("537417", 73, "South Africa", "Canada"),
        ("537415", 74, "Germany", "Paraguay"),
        ("537418", 75, "Netherlands", "Morocco"),
        ("537423", 76, "Brazil", "Japan"),
        ("537416", 77, "France", "Sweden"),
        ("537424", 78, "Ivory Coast", "Norway"),
        ("537425", 79, "Mexico", "Ecuador"),
        ("537426", 80, "England", "Congo DR"),
        ("537421", 81, "United States", "Bosnia-Herzegovina"),
        ("537422", 82, "Belgium", "Senegal"),
        ("537419", 83, "Croatia-2K", "Croatia"),
        ("537420", 84, "Spain", "Austria"),
        ("537429", 85, "Switzerland", "Algeria"),
        ("537427", 86, "Argentina", "Cape Verde"),
        ("537430", 87, "1K", "Ghana"),
        ("537428", 88, "Australia", "Egypt"),
    ]
    # Order by match number; assign kickoffs in M73..M88 sequence so the
    # resolver's kickoff-sorted index would also recover the same order
    # (defensive — R32 uses the ext_id map, not kickoff order, but the
    # fixtures still need plausible kickoffs).
    by_num = sorted(pairs, key=lambda p: p[1])
    fixtures: list[Fixture] = []
    for i, (ext, num, home, away) in enumerate(by_num):
        fx = await _make_fixture(
            session, comp_id,
            home=home, away=away,
            stage="round_of_32",
            kickoff=KICKOFF_R32_BASE + timedelta(hours=i * 3),
            ext_id=ext,
        )
        fixtures.append(fx)
    return fixtures


async def _seed_r16_placeholders(session, comp_id) -> list[Fixture]:
    """Seed all 8 R16 fixtures with slot placeholders, kickoff-ordered
    so the resolver maps them to M89..M96 by kickoff index.
    """
    ext_ids = ["A", "B", "C", "D", "E", "F", "G", "H"]
    fixtures: list[Fixture] = []
    for i, ext in enumerate(ext_ids):
        fx = await _make_fixture(
            session, comp_id,
            home=f"slot:round_of_16:{ext}:home",
            away=f"slot:round_of_16:{ext}:away",
            stage="round_of_16",
            kickoff=KICKOFF_R16_BASE + timedelta(hours=i * 3),
            ext_id=ext,
        )
        fixtures.append(fx)
    return fixtures


@pytest.mark.asyncio
async def test_r16_resolves_when_both_feeding_r32_finished(
    session: AsyncSession, competition: Competition
):
    """R16 M89 = winner(M74) vs winner(M77). With M74 and M77 both
    FINISHED, the R16 fixture's home/away resolves to those winners.
    """
    r32 = await _seed_r32_full(session, competition.id)
    r16 = await _seed_r16_placeholders(session, competition.id)

    # M74 (index 1) = Germany 2-1 Paraguay → home wins
    m74 = r32[1]
    session.add(Score(
        fixture_id=m74.id, home_score=2, away_score=1, outcome="1",
        source=ScoreSource.MANUAL, verified=True,
    ))
    m74.status = MatchStatus.FINISHED
    # M77 (index 4) = France 1-3 Sweden → away wins
    m77 = r32[4]
    session.add(Score(
        fixture_id=m77.id, home_score=1, away_score=3, outcome="2",
        source=ScoreSource.MANUAL, verified=True,
    ))
    m77.status = MatchStatus.FINISHED
    await session.commit()

    # First R16 by kickoff order = M89
    m89 = r16[0]
    resolver = await build_ko_lineup_resolver(session)
    home, away = resolve_ko_pair(resolver, m89)
    assert home == "Germany"  # winner of M74
    assert away == "Sweden"   # winner of M77


@pytest.mark.asyncio
async def test_r16_stays_placeholder_when_upstream_r32_not_finished(
    session: AsyncSession, competition: Competition
):
    """Until BOTH feeding R32s are FINISHED, the R16 slot remains TBD."""
    r32 = await _seed_r32_full(session, competition.id)
    r16 = await _seed_r16_placeholders(session, competition.id)

    # Only M74 finished; M77 still scheduled.
    m74 = r32[1]
    session.add(Score(
        fixture_id=m74.id, home_score=2, away_score=1, outcome="1",
        source=ScoreSource.MANUAL, verified=True,
    ))
    m74.status = MatchStatus.FINISHED
    await session.commit()

    m89 = r16[0]
    resolver = await build_ko_lineup_resolver(session)
    home, away = resolve_ko_pair(resolver, m89)
    assert home == "Germany"  # M74 winner
    assert away == m89.away_team  # M77 unresolved → slot stays


@pytest.mark.asyncio
async def test_qf_resolves_via_two_levels_of_chain(
    session: AsyncSession, competition: Competition
):
    """M97 (QF) = winner(M89) vs winner(M90). M89 needs M74+M77 winners,
    M90 needs M73+M75 winners. With all four R32s + both R16s finished,
    the QF should resolve cleanly to the M89 and M90 winners.
    """
    r32 = await _seed_r32_full(session, competition.id)
    r16 = await _seed_r16_placeholders(session, competition.id)
    # Add one QF fixture (just M97 — the first one by kickoff).
    qf_kickoff = KICKOFF_R16_BASE + timedelta(days=5)
    qf97 = await _make_fixture(
        session, competition.id,
        home="slot:quarter_final:QF1:home",
        away="slot:quarter_final:QF1:away",
        stage="quarter_final",
        kickoff=qf_kickoff,
        ext_id="QF1",
    )

    # Finish all four feeding R32s — note we DON'T set R16 fixture scores;
    # the resolver computes "winner of M89" by walking M89's sources (M74,
    # M77), not by reading M89's own score row.
    #
    # Wait — that's NOT how a real tournament works. To advance from R16
    # to QF, the R16 must be played. So we need: R32 winners feed R16,
    # R16 winners feed QF. The R16 must also be FINISHED with a score.
    for idx, outcome in [(0, "1"), (1, "1"), (3, "1"), (4, "1")]:  # M73, M74, M76, M77
        session.add(Score(
            fixture_id=r32[idx].id, home_score=1, away_score=0, outcome=outcome,
            source=ScoreSource.MANUAL, verified=True,
        ))
        r32[idx].status = MatchStatus.FINISHED
    # Finish R16 M89 and M90 — both home wins so winner = M74 home / M73 home.
    for r16_idx in [0, 1]:  # M89, M90 by kickoff
        session.add(Score(
            fixture_id=r16[r16_idx].id, home_score=2, away_score=0, outcome="1",
            source=ScoreSource.MANUAL, verified=True,
        ))
        r16[r16_idx].status = MatchStatus.FINISHED
    await session.commit()

    resolver = await build_ko_lineup_resolver(session)
    home, away = resolve_ko_pair(resolver, qf97)
    # M89 home winner = M74 winner = Germany
    # M90 home winner = M73 winner = South Africa
    assert home == "Germany"
    assert away == "South Africa"


@pytest.mark.asyncio
async def test_resolver_returns_raw_for_unknown_fixture(
    session: AsyncSession, competition: Competition
):
    """A fixture not in our match-number map (e.g. third_place) falls
    through to the R32 resolver, which then returns the raw strings if
    they aren't R32 slots either.
    """
    fx = await _make_fixture(
        session, competition.id,
        home="Loser101", away="Loser102",
        stage="third_place",
        kickoff=KICKOFF_R16_BASE + timedelta(days=10),
        ext_id="TP1",
    )
    resolver = await build_ko_lineup_resolver(session)
    home, away = resolve_ko_pair(resolver, fx)
    # Neither name is a slot placeholder, so they pass through untouched.
    assert home == "Loser101"
    assert away == "Loser102"
