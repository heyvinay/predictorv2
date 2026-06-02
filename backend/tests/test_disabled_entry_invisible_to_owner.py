"""Regression tests for the "ghost mode" disable contract.

When an admin disables a `PredictionEntry`, that entry must become
invisible to its owner across every read surface — list, detail,
predictions, leaderboard snapshots and breakdown. The action is
reversible: re-enable restores full visibility, including any
historical snapshot rows preserved on disk.

These tests also pin the blind-pool semantics that surround the change.
The visibility check in `services.entries.check_entry_visibility` runs
its branches in this order:
  1. Admin bypass (unconditional — admins always see).
  2. Owner branch — return unless their own entry is disabled / withdrawn.
  3. Disabled / withdrawn check for any non-owner.
  4. Blind pool check (`is_phase1_locked`).
Reordering would either re-open a peek-window (blind-pool moved too
late) or lock owners out of their own active entries (owner branch
moved too late). The "regression" tests at the bottom of this file
prevent both.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models
from app.database import get_session
from app.dependencies import (
    get_admin_user,
    get_current_user,
    get_current_user_optional,
)
from app.main import app
from app.models.competition import Competition
from app.models.entry import (
    EntryStatus,
    PredictionEntry,
    PredictionEntryPhase,
)
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services import leaderboard as leaderboard_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clear_leaderboard_cache():
    leaderboard_service.invalidate_cache()
    yield
    leaderboard_service.invalidate_cache()


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
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


@pytest_asyncio.fixture
async def alice(db_session: AsyncSession) -> User:
    u = User(
        email="alice@example.com",
        name="Alice",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def bob(db_session: AsyncSession) -> User:
    u = User(
        email="bob@example.com",
        name="Bob",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    u = User(
        email="admin@example.com",
        name="Admin",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_admin=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _make_entry(
    session: AsyncSession,
    *,
    user: User,
    competition: Competition,
    display_name: str,
    is_disabled: bool = False,
    status: EntryStatus = EntryStatus.SUBMITTED,
    entry_number: int | None = None,
) -> PredictionEntry:
    # Pass `entry_number` explicitly when creating multiple entries for
    # the same user; otherwise the unique (competition_id, user_id,
    # entry_number) constraint fires. Default to a random non-colliding
    # number when not specified.
    if entry_number is None:
        entry_number = uuid.uuid4().int % 1_000_000 + 1
    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6].upper()}",
        display_name=display_name,
        entry_number=entry_number,
        is_disabled=is_disabled,
        disabled_reason="Test entry cleanup" if is_disabled else None,
        disabled_at=datetime(2026, 6, 1, tzinfo=timezone.utc) if is_disabled else None,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    for phase in (PredictionPhase.PHASE_1, PredictionPhase.PHASE_2):
        session.add(
            PredictionEntryPhase(entry_id=entry.id, phase=phase, status=status)
        )
    await session.commit()
    await session.refresh(entry)
    return entry


def _set_phase1_locked(competition: Competition, *, locked: bool) -> None:
    if locked:
        competition.phase1_deadline = datetime(2020, 1, 1, tzinfo=timezone.utc)
    else:
        competition.phase1_deadline = datetime(2099, 1, 1, tzinfo=timezone.utc)


def _override(
    db_session: AsyncSession,
    *,
    viewer: User | None,
    admin: User | None = None,
):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    if viewer is not None:
        app.dependency_overrides[get_current_user] = lambda: viewer
        app.dependency_overrides[get_current_user_optional] = lambda: viewer
    else:
        app.dependency_overrides[get_current_user_optional] = lambda: None
    if admin is not None:
        app.dependency_overrides[get_admin_user] = lambda: admin


# ---------------------------------------------------------------------------
# Owner-facing ghost-mode contract
# ---------------------------------------------------------------------------
class TestOwnerSeesNothing:
    """Disable means "as if the entry never existed" for the owner."""

    async def test_list_excludes_disabled(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        """GET /api/entries — owner sees an empty list (Gap 1)."""
        await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Test entry",
            is_disabled=True,
        )
        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/entries")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json() == []

    async def test_list_includes_active_alongside_disabled(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        """The filter must be surgical — an active entry alongside the disabled
        one is still returned to the owner."""
        await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Disabled",
            is_disabled=True,
        )
        keep = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Active",
        )
        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/entries")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()]
        assert ids == [str(keep.id)]

    async def test_detail_blocked(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        """GET /api/entries/{id} — owner is blocked on their own disabled
        entry (Gap 3). EntryAccessDeniedError maps to 403; ghost-mode
        intent is unchanged regardless of the specific 4xx code."""
        entry = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Disabled",
            is_disabled=True,
        )
        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/entries/{entry.id}")
        app.dependency_overrides.clear()
        assert r.status_code == 403

    async def test_predictions_matches_blocked(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        """GET /api/entries/{id}/predictions/matches — owner blocked (Gap 4)."""
        entry = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Disabled",
            is_disabled=True,
        )
        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/entries/{entry.id}/predictions/matches")
        app.dependency_overrides.clear()
        assert r.status_code == 403

    async def test_predictions_bracket_blocked(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        """GET /api/entries/{id}/predictions/bracket — owner blocked (Gap 4)."""
        entry = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Disabled",
            is_disabled=True,
        )
        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/entries/{entry.id}/predictions/bracket")
        app.dependency_overrides.clear()
        assert r.status_code == 403

    async def test_predictions_bonus_blocked(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        """GET /api/entries/{id}/predictions/bonus — owner blocked (Gap 4)."""
        entry = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Disabled",
            is_disabled=True,
        )
        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/entries/{entry.id}/predictions/bonus")
        app.dependency_overrides.clear()
        assert r.status_code == 403

    async def test_leaderboard_snapshot_blocked(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        """GET /api/leaderboard/snapshots/{id} — owner blocked (Gap 3, via
        the existing get_entry_for_view call in the route)."""
        entry = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Disabled",
            is_disabled=True,
        )
        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/leaderboard/snapshots/{entry.id}")
        app.dependency_overrides.clear()
        assert r.status_code == 403

    async def test_leaderboard_breakdown_blocked(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        """GET /api/leaderboard/breakdown/{id} — owner blocked (Gap 3)."""
        entry = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Disabled",
            is_disabled=True,
        )
        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/leaderboard/breakdown/{entry.id}")
        app.dependency_overrides.clear()
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Admin still sees everything
# ---------------------------------------------------------------------------
class TestAdminBypass:
    async def test_admin_detail_pre_lock(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
        admin_user: User,
    ):
        """Admin always sees disabled entries — required for forensics."""
        entry = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Disabled",
            is_disabled=True,
        )
        _set_phase1_locked(competition, locked=False)
        db_session.add(competition)
        await db_session.commit()

        _override(db_session, viewer=admin_user, admin=admin_user)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/entries/{entry.id}")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["is_disabled"] is True


# ---------------------------------------------------------------------------
# Blind-pool regression — these MUST stay green to confirm the visibility
# check didn't loosen the public lock or tighten owners out of active entries.
# ---------------------------------------------------------------------------
class TestBlindPoolRegression:
    async def test_pre_lock_non_owner_blocked_on_active_entry(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
        bob: User,
    ):
        """Pre-deadline, a non-owner cannot read someone else's *active*
        entry — pins the blind-pool gate against accidental loosening."""
        entry = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Active",
        )
        _set_phase1_locked(competition, locked=False)
        db_session.add(competition)
        await db_session.commit()

        _override(db_session, viewer=bob)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/leaderboard/breakdown/{entry.id}")
        app.dependency_overrides.clear()
        assert r.status_code == 403

    async def test_pre_lock_owner_allowed_on_active_entry(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        """Pre-deadline, the owner CAN still read their own *active* entry —
        pins the owner branch against accidentally tightening it onto
        non-disabled entries (e.g. by hoisting the disabled check too high)."""
        entry = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Active",
        )
        _set_phase1_locked(competition, locked=False)
        db_session.add(competition)
        await db_session.commit()

        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/leaderboard/breakdown/{entry.id}")
        app.dependency_overrides.clear()
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Reversibility — re-enable restores everything intact.
# ---------------------------------------------------------------------------
class TestReversibility:
    async def test_reenable_restores_owner_visibility(
        self,
        db_session: AsyncSession,
        competition: Competition,
        alice: User,
    ):
        """Toggle is_disabled back to false → owner sees the entry again,
        same id, same predictions/snapshots (unmodified rows on disk)."""
        entry = await _make_entry(
            db_session,
            user=alice,
            competition=competition,
            display_name="Came back",
            is_disabled=True,
        )

        # Confirm initially hidden.
        _override(db_session, viewer=alice)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/entries")
            assert r.status_code == 200
            assert r.json() == []

        # Admin re-enables (in this test we just flip the column directly —
        # the dedicated admin_enable_entry path is covered by service tests).
        entry.is_disabled = False
        entry.disabled_reason = None
        entry.disabled_at = None
        db_session.add(entry)
        await db_session.commit()

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/entries")
            assert r.status_code == 200
            ids = [e["id"] for e in r.json()]
            assert ids == [str(entry.id)]

            r2 = await ac.get(f"/api/entries/{entry.id}")
            assert r2.status_code == 200
        app.dependency_overrides.clear()
