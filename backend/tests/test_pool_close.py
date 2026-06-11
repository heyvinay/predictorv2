"""Close-the-pool tests (v2.166.0).

Archetypes:
* admin (no entries)            → exempt, never disabled
* submitter                     → kept
* withdrawn_submitter           → submitted entry was withdrawn → disabled
* draft_only                    → disabled (its phase row is DRAFT)
* no_entry                      → disabled
* already_inactive              → untouched (stays inactive, not re-counted)

Pins: preview counts, the disable run, admin exemption, pre-deadline
refusal (409), idempotency, audit event with user ids, 403 for
non-admins.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user
from app.main import app
from app.models._datetime import utc_now
from app.models.audit import AuditEvent
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services.pool_close import PoolCloseError, close_pool, preview_pool_close


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_competition(session: AsyncSession, *, deadline: datetime) -> Competition:
    comp = Competition(
        name="Test WC",
        external_id="WC",
        is_active=True,
        phase1_deadline=deadline,
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _make_user(
    session: AsyncSession,
    *,
    email: str,
    is_admin: bool = False,
    is_active: bool = True,
) -> User:
    u = User(
        email=email,
        name="T",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=is_active,
        is_admin=is_admin,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _add_entry(
    session: AsyncSession,
    *,
    user: User,
    competition: Competition,
    status: EntryStatus,
    withdrawn: bool = False,
    n: int = 1,
) -> PredictionEntry:
    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC-{user.email[:6]}-{n:03d}",
        display_name=f"Entry {n}",
        entry_number=n,
    )
    if withdrawn:
        entry.withdrawn_at = utc_now()
        entry.withdrawn_reason = "competition_started"
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    session.add(
        PredictionEntryPhase(
            entry_id=entry.id, phase=PredictionPhase.PHASE_1, status=status
        )
    )
    await session.commit()
    return entry


@pytest_asyncio.fixture
async def world(db_session: AsyncSession):
    """The six archetypes against a past-deadline competition."""
    comp = await _make_competition(
        db_session, deadline=utc_now() - timedelta(hours=1)
    )
    admin = await _make_user(db_session, email="admin@example.com", is_admin=True)
    submitter = await _make_user(db_session, email="submitter@example.com")
    await _add_entry(
        db_session, user=submitter, competition=comp, status=EntryStatus.SUBMITTED
    )
    withdrawn_submitter = await _make_user(db_session, email="wd@example.com")
    await _add_entry(
        db_session,
        user=withdrawn_submitter,
        competition=comp,
        status=EntryStatus.SUBMITTED,
        withdrawn=True,
    )
    draft_only = await _make_user(db_session, email="draft@example.com")
    await _add_entry(
        db_session,
        user=draft_only,
        competition=comp,
        status=EntryStatus.DRAFT,
        withdrawn=True,  # post-deadline state: the flip job withdrew it
    )
    no_entry = await _make_user(db_session, email="noentry@example.com")
    inactive = await _make_user(
        db_session, email="inactive@example.com", is_active=False
    )
    return {
        "comp": comp,
        "admin": admin,
        "submitter": submitter,
        "withdrawn_submitter": withdrawn_submitter,
        "draft_only": draft_only,
        "no_entry": no_entry,
        "inactive": inactive,
    }


# ---------------------------------------------------------------------------
# Service level
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_preview_counts(db_session: AsyncSession, world):
    p = await preview_pool_close(db_session, world["comp"])
    assert p.deadline_passed is True
    # withdrawn_submitter + draft_only + no_entry
    assert p.accounts_to_disable == 3
    assert p.submitters_kept == 1
    assert p.admins_exempt == 1
    assert p.already_inactive == 1
    assert p.drafts_withdrawn == 2  # both withdrawn entries carry the reason
    assert p.eligible_submitted_entries == 1


@pytest.mark.asyncio
async def test_close_disables_exactly_the_right_accounts(
    db_session: AsyncSession, world
):
    result = await close_pool(
        db_session, competition=world["comp"], admin=world["admin"]
    )
    assert result.disabled_count == 3
    expected = {
        world["withdrawn_submitter"].id,
        world["draft_only"].id,
        world["no_entry"].id,
    }
    assert set(result.disabled_user_ids) == expected

    for key, active in [
        ("admin", True),
        ("submitter", True),
        ("withdrawn_submitter", False),
        ("draft_only", False),
        ("no_entry", False),
    ]:
        await db_session.refresh(world[key])
        assert world[key].is_active is active, key

    events = (
        (
            await db_session.execute(
                select(AuditEvent).where(AuditEvent.event_type == "admin.pool_closed")
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].event_metadata["disabled_count"] == 3
    assert set(events[0].event_metadata["disabled_user_ids"]) == {
        str(uid) for uid in expected
    }


@pytest.mark.asyncio
async def test_close_is_idempotent(db_session: AsyncSession, world):
    first = await close_pool(
        db_session, competition=world["comp"], admin=world["admin"]
    )
    second = await close_pool(
        db_session, competition=world["comp"], admin=world["admin"]
    )
    assert first.disabled_count == 3
    assert second.disabled_count == 0


@pytest.mark.asyncio
async def test_close_refuses_before_deadline(db_session: AsyncSession):
    comp = await _make_competition(
        db_session, deadline=utc_now() + timedelta(hours=1)
    )
    admin = await _make_user(db_session, email="a@example.com", is_admin=True)
    with pytest.raises(PoolCloseError):
        await close_pool(db_session, competition=comp, admin=admin)


# ---------------------------------------------------------------------------
# HTTP level
# ---------------------------------------------------------------------------
def _client_as(db_session: AsyncSession, user: User, *, admin: bool):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    if admin:
        app.dependency_overrides[get_admin_user] = lambda: user
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_endpoints_happy_path(db_session: AsyncSession, world):
    async with _client_as(db_session, world["admin"], admin=True) as ac:
        preview = await ac.get("/api/admin/close-pool/preview")
        assert preview.status_code == 200
        assert preview.json()["accounts_to_disable"] == 3

        run = await ac.post("/api/admin/close-pool")
        assert run.status_code == 200
        assert run.json()["disabled_count"] == 3
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_endpoint_409_before_deadline(db_session: AsyncSession):
    await _make_competition(db_session, deadline=utc_now() + timedelta(hours=1))
    admin = await _make_user(db_session, email="a@example.com", is_admin=True)
    async with _client_as(db_session, admin, admin=True) as ac:
        run = await ac.post("/api/admin/close-pool")
        assert run.status_code == 409
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_endpoints_admin_gated(db_session: AsyncSession, world):
    async with _client_as(db_session, world["submitter"], admin=False) as ac:
        assert (await ac.get("/api/admin/close-pool/preview")).status_code == 403
        assert (await ac.post("/api/admin/close-pool")).status_code == 403
    app.dependency_overrides.clear()
