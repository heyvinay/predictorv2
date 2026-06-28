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
    assert len(EXT_ID_TO_MATCH_NUMBER) == 16
    assert EXT_ID_TO_MATCH_NUMBER["537415"] == 73
    assert EXT_ID_TO_MATCH_NUMBER["537430"] == 88


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
    # Match 79 is `1A vs 3rd[C,E,F,H,I]` → ext_id 537421.
    fx = await _make_r32_placeholder(session, competition.id, "537421")

    resolver = await build_r32_resolver(session)
    home, away = resolve_r32_pair(resolver, fx.home_team, fx.away_team)
    assert home == "Mexico"  # 1A
    # Away is third-place — resolver returns None (the placeholder stays
    # untouched) until FIFA's Annex C assignment is wired in (v2.183.0).
    assert away == fx.away_team


@pytest.mark.asyncio
async def test_third_place_sources_never_resolve_in_v2_182_2(
    session: AsyncSession, competition: Competition
):
    """All 8 R32 third-place sources stay as TBD placeholders. Greedy
    resolution was producing wrong picks vs FIFA's Annex C — better
    to surface TBD than to surface a wrong-with-confidence team name."""
    # Settle every group so the greedy logic would otherwise activate.
    for grp_letter in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]:
        await _make_group(session, competition.id, group=grp_letter, results=[
            (f"{grp_letter}1", f"{grp_letter}2", 2, 0),
            (f"{grp_letter}3", f"{grp_letter}4", 1, 0),
            (f"{grp_letter}1", f"{grp_letter}3", 1, 0),
            (f"{grp_letter}2", f"{grp_letter}4", 2, 1),
            (f"{grp_letter}1", f"{grp_letter}4", 1, 0),
            (f"{grp_letter}2", f"{grp_letter}3", 0, 1),
        ])

    # M74 (ext 537416) has third_place away source.
    fx = await _make_r32_placeholder(session, competition.id, "537416")
    resolver = await build_r32_resolver(session)
    home, away = resolve_r32_pair(resolver, fx.home_team, fx.away_team)
    assert home == "E1"  # 1E from Group E settled
    # Third-place away stays as placeholder — no greedy assignment.
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
