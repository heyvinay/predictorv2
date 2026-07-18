"""Tournament conclusion end-state (Plan A) — flag, phase-status, admin toggle."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register all tables
from app.models.competition import Competition
from app.models._datetime import utc_now


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
        name="WC26",
        is_active=True,
        phase1_deadline=utc_now(),
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


@pytest.mark.asyncio
async def test_competition_has_conclusion_fields(competition: Competition):
    assert competition.tournament_concluded is False
    assert competition.final_match_narrative is None


@pytest.mark.asyncio
async def test_phase_status_surfaces_tournament_concluded(
    db_session: AsyncSession, competition: Competition
):
    from app.api.competition import get_phase_status

    status_out = await get_phase_status(session=db_session, _current_user=None)
    assert status_out.tournament_concluded is False

    competition.tournament_concluded = True
    await db_session.commit()
    status_out = await get_phase_status(session=db_session, _current_user=None)
    assert status_out.tournament_concluded is True
