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
from app.dependencies import get_admin_user, get_current_user, get_current_user_optional
from app.main import app
from app.models.competition import Competition
from app.models.user import AuthProvider, User
from app.services.group_stage_winner import group_stage_total
from app.services.tournament_champion import TriondaResult, pick_trionda_recipient


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
async def regular_user(db_session: AsyncSession) -> User:
    u = User(
        email="user@example.com",
        name="Regular",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=True,
        is_admin=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def client_as_admin(db_session: AsyncSession, admin_user: User):
    """Overrides get_current_user / get_admin_user (used by routes that
    depend on CurrentUser/AdminUser directly) AND get_current_user_optional
    directly.

    The latter override is the one that actually matters for
    GET /leaderboard/final-podium: that route depends on OptionalUser
    (Depends(get_current_user_optional)), and get_current_user_optional
    checks for a bearer token FIRST — if no token is present it returns
    None immediately, calling get_current_user as a plain nested function
    call rather than through Depends(). That means overriding
    get_current_user/get_admin_user alone (the original version of this
    fixture) never reaches this route's dependency at all when no
    Authorization header is sent — it silently behaved identically to
    client_anonymous for this endpoint. Overriding get_current_user_optional
    directly is what makes the admin user genuinely arrive through the real
    code path this route resolves.
    """

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_admin_user] = lambda: admin_user
    app.dependency_overrides[get_current_user_optional] = lambda: admin_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_as_user(db_session: AsyncSession, regular_user: User):
    """Authenticated but NON-admin — overrides get_current_user_optional
    directly (same reasoning as client_as_admin) so
    GET /leaderboard/final-podium genuinely receives a real, non-admin User
    instance through its actual dependency, exercising the
    `not (user and user.is_admin)` branch with a truthy-but-non-admin user
    rather than either None (client_anonymous) or an admin (client_as_admin).
    """

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: regular_user
    app.dependency_overrides[get_current_user_optional] = lambda: regular_user
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


def _fake_podium_payload() -> dict:
    """A real, complete get_final_podium()-shaped payload — used only so the
    gate tests below can tell "blocked → None" apart from "let through →
    real content" apart. Against an EMPTY database, get_final_podium()
    itself already returns None (no leaderboard rows), which means a naive
    gate test asserting only `resp.json() is None` passes whether the gate
    blocked correctly OR the admin bypass is silently broken — exactly the
    false-positive this file previously shipped with. Stubbing a non-None
    payload closes that hole: "let through" must now produce THIS content,
    not just any 200/None response.
    """
    return {
        "entries": [
            {
                "entry_id": "e1",
                "user_name": "Champ",
                "entry_name": "Champ Entry",
                "final_rank": 1,
                "total_points": 500,
                "group_points": 200,
                "knockout_points": 250,
                "bonus_points": 30,
                "exact_scores": 5,
                "rarity_points": 10,
                "days_at_top": 12,
                "champion_pick": "Brazil",
                "champion_hit": True,
                "is_champion": True,
            }
        ],
        "trionda": TriondaResult(None, "not enough entries"),
        "story_line": "Champ takes the title by a mile.",
        "total_days": 20,
    }


@pytest_asyncio.fixture
async def stub_final_podium(monkeypatch):
    """Patches app.services.tournament_champion.get_final_podium to return
    a real, non-None payload instead of hitting the DB. The endpoint does
    `from app.services.tournament_champion import get_final_podium` INSIDE
    the function body on every call, so it re-reads the attribute off the
    already-imported module object each request — monkeypatch.setattr on
    that same module object is what the endpoint actually sees."""

    async def fake(session):
        return _fake_podium_payload()

    import app.services.tournament_champion as tc_service

    monkeypatch.setattr(tc_service, "get_final_podium", fake)


@pytest.mark.asyncio
async def test_final_podium_hidden_pre_conclusion_for_anonymous(
    client_anonymous, competition, stub_final_podium
):
    resp = await client_anonymous.get("/api/leaderboard/final-podium")
    assert resp.status_code == 200
    # Real content is available (stubbed) — None here proves the gate
    # itself blocked the anonymous request, not that the DB was empty.
    assert resp.json() is None


@pytest.mark.asyncio
async def test_final_podium_admin_preview_pre_conclusion(
    client_as_admin, competition, stub_final_podium
):
    resp = await client_as_admin.get("/api/leaderboard/final-podium")
    assert resp.status_code == 200
    body = resp.json()
    # A real payload — not just a 200/None — proves an admin User genuinely
    # reached the endpoint's `user` parameter through get_current_user_optional
    # (the actual dependency this route resolves) and the
    # `not (user and user.is_admin)` branch evaluated to False, bypassing
    # the block. client_as_admin overrides get_current_user_optional
    # directly for this reason — overriding only get_current_user/
    # get_admin_user (as this fixture originally did) never reaches this
    # route at all when no bearer token is sent, since
    # get_current_user_optional short-circuits to None on `token is None`
    # BEFORE ever calling get_current_user, which it invokes as a plain
    # function call rather than through Depends().
    assert body is not None
    assert body["entries"][0]["user_name"] == "Champ"
    assert body["story_line"] == "Champ takes the title by a mile."


@pytest.mark.asyncio
async def test_final_podium_hidden_pre_conclusion_for_authenticated_non_admin(
    client_as_user, competition, stub_final_podium
):
    """Authenticated-but-not-privileged case: a real, non-admin User reaches
    the route (proving client_as_user isn't just a no-token no-op like
    client_anonymous), yet the gate still blocks pre-conclusion — real
    content is available (stubbed) but withheld. Pins the
    `not (user and user.is_admin)` parenthesization: the easy bug to
    introduce is `(not user) and user.is_admin`, which for a truthy
    non-admin user evaluates to False and would incorrectly let the
    request through to the stubbed (non-None) payload.
    """
    resp = await client_as_user.get("/api/leaderboard/final-podium")
    assert resp.status_code == 200
    assert resp.json() is None
