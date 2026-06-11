"""Tests for the all-entries predictions CSV export (transparency sheet).

Service: app.services.predictions_export.build_all_entries_export
Endpoint: GET /api/predictions/export/all-entries.csv

Gate contract (mirrors the V4 pages): admins always; everyone else only
once competition.post_deadline_live is flipped. Blind pool stays sealed
until release.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — registers all SQLModel tables
from app.database import get_session
from app.dependencies import get_current_user, get_current_user_optional
from app.main import app
from app.models.bonus import BonusPrediction
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import (
    MatchPrediction,
    PredictionPhase,
    TeamPrediction,
)
from app.models.user import AuthProvider, User
from app.services.bonus import get_questions as get_bonus_questions
from app.services.predictions_export import build_all_entries_export

BOM = "﻿"


# ─── DB session fixture ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


# ─── Factory helpers ───────────────────────────────────────────────────


async def _make_competition(
    session: AsyncSession, *, post_deadline_live: bool = False
) -> Competition:
    comp = Competition(
        name="World Cup 2026",
        external_id="WC",
        is_active=True,
        phase1_deadline=datetime(2026, 6, 11, 17, 0, tzinfo=timezone.utc),
        post_deadline_live=post_deadline_live,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _make_user(
    session: AsyncSession,
    email: str,
    name: str | None,
    *,
    is_admin: bool = False,
) -> User:
    u = User(
        email=email,
        name=name,
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_admin=is_admin,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _make_entry(
    session: AsyncSession,
    user: User,
    competition: Competition,
    entry_number: int,
    *,
    status: EntryStatus = EntryStatus.SUBMITTED,
    display_name: str | None = None,
    is_disabled: bool = False,
    withdrawn: bool = False,
) -> PredictionEntry:
    entry = PredictionEntry(
        user_id=user.id,
        competition_id=competition.id,
        display_name=display_name or f"Entry {entry_number}",
        reference=f"WC26-{entry_number:06d}",
        entry_number=entry_number,
        is_disabled=is_disabled,
        withdrawn_at=datetime.now(timezone.utc) if withdrawn else None,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    session.add(
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_1,
            status=status,
            submitted_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
            if status == EntryStatus.SUBMITTED
            else None,
        )
    )
    await session.commit()
    return entry


async def _make_group_fixture(
    session: AsyncSession,
    competition: Competition,
    *,
    home: str,
    away: str,
    group: str,
    hours_offset: int,
) -> Fixture:
    f = Fixture(
        competition_id=competition.id,
        home_team=home,
        away_team=away,
        kickoff=datetime(2026, 6, 12, 15, 0, tzinfo=timezone.utc)
        + timedelta(hours=hours_offset),
        stage="group",
        group=group,
        status=MatchStatus.SCHEDULED,
    )
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


def _parse(csv_text: str) -> list[list[str]]:
    assert csv_text.startswith(BOM), "export must be BOM-prefixed for Excel"
    return list(csv.reader(io.StringIO(csv_text[len(BOM):])))


def _row_with_label(rows: list[list[str]], col: int, label: str) -> list[str]:
    for r in rows:
        if len(r) > col and r[col] == label:
            return r
    raise AssertionError(f"no row with {label!r} in column {col}")


# ─── Service tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_structure_and_content(db_session: AsyncSession):
    """One eligible entry: identity block, group score, alphabetical
    knockout rows, quota row counts, bonus answers."""
    comp = await _make_competition(db_session)
    alice = await _make_user(db_session, "alice@example.com", "Alice")
    entry = await _make_entry(db_session, alice, comp, 1, display_name="The Kings")

    fx = await _make_group_fixture(
        db_session, comp, home="Mexico", away="South Africa", group="A", hours_offset=0
    )
    db_session.add(
        MatchPrediction(
            entry_id=entry.id,
            fixture_id=fx.id,
            phase=PredictionPhase.PHASE_1,
            home_score=2,
            away_score=1,
        )
    )
    # Deliberately unsorted insert — export must alphabetize.
    for team in ["Spain", "Argentina", "Brazil"]:
        db_session.add(
            TeamPrediction(
                entry_id=entry.id,
                team=team,
                stage="round_of_32",
                phase=PredictionPhase.PHASE_1,
            )
        )
    db_session.add(
        TeamPrediction(
            entry_id=entry.id,
            team="Brazil",
            stage="winner",
            phase=PredictionPhase.PHASE_1,
        )
    )
    questions = get_bonus_questions()
    assert questions, "tournament YAML must define bonus questions"
    db_session.add(
        BonusPrediction(
            entry_id=entry.id, question_id=questions[0].id, answer="France"
        )
    )
    await db_session.commit()

    rows = _parse(await build_all_entries_export(db_session, comp))

    # Identity block: labels sit in the 4th column, values follow.
    assert _row_with_label(rows, 3, "Ref")[4] == "WC26-000001"
    assert _row_with_label(rows, 3, "Name")[4] == "Alice"
    assert _row_with_label(rows, 3, "Entry")[4] == "The Kings"
    assert _row_with_label(rows, 3, "Submitted (UTC)")[4] == "2026-06-10 12:00"

    # Group fixture row: date, group, teams, then the score.
    fx_row = next(r for r in rows if len(r) > 2 and r[2] == "Mexico")
    assert fx_row[1] == "A"
    assert fx_row[3] == "South Africa"
    assert fx_row[4] == "2-1"

    # R32: alphabetical, padded to the 32-row quota with blanks.
    r32_first = _row_with_label(rows, 2, "R32 pick 1")
    assert r32_first[4] == "Argentina"
    assert _row_with_label(rows, 2, "R32 pick 2")[4] == "Brazil"
    assert _row_with_label(rows, 2, "R32 pick 3")[4] == "Spain"
    r32_last = _row_with_label(rows, 2, "R32 pick 32")
    assert len(r32_last) == 4 or r32_last[4] == ""
    with pytest.raises(AssertionError):
        _row_with_label(rows, 2, "R32 pick 33")

    # Quota-only sections still emit their full row count.
    _row_with_label(rows, 2, "QF pick 8")
    _row_with_label(rows, 2, "SF pick 4")
    _row_with_label(rows, 2, "Finalist 2")
    assert _row_with_label(rows, 2, "Champion")[4] == "Brazil"

    # Bonus block: answered question carries the answer, others blank.
    q_row = _row_with_label(rows, 2, questions[0].label)
    assert q_row[4] == "France"


@pytest.mark.asyncio
async def test_export_excludes_non_eligible_entries(db_session: AsyncSession):
    """Draft, withdrawn and disabled entries never appear — same pool
    scoring pays."""
    comp = await _make_competition(db_session)
    u = await _make_user(db_session, "multi@example.com", "Multi")
    await _make_entry(db_session, u, comp, 1)  # eligible
    await _make_entry(db_session, u, comp, 2, status=EntryStatus.DRAFT)
    await _make_entry(db_session, u, comp, 3, withdrawn=True)
    await _make_entry(db_session, u, comp, 4, is_disabled=True)

    rows = _parse(await build_all_entries_export(db_session, comp))
    ref_row = _row_with_label(rows, 3, "Ref")
    assert ref_row[4:] == ["WC26-000001"]
    entries_row = next(r for r in rows if r and r[0] == "Entries")
    assert entries_row[1] == "1"


@pytest.mark.asyncio
async def test_export_guards_formula_injection(db_session: AsyncSession):
    """User-supplied strings starting with =, +, -, @ are apostrophe-
    escaped so Excel treats them as text."""
    comp = await _make_competition(db_session)
    evil = await _make_user(db_session, "evil@example.com", "=cmd|' /C calc'!A0")
    await _make_entry(db_session, evil, comp, 1, display_name="+SUM(1)")

    rows = _parse(await build_all_entries_export(db_session, comp))
    assert _row_with_label(rows, 3, "Name")[4].startswith("'=")
    assert _row_with_label(rows, 3, "Entry")[4].startswith("'+")


@pytest.mark.asyncio
async def test_export_missing_picks_render_blank(db_session: AsyncSession):
    """An eligible entry with no predictions yields blank cells, not
    invented values, and no dropped rows."""
    comp = await _make_competition(db_session)
    u = await _make_user(db_session, "empty@example.com", "Empty")
    await _make_entry(db_session, u, comp, 1)
    await _make_group_fixture(
        db_session, comp, home="Canada", away="Qatar", group="B", hours_offset=1
    )

    rows = _parse(await build_all_entries_export(db_session, comp))
    fx_row = next(r for r in rows if len(r) > 2 and r[2] == "Canada")
    assert len(fx_row) == 4 or fx_row[4] == ""
    champion = _row_with_label(rows, 2, "Champion")
    assert len(champion) == 4 or champion[4] == ""


# ─── Endpoint gate tests ───────────────────────────────────────────────


def _override(db_session: AsyncSession, *, viewer: User | None):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    if viewer is not None:
        app.dependency_overrides[get_current_user] = lambda: viewer
        app.dependency_overrides[get_current_user_optional] = lambda: viewer
    else:
        app.dependency_overrides[get_current_user_optional] = lambda: None


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


URL = "/api/predictions/export/all-entries.csv"


class TestExportGate:
    async def test_unauthenticated_gets_401(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        await _make_competition(db_session)
        _override(db_session, viewer=None)
        r = await client.get(URL)
        assert r.status_code == 401

    async def test_non_admin_pre_release_gets_403(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        await _make_competition(db_session, post_deadline_live=False)
        alice = await _make_user(db_session, "alice@example.com", "Alice")
        _override(db_session, viewer=alice)
        r = await client.get(URL)
        assert r.status_code == 403

    async def test_admin_pre_release_gets_csv(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        await _make_competition(db_session, post_deadline_live=False)
        admin = await _make_user(
            db_session, "admin@example.com", "Admin", is_admin=True
        )
        _override(db_session, viewer=admin)
        r = await client.get(URL)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "all-entries-predictions-" in r.headers["content-disposition"]
        assert "GROUP STAGE" in r.text

    async def test_pool_post_release_gets_csv(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        comp = await _make_competition(db_session, post_deadline_live=True)
        bob = await _make_user(db_session, "bob@example.com", "Bob")
        await _make_entry(db_session, bob, comp, 1)
        _override(db_session, viewer=bob)
        r = await client.get(URL)
        assert r.status_code == 200
        assert "WC26-000001" in r.text

    async def test_no_active_competition_gets_404(
        self, db_session: AsyncSession, client: AsyncClient
    ):
        admin = await _make_user(
            db_session, "admin@example.com", "Admin", is_admin=True
        )
        _override(db_session, viewer=admin)
        r = await client.get(URL)
        assert r.status_code == 404
