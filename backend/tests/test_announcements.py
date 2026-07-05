"""Tests for the v2.165.0 dashboard announcements feature.

Pins:
* User feed returns only PUBLISHED announcements, newest first, capped.
* Admin list returns drafts too.
* Admin gate — non-admin gets 403 on every mutation (and the admin list).
* Create denormalizes the author name and writes an audit event.
* Patch updates only provided fields and audits the changed keys.
* Delete removes the row and audits.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register every model with metadata
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user
from app.main import app
from app.models.announcement import Announcement
from app.models.audit import AuditEvent
from app.models.user import AuthProvider, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _make_user(
    session: AsyncSession, *, email: str, name: str | None, is_admin: bool
) -> User:
    u = User(
        email=email,
        name=name,
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
        is_admin=is_admin,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    return await _make_user(
        db_session, email="admin@example.com", name="Matt Admin", is_admin=True
    )


@pytest_asyncio.fixture
async def normal_user(db_session: AsyncSession) -> User:
    return await _make_user(
        db_session, email="user@example.com", name="Norma User", is_admin=False
    )


@pytest_asyncio.fixture
async def client_as_admin(db_session: AsyncSession, admin_user: User):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_admin_user] = lambda: admin_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_as_user(db_session: AsyncSession, normal_user: User):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: normal_user
    # Do NOT override get_admin_user — the real dependency must 403.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _seed(
    session: AsyncSession, *, title: str, published: bool = True
) -> Announcement:
    a = Announcement(
        tag="Matchday",
        tone="gold",
        title=title,
        body=f"Body for {title}",
        author_name="Matt Admin",
        published=published,
    )
    session.add(a)
    await session.commit()
    await session.refresh(a)
    return a


# ---------------------------------------------------------------------------
# User feed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_feed_returns_published_newest_first(
    client_as_user: AsyncClient, db_session: AsyncSession
):
    await _seed(db_session, title="Oldest")
    await _seed(db_session, title="Hidden", published=False)
    await _seed(db_session, title="Newest")

    resp = await client_as_user.get("/api/announcements/")
    assert resp.status_code == 200
    # Response envelope: {hero_enabled: bool, items: [...]}
    titles = [a["title"] for a in resp.json()["items"]]
    assert titles == ["Newest", "Oldest"]  # unpublished excluded


@pytest.mark.asyncio
async def test_feed_is_capped(client_as_user: AsyncClient, db_session: AsyncSession):
    for i in range(15):
        await _seed(db_session, title=f"News {i}")
    resp = await client_as_user.get("/api/announcements/")
    assert resp.status_code == 200
    # Response envelope: {hero_enabled, items} — feed cap of 10 applies to items.
    assert len(resp.json()["items"]) == 10


# ---------------------------------------------------------------------------
# Admin gate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_non_admin_cannot_mutate(
    client_as_user: AsyncClient, db_session: AsyncSession
):
    existing = await _seed(db_session, title="Keep me")
    payload = {"tag": "Rules", "title": "Nope", "body": "Nope"}

    assert (await client_as_user.get("/api/admin/announcements/")).status_code == 403
    assert (
        await client_as_user.post("/api/admin/announcements/", json=payload)
    ).status_code == 403
    assert (
        await client_as_user.patch(
            f"/api/admin/announcements/{existing.id}", json={"title": "Hacked"}
        )
    ).status_code == 403
    assert (
        await client_as_user.delete(f"/api/admin/announcements/{existing.id}")
    ).status_code == 403


# ---------------------------------------------------------------------------
# Admin CRUD
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_list_includes_drafts(
    client_as_admin: AsyncClient, db_session: AsyncSession
):
    await _seed(db_session, title="Live one")
    await _seed(db_session, title="Draft one", published=False)
    resp = await client_as_admin.get("/api/admin/announcements/")
    assert resp.status_code == 200
    assert {a["title"] for a in resp.json()} == {"Live one", "Draft one"}


@pytest.mark.asyncio
async def test_create_denormalizes_author_and_audits(
    client_as_admin: AsyncClient, db_session: AsyncSession
):
    resp = await client_as_admin.post(
        "/api/admin/announcements/",
        json={
            "tag": "Prizes",
            "tone": "green",
            "title": "  Payouts done  ",
            "body": "All settled.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["author_name"] == "Matt Admin"
    assert data["title"] == "Payouts done"  # stripped
    assert data["published"] is True

    events = (
        (await db_session.execute(select(AuditEvent))).scalars().all()
    )
    assert [e.event_type for e in events] == ["announcement.created"]
    assert events[0].event_metadata["title"] == "Payouts done"


@pytest.mark.asyncio
async def test_create_rejects_unknown_tone(client_as_admin: AsyncClient):
    resp = await client_as_admin.post(
        "/api/admin/announcements/",
        json={"tag": "X", "tone": "neon", "title": "T", "body": "B"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_updates_only_given_fields(
    client_as_admin: AsyncClient, db_session: AsyncSession
):
    a = await _seed(db_session, title="Before")
    resp = await client_as_admin.patch(
        f"/api/admin/announcements/{a.id}", json={"published": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["published"] is False
    assert data["title"] == "Before"  # untouched

    events = (
        (await db_session.execute(select(AuditEvent))).scalars().all()
    )
    assert [e.event_type for e in events] == ["announcement.updated"]
    assert events[0].event_metadata["changed"] == ["published"]


@pytest.mark.asyncio
async def test_patch_missing_id_404s(client_as_admin: AsyncClient):
    resp = await client_as_admin.patch(
        "/api/admin/announcements/00000000-0000-0000-0000-000000000000",
        json={"title": "Ghost"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_row_and_audits(
    client_as_admin: AsyncClient, db_session: AsyncSession
):
    a = await _seed(db_session, title="Doomed")
    resp = await client_as_admin.delete(f"/api/admin/announcements/{a.id}")
    assert resp.status_code == 204

    remaining = (
        (await db_session.execute(select(Announcement))).scalars().all()
    )
    assert remaining == []
    events = (
        (await db_session.execute(select(AuditEvent))).scalars().all()
    )
    assert [e.event_type for e in events] == ["announcement.deleted"]
