"""What-if bracket simulator bulk endpoint + gating layer.

`GET /api/simulator/bracket-picks` returns every eligible entry's full
knockout picks + frozen group points + current total/position in one
response, powering a client-side leaderboard re-rank.

Gating: an admin master switch per competition
(`Competition.simulator_enabled`). Admins always bypass it and retain
full access even when it's off. There is no per-user unlock or daily
run cap.

HTTP-level tests via ASGITransport, mirroring test_leaderboard_admin_gate.py.
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
from app.dependencies import get_current_user, get_current_user_optional
from app.main import app
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.user import AuthProvider, User
from app.services import leaderboard as leaderboard_service


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
        phase1_deadline=datetime(2020, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
        # Gating (v2.194.x): the master switch defaults to True here so
        # the pre-existing bracket-picks tests (which predate gating)
        # keep exercising the endpoint without every one of them having
        # to flip it on individually. Dedicated gating tests below build
        # their own disabled-feature scenarios.
        simulator_enabled=True,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


@pytest_asyncio.fixture
async def viewer(db_session: AsyncSession) -> User:
    u = User(
        email="viewer@example.com",
        name="Viewer",
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
    db_session: AsyncSession,
    competition: Competition,
    *,
    email: str,
    entry_number: int = 1,
    submitted: bool = True,
    withdrawn: bool = False,
    disabled: bool = False,
) -> PredictionEntry:
    user = User(
        email=email,
        name=email.split("@")[0].title(),
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6].upper()}",
        display_name=f"{user.name}'s Entry",
        entry_number=entry_number,
        is_disabled=disabled,
        withdrawn_at=datetime(2026, 1, 1, tzinfo=timezone.utc) if withdrawn else None,
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    db_session.add(
        PredictionEntryPhase(
            entry_id=entry.id,
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.SUBMITTED if submitted else EntryStatus.DRAFT,
        )
    )
    await db_session.commit()
    return entry


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


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


async def test_unauthenticated_gets_401(db_session: AsyncSession, client: AsyncClient):
    _override(db_session, viewer=None)
    r = await client.get("/api/simulator/bracket-picks")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Response shape + eligibility
# ---------------------------------------------------------------------------


async def test_response_shape_and_plural_fields(
    db_session: AsyncSession, competition: Competition, viewer: User, client: AsyncClient
):
    entry = await _make_entry(db_session, competition, email="alice@example.com")
    db_session.add_all(
        [
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="round_of_32"),
            TeamPrediction(entry_id=entry.id, team="France", stage="round_of_32"),
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="round_of_16"),
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="quarter_final"),
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="semi_final"),
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="final"),
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="winner"),
        ]
    )
    await db_session.commit()

    _override(db_session, viewer=viewer)
    r = await client.get("/api/simulator/bracket-picks")
    assert r.status_code == 200
    body = r.json()

    assert "entries" in body
    assert "last_calculated" in body
    assert len(body["entries"]) == 1

    row = body["entries"][0]
    for key in (
        "entry_id",
        "entry_name",
        "user_id",
        "user_name",
        "position",
        "total_points",
        "group_points",
        "bonus_knockout_points",
        "picks",
    ):
        assert key in row

    picks = row["picks"]
    # Plural QF/SF field names — matches BracketPrediction API convention.
    assert picks["quarter_finals"] == ["Brazil"]
    assert picks["semi_finals"] == ["Brazil"]
    assert sorted(picks["round_of_32"]) == ["Brazil", "France"]
    assert picks["round_of_16"] == ["Brazil"]
    assert picks["final"] == ["Brazil"]
    assert picks["winner"] == "Brazil"


async def test_winner_is_none_when_no_pick(
    db_session: AsyncSession, competition: Competition, viewer: User, client: AsyncClient
):
    await _make_entry(db_session, competition, email="alice@example.com")

    _override(db_session, viewer=viewer)
    r = await client.get("/api/simulator/bracket-picks")
    assert r.status_code == 200
    body = r.json()
    assert len(body["entries"]) == 1
    row = body["entries"][0]
    assert row["picks"]["winner"] is None
    assert row["picks"]["round_of_32"] == []


async def test_draft_entry_excluded(
    db_session: AsyncSession, competition: Competition, viewer: User, client: AsyncClient
):
    await _make_entry(db_session, competition, email="draft@example.com", submitted=False)
    submitted_entry = await _make_entry(
        db_session, competition, email="submitted@example.com"
    )

    _override(db_session, viewer=viewer)
    r = await client.get("/api/simulator/bracket-picks")
    assert r.status_code == 200
    body = r.json()
    entry_ids = {e["entry_id"] for e in body["entries"]}
    assert entry_ids == {str(submitted_entry.id)}


async def test_withdrawn_entry_excluded(
    db_session: AsyncSession, competition: Competition, viewer: User, client: AsyncClient
):
    await _make_entry(
        db_session, competition, email="withdrawn@example.com", withdrawn=True
    )
    kept = await _make_entry(db_session, competition, email="kept@example.com")

    _override(db_session, viewer=viewer)
    r = await client.get("/api/simulator/bracket-picks")
    assert r.status_code == 200
    body = r.json()
    entry_ids = {e["entry_id"] for e in body["entries"]}
    assert entry_ids == {str(kept.id)}


async def test_disabled_entry_excluded(
    db_session: AsyncSession, competition: Competition, viewer: User, client: AsyncClient
):
    await _make_entry(
        db_session, competition, email="disabled@example.com", disabled=True
    )
    kept = await _make_entry(db_session, competition, email="kept2@example.com")

    _override(db_session, viewer=viewer)
    r = await client.get("/api/simulator/bracket-picks")
    assert r.status_code == 200
    body = r.json()
    entry_ids = {e["entry_id"] for e in body["entries"]}
    assert entry_ids == {str(kept.id)}


async def test_phase2_team_predictions_ignored(
    db_session: AsyncSession, competition: Competition, viewer: User, client: AsyncClient
):
    entry = await _make_entry(db_session, competition, email="alice@example.com")
    db_session.add_all(
        [
            TeamPrediction(entry_id=entry.id, team="Brazil", stage="winner"),
            # Dormant phase_2 row must never leak into the simulator response.
            TeamPrediction(
                entry_id=entry.id,
                team="Germany",
                stage="winner",
                phase=PredictionPhase.PHASE_2,
            ),
        ]
    )
    await db_session.commit()

    _override(db_session, viewer=viewer)
    r = await client.get("/api/simulator/bracket-picks")
    assert r.status_code == 200
    row = r.json()["entries"][0]
    assert row["picks"]["winner"] == "Brazil"


async def test_group_points_and_totals_populated(
    db_session: AsyncSession, competition: Competition, viewer: User, client: AsyncClient
):
    await _make_entry(db_session, competition, email="alice@example.com")

    _override(db_session, viewer=viewer)
    r = await client.get("/api/simulator/bracket-picks")
    assert r.status_code == 200
    row = r.json()["entries"][0]
    # No fixtures/scores in this test → zero points, but fields must be
    # present and numeric (not None) so the frontend re-rank has a stable
    # base to add hypothetical knockout points onto.
    assert isinstance(row["group_points"], int)
    assert isinstance(row["bonus_knockout_points"], int)
    assert isinstance(row["total_points"], int)
    assert isinstance(row["position"], int)
    assert row["position"] >= 1


# ---------------------------------------------------------------------------
# Gating — admin master switch only
# ---------------------------------------------------------------------------


async def test_non_admin_can_use_simulator_freely_when_enabled(
    db_session: AsyncSession, competition: Competition, viewer: User, client: AsyncClient
):
    """No unlock, no daily cap — a plain non-admin user can hit /run and
    /bracket-picks repeatedly the moment the competition's master switch
    is on. Positive-path proof that the gate and run limit are gone."""
    _override(db_session, viewer=viewer)

    for _ in range(5):
        r = await client.post("/api/simulator/run")
        assert r.status_code == 200

    picks_r = await client.get("/api/simulator/bracket-picks")
    assert picks_r.status_code == 200

    status_r = await client.get("/api/simulator/status")
    assert status_r.status_code == 200
    assert status_r.json() == {"feature_enabled": True, "is_admin": False}


async def test_admin_bypasses_master_switch_when_feature_disabled(
    db_session: AsyncSession, admin_user: User, client: AsyncClient
):
    comp = Competition(
        name="Test World Cup",
        external_id="WC",
        is_active=True,
        phase1_deadline=datetime(2020, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
        simulator_enabled=False,  # master switch OFF
    )
    db_session.add(comp)
    await db_session.commit()

    _override(db_session, viewer=admin_user)

    status_r = await client.get("/api/simulator/status")
    assert status_r.status_code == 200
    assert status_r.json() == {"feature_enabled": False, "is_admin": True}

    r = await client.post("/api/simulator/run")
    assert r.status_code == 200

    # bracket-picks reachable too, despite simulator_enabled=False.
    picks_r = await client.get("/api/simulator/bracket-picks")
    assert picks_r.status_code == 200


async def test_non_admin_blocked_from_every_interactive_route_when_feature_disabled(
    db_session: AsyncSession, viewer: User, client: AsyncClient
):
    # With the master switch off, a non-admin must be 403'd on every
    # interactive route — run and bracket-picks — so they can't touch the
    # simulator at all. Only /status stays reachable.
    comp = Competition(
        name="Test World Cup",
        external_id="WC",
        is_active=True,
        phase1_deadline=datetime(2020, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
        simulator_enabled=False,
    )
    db_session.add(comp)
    await db_session.commit()

    _override(db_session, viewer=viewer)

    picks_r = await client.get("/api/simulator/bracket-picks")
    assert picks_r.status_code == 403

    run_r = await client.post("/api/simulator/run")
    assert run_r.status_code == 403

    # /status MUST stay reachable — it's how the frontend learns the
    # feature is off and hides the simulator UI.
    status_r = await client.get("/api/simulator/status")
    assert status_r.status_code == 200
    assert status_r.json()["feature_enabled"] is False
