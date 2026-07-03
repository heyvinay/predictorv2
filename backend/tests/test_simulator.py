"""What-if bracket simulator bulk endpoint + gating layer.

`GET /api/simulator/bracket-picks` returns every eligible entry's full
knockout picks + frozen group points + current total/position in one
response, powering a client-side leaderboard re-rank.

Gating (v2.194.x): a one-time trivia unlock (permanent per user), a
daily cap of 3 committed runs, and an admin master switch. Admins
bypass the unlock + cap entirely and retain full access even when the
master switch is off; admin usage is still counted + audited.

HTTP-level tests via ASGITransport, mirroring test_leaderboard_admin_gate.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

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
from app.services.simulator import (
    CHALLENGE_TIME_LIMIT_MS,
    SIMULATOR_DAILY_CAP,
    _TRIVIA_QUESTIONS,
    get_challenge_question,
)


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
        # Gating (v2.194.x): pre-unlocked so the pre-existing bracket-picks
        # tests (which predate gating) keep exercising the endpoint.
        # Dedicated gating tests below build their own locked users.
        simulator_unlocked=True,
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


@pytest_asyncio.fixture
async def locked_user(db_session: AsyncSession) -> User:
    """A plain, non-admin user who has NOT completed the trivia unlock."""
    u = User(
        email="locked@example.com",
        name="Locked",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
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
    assert isinstance(row["total_points"], int)
    assert isinstance(row["position"], int)
    assert row["position"] >= 1


# ---------------------------------------------------------------------------
# Gating (v2.194.x) — trivia unlock, daily cap, admin master switch
# ---------------------------------------------------------------------------


def _correct_attempt_payload(user: User) -> dict:
    """Build a correct-answer ChallengeAttempt body for whatever question
    `get_challenge_question` deterministically serves this user right now."""
    q = get_challenge_question(user)
    correct = next(tq for tq in _TRIVIA_QUESTIONS if tq["id"] == q.question_id)
    return {
        "question_id": q.question_id,
        "answer_index": correct["correct_index"],
        "elapsed_ms": 1000,
    }


async def test_challenge_get_never_includes_answer(
    db_session: AsyncSession, competition: Competition, locked_user: User, client: AsyncClient
):
    _override(db_session, viewer=locked_user)
    r = await client.get("/api/simulator/challenge")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"question_id", "question", "options"}
    assert len(body["options"]) == 4


async def test_fifty_fifty_returns_two_wrong_indexes_only(
    db_session: AsyncSession, competition: Competition, locked_user: User, client: AsyncClient
):
    """The 50:50 lifeline endpoint returns exactly two option indexes,
    both provably NOT the correct one — otherwise the classic Millionaire
    mechanic would be broken. `correct_index` must never appear in the
    wrong_indexes list, and there must always be two."""
    _override(db_session, viewer=locked_user)
    q = get_challenge_question(locked_user)
    correct = next(tq for tq in _TRIVIA_QUESTIONS if tq["id"] == q.question_id)

    r = await client.post(
        "/api/simulator/challenge/fifty-fifty",
        json={"question_id": q.question_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"wrong_indexes"}
    assert len(body["wrong_indexes"]) == 2
    assert correct["correct_index"] not in body["wrong_indexes"]
    # Indexes must be distinct and valid for the 4-option shape.
    assert len(set(body["wrong_indexes"])) == 2
    assert all(0 <= idx < len(correct["options"]) for idx in body["wrong_indexes"])


async def test_fifty_fifty_404_on_unknown_question(
    db_session: AsyncSession, competition: Competition, locked_user: User, client: AsyncClient
):
    _override(db_session, viewer=locked_user)
    r = await client.post(
        "/api/simulator/challenge/fifty-fifty",
        json={"question_id": "does-not-exist"},
    )
    assert r.status_code == 404


async def test_unlock_succeeds_on_correct_answer_within_time(
    db_session: AsyncSession, competition: Competition, locked_user: User, client: AsyncClient
):
    _override(db_session, viewer=locked_user)
    payload = _correct_attempt_payload(locked_user)
    r = await client.post("/api/simulator/challenge", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["unlocked"] is True
    assert body["status"]["unlocked"] is True

    await db_session.refresh(locked_user)
    assert locked_user.simulator_unlocked is True


async def test_unlock_fails_on_wrong_answer(
    db_session: AsyncSession, competition: Competition, locked_user: User, client: AsyncClient
):
    _override(db_session, viewer=locked_user)
    q = get_challenge_question(locked_user)
    correct = next(tq for tq in _TRIVIA_QUESTIONS if tq["id"] == q.question_id)
    wrong_index = (correct["correct_index"] + 1) % len(correct["options"])

    r = await client.post(
        "/api/simulator/challenge",
        json={
            "question_id": q.question_id,
            "answer_index": wrong_index,
            "elapsed_ms": 1000,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["unlocked"] is False
    assert body["status"]["unlocked"] is False

    await db_session.refresh(locked_user)
    assert locked_user.simulator_unlocked is False


async def test_unlock_fails_when_over_time_limit(
    db_session: AsyncSession, competition: Competition, locked_user: User, client: AsyncClient
):
    _override(db_session, viewer=locked_user)
    payload = _correct_attempt_payload(locked_user)
    payload["elapsed_ms"] = CHALLENGE_TIME_LIMIT_MS + 1

    r = await client.post("/api/simulator/challenge", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["unlocked"] is False

    await db_session.refresh(locked_user)
    assert locked_user.simulator_unlocked is False


async def test_unlock_allows_unlimited_attempts_no_lockout(
    db_session: AsyncSession, competition: Competition, locked_user: User, client: AsyncClient
):
    _override(db_session, viewer=locked_user)
    q = get_challenge_question(locked_user)
    correct = next(tq for tq in _TRIVIA_QUESTIONS if tq["id"] == q.question_id)
    wrong_index = (correct["correct_index"] + 1) % len(correct["options"])

    # Multiple wrong attempts should never lock the user out of trying again.
    for _ in range(3):
        r = await client.post(
            "/api/simulator/challenge",
            json={
                "question_id": q.question_id,
                "answer_index": wrong_index,
                "elapsed_ms": 1000,
            },
        )
        assert r.status_code == 200
        assert r.json()["unlocked"] is False

    # A subsequent correct attempt still succeeds.
    payload = _correct_attempt_payload(locked_user)
    r = await client.post("/api/simulator/challenge", json=payload)
    assert r.status_code == 200
    assert r.json()["unlocked"] is True


async def test_daily_reset_when_reset_at_is_yesterday(
    db_session: AsyncSession, competition: Competition, viewer: User, client: AsyncClient
):
    viewer.simulator_runs_used = SIMULATOR_DAILY_CAP
    viewer.simulator_runs_reset_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add(viewer)
    await db_session.commit()

    _override(db_session, viewer=viewer)
    r = await client.get("/api/simulator/status")
    assert r.status_code == 200
    body = r.json()
    assert body["runs_used"] == 0
    assert body["runs_remaining"] == SIMULATOR_DAILY_CAP

    await db_session.refresh(viewer)
    assert viewer.simulator_runs_used == 0


async def test_cap_blocks_fourth_run_with_429(
    db_session: AsyncSession, competition: Competition, viewer: User, client: AsyncClient
):
    _override(db_session, viewer=viewer)
    for _ in range(SIMULATOR_DAILY_CAP):
        r = await client.post("/api/simulator/run")
        assert r.status_code == 200

    r = await client.post("/api/simulator/run")
    assert r.status_code == 429
    assert "Retry-After" in r.headers


async def test_admin_bypasses_cap_and_is_unlocked_when_feature_disabled(
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
    status_body = status_r.json()
    assert status_body["unlocked"] is True
    assert status_body["is_admin"] is True
    assert status_body["runs_remaining"] is None

    # Many more than the non-admin cap — none should 429.
    for _ in range(SIMULATOR_DAILY_CAP + 5):
        r = await client.post("/api/simulator/run")
        assert r.status_code == 200

    # bracket-picks reachable too, despite simulator_enabled=False.
    picks_r = await client.get("/api/simulator/bracket-picks")
    assert picks_r.status_code == 200


async def test_non_admin_locked_gets_403_from_bracket_picks_and_run(
    db_session: AsyncSession, competition: Competition, locked_user: User, client: AsyncClient
):
    _override(db_session, viewer=locked_user)

    picks_r = await client.get("/api/simulator/bracket-picks")
    assert picks_r.status_code == 403

    run_r = await client.post("/api/simulator/run")
    assert run_r.status_code == 403


async def test_non_admin_blocked_from_every_interactive_route_when_feature_disabled(
    db_session: AsyncSession, viewer: User, client: AsyncClient
):
    # viewer is unlocked, but the competition's master switch is off. With
    # the switch off, a non-admin must be 403'd on EVERY interactive route
    # — challenge (GET + POST), run, and bracket-picks — so they can't
    # touch the simulator at all. Only /status stays reachable.
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

    challenge_get_r = await client.get("/api/simulator/challenge")
    assert challenge_get_r.status_code == 403

    challenge_post_r = await client.post(
        "/api/simulator/challenge",
        json={"question_id": "wc-1930-winner", "answer_index": 2, "elapsed_ms": 1000},
    )
    assert challenge_post_r.status_code == 403

    fifty_fifty_r = await client.post(
        "/api/simulator/challenge/fifty-fifty",
        json={"question_id": "wc-1930-winner"},
    )
    assert fifty_fifty_r.status_code == 403

    # /status MUST stay reachable — it's how the frontend learns the
    # feature is off and hides the simulator UI.
    status_r = await client.get("/api/simulator/status")
    assert status_r.status_code == 200
    assert status_r.json()["feature_enabled"] is False
