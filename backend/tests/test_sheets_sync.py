"""Tests for the Google Sheets sync (v2.177.0).

Service: app.services.sheets_sync

We never hit the real Google API — `_open_spreadsheet` is monkeypatched
with a fake recording spreadsheet, and `get_settings` is swapped for a
lightweight stand-in so the configuration gate is exercised without env
plumbing. The gspread/google-auth imports are lazy and therefore never
touched by these tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — registers all SQLModel tables
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services import sheets_sync


# ─── Fakes ─────────────────────────────────────────────────────────────


@dataclass
class _FakeSettings:
    sheets_sync_enabled: bool = True
    google_sheet_id: str = "sheet-123"
    google_service_account_json: str = '{"client_email": "svc@x.iam"}'


class _FakeWorksheet:
    def __init__(self, title: str, sheet_id: int = 0):
        self.title = title
        self.id = sheet_id  # numeric sheetId — formatting needs this
        self.values: list[list[str]] | None = None
        self.cleared = False

    def clear(self):
        self.cleared = True

    def resize(self, rows: int, cols: int):
        self._size = (rows, cols)

    def update(self, values, a1=None, **_kwargs):
        # **_kwargs absorbs value_input_option and any future gspread args
        self.values = values


class _FakeSpreadsheet:
    def __init__(self):
        self.tabs: dict[str, _FakeWorksheet] = {}
        self._next_id: int = 0
        # Capture batch_update calls so tests can assert formatting requests.
        self.batch_requests: list[dict] = []
        self.deleted: list[str] = []

    def worksheet(self, title: str) -> _FakeWorksheet:
        if title not in self.tabs:
            raise RuntimeError("WorksheetNotFound")  # mimics gspread
        return self.tabs[title]

    def add_worksheet(self, title: str, rows: int, cols: int) -> _FakeWorksheet:
        ws = _FakeWorksheet(title, sheet_id=self._next_id)
        self._next_id += 1
        self.tabs[title] = ws
        return ws

    def batch_update(self, body):
        self.batch_requests.append(body)

    def del_worksheet(self, ws):
        for title, candidate in list(self.tabs.items()):
            if candidate is ws:
                del self.tabs[title]
                self.deleted.append(title)
                return
        raise RuntimeError("WorksheetNotFound")


# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_competition(session: AsyncSession) -> Competition:
    comp = Competition(
        name="World Cup 2026",
        external_id="WC",
        is_active=True,
        phase1_deadline=datetime(2026, 6, 11, 17, 0, tzinfo=timezone.utc),
        post_deadline_live=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _make_eligible_entry(
    session: AsyncSession, comp: Competition, n: int
) -> PredictionEntry:
    user = User(
        email=f"u{n}@example.com",
        name=f"User {n}",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    entry = PredictionEntry(
        user_id=user.id,
        competition_id=comp.id,
        display_name=f"Entry {n}",
        reference=f"WC26-{n:06d}",
        entry_number=n,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    session.add(
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.SUBMITTED,
            submitted_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        )
    )
    await session.commit()
    return entry


# ─── is_configured gate ────────────────────────────────────────────────


def test_is_configured_requires_all_three(monkeypatch):
    monkeypatch.setattr(sheets_sync, "get_settings", lambda: _FakeSettings())
    assert sheets_sync.is_configured() is True

    monkeypatch.setattr(
        sheets_sync, "get_settings", lambda: _FakeSettings(sheets_sync_enabled=False)
    )
    assert sheets_sync.is_configured() is False

    monkeypatch.setattr(
        sheets_sync, "get_settings", lambda: _FakeSettings(google_sheet_id="")
    )
    assert sheets_sync.is_configured() is False

    monkeypatch.setattr(
        sheets_sync,
        "get_settings",
        lambda: _FakeSettings(google_service_account_json=""),
    )
    assert sheets_sync.is_configured() is False


# ─── standings rows ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_standings_rows_shape(db_session: AsyncSession):
    comp = await _make_competition(db_session)
    await _make_eligible_entry(db_session, comp, 1)

    rows = await sheets_sync.build_standings_rows(db_session, comp)

    assert rows[0][0].startswith("World Cup 2026")
    header = next(r for r in rows if r and r[0] == "Rank")
    assert header == [
        "Rank",
        "Name - Entry",
        "No of Exact Scores",
        "Group Points",
        "Rarity Bonus Points",
        "Grp Stage Bonus Questions",
        "Total Grp Stage Points",
        "Knockout Pnts",
        "Knockout Bonus Points",
        "Grand Total",
    ]
    # One ranked data row for the single eligible entry. The test fixture
    # names its entry "Entry 1" which `_DEFAULT_ENTRY_NAME_RE` suppresses,
    # so col B shows just the user name.
    data = rows[rows.index(header) + 1:]
    assert len(data) == 1
    assert data[0][0] == "1"  # rank
    assert data[0][1] == "User 1"  # name only — auto-generated entry name dropped


# ─── sync_to_sheets orchestration ──────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_skips_when_not_configured(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(
        sheets_sync, "get_settings", lambda: _FakeSettings(google_sheet_id="")
    )
    comp = await _make_competition(db_session)
    assert await sheets_sync.sync_to_sheets(db_session, comp) is False


@pytest.mark.asyncio
async def test_sync_writes_both_tabs_every_tick(
    db_session: AsyncSession, monkeypatch
):
    """Standings + Predictions both refresh on every push — Predictions
    now carries live point cells alongside picks, so the once-per-process
    cache from v2.177.0 is no longer applicable.
    """
    monkeypatch.setattr(sheets_sync, "get_settings", lambda: _FakeSettings())
    fake = _FakeSpreadsheet()
    monkeypatch.setattr(sheets_sync, "_open_spreadsheet", lambda: fake)

    comp = await _make_competition(db_session)
    await _make_eligible_entry(db_session, comp, 1)

    ok = await sheets_sync.sync_to_sheets(db_session, comp)
    assert ok is True
    assert sheets_sync.STANDINGS_TAB in fake.tabs
    assert sheets_sync.PREDICTIONS_TAB in fake.tabs
    standings_first = fake.tabs[sheets_sync.STANDINGS_TAB].values
    predictions_first = fake.tabs[sheets_sync.PREDICTIONS_TAB].values
    assert standings_first is not None and predictions_first is not None
    # Both rectangles have uniform row widths.
    assert len({len(r) for r in standings_first}) == 1
    assert len({len(r) for r in predictions_first}) == 1

    # Reset both values and push again — both must re-render.
    fake.tabs[sheets_sync.STANDINGS_TAB].values = None
    fake.tabs[sheets_sync.PREDICTIONS_TAB].values = None
    ok2 = await sheets_sync.sync_to_sheets(db_session, comp)
    assert ok2 is True
    assert fake.tabs[sheets_sync.STANDINGS_TAB].values is not None
    assert fake.tabs[sheets_sync.PREDICTIONS_TAB].values is not None


@pytest.mark.asyncio
async def test_sync_accepts_and_ignores_legacy_kwargs(
    db_session: AsyncSession, monkeypatch
):
    """Old callers may still pass include_predictions / force_predictions;
    sync_to_sheets accepts and ignores them (backwards compatibility)."""
    monkeypatch.setattr(sheets_sync, "get_settings", lambda: _FakeSettings())
    fake = _FakeSpreadsheet()
    monkeypatch.setattr(sheets_sync, "_open_spreadsheet", lambda: fake)

    comp = await _make_competition(db_session)
    await _make_eligible_entry(db_session, comp, 1)

    ok = await sheets_sync.sync_to_sheets(
        db_session, comp, include_predictions=True, force_predictions=True
    )
    assert ok is True
    assert sheets_sync.PREDICTIONS_TAB in fake.tabs


@pytest.mark.asyncio
async def test_sync_never_raises_on_failure(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(sheets_sync, "get_settings", lambda: _FakeSettings())

    def _boom():
        raise RuntimeError("google down")

    monkeypatch.setattr(sheets_sync, "_open_spreadsheet", _boom)
    comp = await _make_competition(db_session)
    await _make_eligible_entry(db_session, comp, 1)

    # Returns False, does not propagate.
    assert await sheets_sync.sync_to_sheets(db_session, comp) is False
