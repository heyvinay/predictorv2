"""R32 slot-placeholder resolver (v2.182.1).

Resolves `slot:round_of_32:{external_id}:home|away` placeholders against
computed group standings + bracket config. Read-time only — the DB is
never written.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
    EXT_ID_TO_MATCH_NUMBER,
    is_r32_slot_placeholder,
    parse_r32_slot,
)
from app.services.r32_resolver import build_r32_resolver, resolve_r32_pair


KICKOFF = datetime(2026, 6, 14, 17, 0, tzinfo=timezone.utc)


# ───────────────────────────────────────────────────────────────────────────
# Pure helpers
# ───────────────────────────────────────────────────────────────────────────


def test_is_r32_slot_placeholder_recognises_format():
    assert is_r32_slot_placeholder("slot:round_of_32:537415:home") is True
    assert is_r32_slot_placeholder("slot:round_of_32:537430:away") is True
    assert is_r32_slot_placeholder("Mexico") is False
    assert is_r32_slot_placeholder(None) is False
    assert is_r32_slot_placeholder("") is False
    assert is_r32_slot_placeholder("slot:round_of_16:1:home") is False


def test_parse_r32_slot_returns_ext_and_side():
    assert parse_r32_slot("slot:round_of_32:537415:home") == ("537415", "home")
    assert parse_r32_slot("slot:round_of_32:537430:away") == ("537430", "away")


def test_parse_r32_slot_returns_none_for_garbage():
    assert parse_r32_slot("Mexico") is None
    assert parse_r32_slot("slot:round_of_32:537415") is None  # missing side
    assert parse_r32_slot("slot:round_of_32:537415:left") is None  # bad side


def test_ext_to_match_number_covers_all_16():
    # Cross-referenced against Wikipedia kickoff schedule. See
    # tests/test_r32_ext_id_mapping.py for the full pinned R32 set,
    # and tests/test_ko_ext_id_mapping.py for R16/QF/SF/Final.
    # The map was extended KO-wide in v2.195.x; this test checks the
    # R32 slice specifically.
    r32_slice = {k: v for k, v in EXT_ID_TO_MATCH_NUMBER.items() if 73 <= v <= 88}
    assert len(r32_slice) == 16
    assert EXT_ID_TO_MATCH_NUMBER["537417"] == 73  # SA vs Canada (first R32)
    assert EXT_ID_TO_MATCH_NUMBER["537430"] == 87  # 1K vs Ghana (last R32)
    assert EXT_ID_TO_MATCH_NUMBER["537423"] == 76  # Brazil vs Japan


# ───────────────────────────────────────────────────────────────────────────
# Integration — resolver against real-shape data
# ───────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_group(
    session: AsyncSession, comp_id, *, group: str, results: list[tuple[str, str, int, int]]
):
    """Add the 6 group-stage matches + scores to settle a group.

    `results`: list of (home, away, home_score, away_score). Provide all
    6 matches for full settlement.
    """
    for home, away, hs, asc in results:
        fx = Fixture(
            competition_id=comp_id,
            home_team=home,
            away_team=away,
            kickoff=KICKOFF,
            stage="group",
            group=group,
            status=MatchStatus.FINISHED,
        )
        session.add(fx)
        await session.commit()
        await session.refresh(fx)
        session.add(
            Score(
                fixture_id=fx.id,
                home_score=hs,
                away_score=asc,
                source=ScoreSource.MANUAL,
                verified=True,
            )
        )
    await session.commit()


async def _make_r32_placeholder(session: AsyncSession, comp_id, ext_id: str):
    fx = Fixture(
        competition_id=comp_id,
        home_team=f"slot:round_of_32:{ext_id}:home",
        away_team=f"slot:round_of_32:{ext_id}:away",
        kickoff=KICKOFF,
        stage="round_of_32",
        group=None,
        status=MatchStatus.SCHEDULED,
        external_id=ext_id,
    )
    session.add(fx)
    await session.commit()
    await session.refresh(fx)
    return fx


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(
        name="WC", external_id="WC", is_active=True,
        created_at=KICKOFF, updated_at=KICKOFF, max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


@pytest.mark.asyncio
async def test_resolver_resolves_group_position_for_settled_group(
    session: AsyncSession, competition: Competition
):
    """Settle Group A. Verify R32 home slot for match 79 (1A) → group A's winner."""
    # Group A: Mexico wins all 3, S. Korea second, S. Africa third, Czechia fourth.
    await _make_group(session, competition.id, group="A", results=[
        ("Mexico", "S. Korea", 2, 0),
        ("S. Africa", "Czechia", 1, 0),
        ("Mexico", "S. Africa", 3, 1),
        ("S. Korea", "Czechia", 2, 1),
        ("Mexico", "Czechia", 1, 0),
        ("S. Korea", "S. Africa", 0, 1),
    ])
    # Match 79 is `1A vs 3rd[C,E,F,H,I]` → ext_id 537425 (per pinned
    # kickoff cross-reference; the earlier 537421 assumption was wrong).
    fx = await _make_r32_placeholder(session, competition.id, "537425")

    resolver = await build_r32_resolver(session)
    home, away = resolve_r32_pair(resolver, fx.home_team, fx.away_team)
    assert home == "Mexico"  # 1A
    # Away is third-place — until all 12 groups settle, no Annex C
    # lookup; placeholder stays.
    assert away == fx.away_team


@pytest.mark.asyncio
async def test_third_place_resolves_via_annex_c_when_all_groups_settled(
    session: AsyncSession, competition: Competition
):
    """When all 12 groups are settled, third-place sources resolve via
    the FIFA Annex C table (v2.183.0). The exact team depends on the
    Annex C row for the qualifying-8 key — this test only asserts that
    a real team comes out, NOT a placeholder. Specific assignments are
    covered by the live-data smoke test in dev."""
    for grp_letter in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]:
        await _make_group(session, competition.id, group=grp_letter, results=[
            (f"{grp_letter}1", f"{grp_letter}2", 2, 0),
            (f"{grp_letter}3", f"{grp_letter}4", 1, 0),
            (f"{grp_letter}1", f"{grp_letter}3", 1, 0),
            (f"{grp_letter}2", f"{grp_letter}4", 2, 1),
            (f"{grp_letter}1", f"{grp_letter}4", 1, 0),
            (f"{grp_letter}2", f"{grp_letter}3", 0, 1),
        ])

    # M74 (1E vs third_place) is ext 537415 per pinned cross-reference.
    fx = await _make_r32_placeholder(session, competition.id, "537415")
    resolver = await build_r32_resolver(session)
    home, away = resolve_r32_pair(resolver, fx.home_team, fx.away_team)
    assert home == "E1"  # 1E from settled Group E
    # Third-place away should now be a real team name (from the Annex C
    # lookup), NOT a slot placeholder.
    assert away is not None
    assert not away.startswith("slot:round_of_32:")
    # Per the synthetic fixture scoring pattern (g1 wins all, g3 wins
    # two, g2 wins one, g4 loses all), each group's third-placed team
    # is "{g}2". So Annex C lookup should land on one of those.
    assert any(away == f"{g}2" for g in "ABCDEFGHIJKL")


@pytest.mark.asyncio
async def test_third_place_unresolved_when_some_groups_pending(
    session: AsyncSession, competition: Competition
):
    """Until ALL 12 groups settle, third-place sources stay TBD — the
    qualifying-8 letters could still change."""
    # 11 settled, 1 pending.
    for grp_letter in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]:
        await _make_group(session, competition.id, group=grp_letter, results=[
            (f"{grp_letter}1", f"{grp_letter}2", 2, 0),
            (f"{grp_letter}3", f"{grp_letter}4", 1, 0),
            (f"{grp_letter}1", f"{grp_letter}3", 1, 0),
            (f"{grp_letter}2", f"{grp_letter}4", 2, 1),
            (f"{grp_letter}1", f"{grp_letter}4", 1, 0),
            (f"{grp_letter}2", f"{grp_letter}3", 0, 1),
        ])
    # Group L: 5 finished, 1 scheduled — not settled.
    await _make_group(session, competition.id, group="L", results=[
        ("L1", "L2", 2, 0),
        ("L3", "L4", 1, 0),
        ("L1", "L3", 1, 0),
        ("L2", "L4", 2, 1),
        ("L1", "L4", 1, 0),
    ])
    pending = Fixture(
        competition_id=competition.id, home_team="L2", away_team="L3",
        kickoff=KICKOFF, stage="group", group="L", status=MatchStatus.SCHEDULED,
    )
    session.add(pending)
    await session.commit()

    # M74 (1E vs third_place) is ext 537415 per pinned cross-reference.
    fx = await _make_r32_placeholder(session, competition.id, "537415")
    resolver = await build_r32_resolver(session)
    home, away = resolve_r32_pair(resolver, fx.home_team, fx.away_team)
    assert home == "E1"  # 1E side resolves — Group E settled
    # Third-place stays as placeholder until Group L settles.
    assert away == fx.away_team
    assert away.startswith("slot:round_of_32:")


@pytest.mark.asyncio
async def test_resolver_skips_unsettled_groups(
    session: AsyncSession, competition: Competition
):
    """Group A has 5 FINISHED + 1 SCHEDULED — real prod shape for an
    in-progress matchday-3. The group is not settled, so no resolution."""
    await _make_group(session, competition.id, group="A", results=[
        ("Mexico", "S. Korea", 2, 0),
        ("S. Africa", "Czechia", 1, 0),
        ("Mexico", "S. Africa", 3, 1),
        ("S. Korea", "Czechia", 2, 1),
        ("Mexico", "Czechia", 1, 0),
    ])
    # The 6th fixture is SCHEDULED — group still incomplete.
    fx_pending = Fixture(
        competition_id=competition.id,
        home_team="S. Korea", away_team="S. Africa",
        kickoff=KICKOFF, stage="group", group="A",
        status=MatchStatus.SCHEDULED,
    )
    session.add(fx_pending)
    await session.commit()

    fx = await _make_r32_placeholder(session, competition.id, "537421")

    resolver = await build_r32_resolver(session)
    home, away = resolve_r32_pair(resolver, fx.home_team, fx.away_team)
    # Both should remain as placeholders.
    assert home == fx.home_team
    assert away == fx.away_team


@pytest.mark.asyncio
async def test_resolver_leaves_non_placeholder_names_untouched(
    session: AsyncSession, competition: Competition
):
    """Once Football-Data publishes real names, the resolver is a no-op."""
    await _make_group(session, competition.id, group="A", results=[
        ("Mexico", "S. Korea", 2, 0),
        ("S. Africa", "Czechia", 1, 0),
        ("Mexico", "S. Africa", 3, 1),
        ("S. Korea", "Czechia", 2, 1),
        ("Mexico", "Czechia", 1, 0),
        ("S. Korea", "S. Africa", 0, 1),
    ])

    resolver = await build_r32_resolver(session)
    home, away = resolve_r32_pair(resolver, "Mexico", "Senegal")
    assert home == "Mexico"
    assert away == "Senegal"


@pytest.mark.asyncio
async def test_resolver_returns_unknown_external_id_unchanged(
    session: AsyncSession, competition: Competition
):
    """A slot placeholder with an unrecognised ext_id stays a placeholder."""
    await _make_group(session, competition.id, group="A", results=[
        ("Mexico", "S. Korea", 2, 0),
        ("S. Africa", "Czechia", 1, 0),
        ("Mexico", "S. Africa", 3, 1),
        ("S. Korea", "Czechia", 2, 1),
        ("Mexico", "Czechia", 1, 0),
        ("S. Korea", "S. Africa", 0, 1),
    ])

    placeholder = "slot:round_of_32:999999:home"
    resolver = await build_r32_resolver(session)
    home, away = resolve_r32_pair(resolver, placeholder, None)
    assert home == placeholder  # unchanged
