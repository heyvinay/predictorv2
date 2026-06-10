"""Admin score editor (v2.162.0) — sync guard + audit events.

The /admin/sync fixtures table lets the admin enter scores and seed
knockout teams by hand. These tests pin the backend contracts:

1. The API sync SKIPS admin-verified scores (a manual correction must
   survive the 60-second scheduler re-applying a wrong upstream value)
   and counts them in `skipped_verified`. Unverified scores are still
   overwritten as before.
2. `PUT /api/scores/{fixture_id}` records a `score.manual_update` audit
   event, marks the score MANUAL, and flips the fixture FINISHED.
3. `PUT /api/fixtures/{id}` records a `fixture.admin_update` audit event
   (the knockout team-seeding escape hatch).

Uses in-memory SQLite per the project convention.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import app.models  # noqa: F401  — registers all models
from app.database import get_session
from app.dependencies import get_current_user
from app.main import app
from app.models.audit import AuditEvent
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score, ScoreSource
from app.models.user import AuthProvider, User
from app.services.external_scores import ExternalScore
from app.services.score_sync import ScoreSyncResult, _apply_external_score


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(
        name="WC2026", entry_fee=Decimal("0"), external_id="WC", is_active=True
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


@pytest_asyncio.fixture
async def admin_user(session: AsyncSession) -> User:
    u = User(
        email="admin@example.com",
        name="Admin",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_admin=True,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _make_fixture(
    session: AsyncSession,
    competition: Competition,
    *,
    stage: str = "group",
    home: str = "Brazil",
    away: str = "Germany",
    status: MatchStatus = MatchStatus.SCHEDULED,
    external_id: str | None = "fd-1",
) -> Fixture:
    fx = Fixture(
        competition_id=competition.id,
        external_id=external_id,
        home_team=home,
        away_team=away,
        kickoff=datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
        stage=stage,
        group="A" if stage == "group" else None,
        status=status,
    )
    session.add(fx)
    await session.commit()
    await session.refresh(fx)
    return fx


def _ext(fixture: Fixture, home: int, away: int) -> ExternalScore:
    return ExternalScore(
        external_id=fixture.external_id or "",
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        home_score=home,
        away_score=away,
        status=MatchStatus.FINISHED,
    )


# ---------------------------------------------------------------------------
# 1. Sync guard
# ---------------------------------------------------------------------------
class TestVerifiedSyncGuard:
    async def test_sync_skips_verified_score(
        self, session: AsyncSession, competition: Competition
    ):
        """An admin-verified 2-1 survives the API trying to write 0-3."""
        fx = await _make_fixture(session, competition, status=MatchStatus.FINISHED)
        session.add(
            Score(
                fixture_id=fx.id,
                home_score=2,
                away_score=1,
                source=ScoreSource.MANUAL,
                verified=True,
            )
        )
        await session.commit()

        result = ScoreSyncResult()
        await _apply_external_score(session, competition.id, _ext(fx, 0, 3), result)
        await session.commit()

        score = (
            await session.execute(select(Score).where(Score.fixture_id == fx.id))
        ).scalar_one()
        assert score.home_score == 2
        assert score.away_score == 1
        assert score.source == ScoreSource.MANUAL
        assert score.verified is True
        assert result.skipped_verified == 1
        assert result.updated == 0

    async def test_sync_still_overwrites_unverified_manual_score(
        self, session: AsyncSession, competition: Competition
    ):
        """A manual score saved WITHOUT verified stays API-updatable —
        the stopgap case where the admin wants the API to resume."""
        fx = await _make_fixture(session, competition, status=MatchStatus.FINISHED)
        session.add(
            Score(
                fixture_id=fx.id,
                home_score=1,
                away_score=1,
                source=ScoreSource.MANUAL,
                verified=False,
            )
        )
        await session.commit()

        result = ScoreSyncResult()
        await _apply_external_score(session, competition.id, _ext(fx, 0, 3), result)
        await session.commit()

        score = (
            await session.execute(select(Score).where(Score.fixture_id == fx.id))
        ).scalar_one()
        assert score.home_score == 0
        assert score.away_score == 3
        assert score.source == ScoreSource.API
        assert result.updated == 1
        assert result.skipped_verified == 0


# ---------------------------------------------------------------------------
# 2 + 3. HTTP endpoints: manual score + team seeding write audit events
# ---------------------------------------------------------------------------
def _override(session: AsyncSession, admin: User):
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestManualScoreEndpoint:
    async def test_manual_score_sets_manual_verified_finished_and_audits(
        self,
        session: AsyncSession,
        competition: Competition,
        admin_user: User,
        client: AsyncClient,
    ):
        fx = await _make_fixture(session, competition)
        _override(session, admin_user)

        r = await client.put(
            f"/api/scores/{fx.id}",
            json={"home_score": 2, "away_score": 1, "verified": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["home_score"] == 2
        assert body["source"] == "manual"
        assert body["verified"] is True

        await session.refresh(fx)
        assert fx.status == MatchStatus.FINISHED

        events = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.event_type == "score.manual_update"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].actor_user_id == admin_user.id
        assert events[0].subject_id == fx.id
        assert events[0].event_metadata["new"]["home_score"] == 2
        # First manual entry on a fixture with no prior score.
        assert events[0].event_metadata["old"] is None

    async def test_knockout_shootout_resolves_winner(
        self,
        session: AsyncSession,
        competition: Competition,
        admin_user: User,
        client: AsyncClient,
    ):
        """Level after ET, decided on penalties — outcome resolves to the
        shootout winner (this is why the editor needs ET/pens fields)."""
        fx = await _make_fixture(
            session, competition, stage="quarter_final", external_id="fd-ko"
        )
        _override(session, admin_user)

        r = await client.put(
            f"/api/scores/{fx.id}",
            json={
                "home_score": 1,
                "away_score": 1,
                "home_score_et": 1,
                "away_score_et": 1,
                "home_penalties": 4,
                "away_penalties": 3,
                "verified": True,
            },
        )
        assert r.status_code == 200
        assert r.json()["outcome"] == "1"


class TestFixtureTeamSeeding:
    async def test_team_update_writes_audit_event(
        self,
        session: AsyncSession,
        competition: Competition,
        admin_user: User,
        client: AsyncClient,
    ):
        fx = await _make_fixture(
            session,
            competition,
            stage="round_of_32",
            home="Winner of Match 1",
            away="Winner of Match 2",
            external_id="fd-r32",
        )
        _override(session, admin_user)

        r = await client.put(
            f"/api/fixtures/{fx.id}",
            json={"home_team": "Brazil", "away_team": "Mexico"},
        )
        assert r.status_code == 200
        assert r.json()["home_team"] == "Brazil"

        events = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.event_type == "fixture.admin_update"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata["old"]["home_team"] == "Winner of Match 1"
        assert events[0].event_metadata["new"]["home_team"] == "Brazil"
