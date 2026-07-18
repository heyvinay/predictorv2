"""Final podium + Trionda side prize (Plan A)."""

from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register all tables
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user
from app.main import app
from app.models.competition import Competition
from app.models.user import AuthProvider, User
from app.services.group_stage_winner import group_stage_total
from app.services.tournament_champion import pick_trionda_recipient


class _Phase1:
    match_outcome_points = 100
    exact_score_points = 40
    hybrid_bonus_points = 7


class _Breakdown:
    phase1 = _Phase1()


class _Entry:
    breakdown = _Breakdown()
    bonus_group_points = 10


def test_group_stage_total_is_shared_and_stable():
    assert group_stage_total(_Entry()) == 157


@dataclass
class _Row:
    entry_id: str
    user_name: str
    position: int
    total_points: int
    gs_total: int


def _rows(*specs):
    # specs: (entry_id, position, total, gs_total)
    return [
        _Row(entry_id=e, user_name=e.upper(), position=p, total_points=t, gs_total=g)
        for (e, p, t, g) in specs
    ]


def test_trionda_direct_runner_up_eligible():
    rows = _rows(("champ", 1, 612, 348), ("kevin", 2, 598, 340), ("john", 3, 587, 341))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "kevin"
    assert out.requires_draw is False
    assert out.reason == "runner-up on total points"


def test_trionda_skips_group_stage_cash_winner():
    # kevin at #2 also holds the max group-stage total → ineligible, ball walks to #3
    rows = _rows(("champ", 1, 612, 348), ("kevin", 2, 598, 356), ("john", 3, 587, 341))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "john"
    assert "not eligible" in out.reason


def test_trionda_shared_gs_cash_both_skipped():
    # champ and kevin SHARE max gs_total (tie) → both ineligible; champ is champion anyway
    rows = _rows(("champ", 1, 612, 356), ("kevin", 2, 598, 356), ("john", 3, 587, 341))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "john"


def test_trionda_rank_tie_breaks_on_group_stage_points():
    rows = _rows(
        ("champ", 1, 612, 356),
        ("a", 2, 598, 330),
        ("b", 2, 598, 345),  # same rank, more gs points → b gets the ball
    )
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "b"
    assert out.requires_draw is False


def test_trionda_persisting_tie_requires_draw():
    rows = _rows(
        ("champ", 1, 612, 356),
        ("a", 2, 598, 330),
        ("b", 2, 598, 330),
    )
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.requires_draw is True
    assert {c.entry_id for c in out.draw_candidates} == {"a", "b"}
    assert out.recipient is None


def test_trionda_shared_champions_shift_runner_up_rank():
    # two joint champions at position 1 → runner-up rank is position 2
    rows = _rows(("c1", 1, 612, 356), ("c2", 1, 612, 340), ("a", 2, 598, 330))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "a"


# ---------------------------------------------------------------------------
# GET /leaderboard/final-podium — access-gate tests (Task A5)
# ---------------------------------------------------------------------------
# These fixtures didn't exist in this file yet (A3/A4 only added pure
# service-level unit tests above) — added here, copied from the
# client_as_admin pattern in test_tournament_conclusion.py, plus a new
# client_anonymous fixture per the A5 plan.


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
    comp = Competition(name="WC26", is_active=True)
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    u = User(
        email="admin@example.com",
        name="Admin",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
        is_admin=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


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
async def client_anonymous(db_session: AsyncSession):
    """Same AsyncClient shape as client_as_admin, but ONLY get_session is
    overridden — no user/admin override — so the real
    get_current_user_optional dependency runs and yields None for an
    unauthenticated request (no Authorization header sent)."""

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_final_podium_hidden_pre_conclusion_for_anonymous(
    client_anonymous, competition
):
    resp = await client_anonymous.get("/api/leaderboard/final-podium")
    assert resp.status_code == 200
    assert resp.json() is None  # gate: not concluded, not admin → None


@pytest.mark.asyncio
async def test_final_podium_admin_preview_pre_conclusion(client_as_admin, competition):
    resp = await client_as_admin.get("/api/leaderboard/final-podium")
    assert resp.status_code == 200
    # empty DB → service returns None; the point is the gate didn't block
