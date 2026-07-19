"""Final audit — full rescore vs live leaderboard (Plan A)."""

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register all tables
from app.services import final_audit


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.mark.asyncio
async def test_audit_writes_artifact_and_summary(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(final_audit, "SNAPSHOT_DIR", tmp_path)
    summary = await final_audit.run_final_audit(db_session)
    assert summary["entries_verified"] == 0  # empty DB
    assert summary["discrepancies"] == 0
    files = list(tmp_path.glob("final-audit-*.json"))
    assert len(files) == 1
    on_disk = json.loads(files[0].read_text())
    assert on_disk["sources"]  # names the immutable sources


@pytest.mark.asyncio
async def test_latest_summary_roundtrip(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(final_audit, "SNAPSHOT_DIR", tmp_path)
    await final_audit.run_final_audit(db_session)
    loaded = final_audit.load_latest_audit_summary()
    assert loaded is not None and loaded["discrepancies"] == 0


def test_default_dir_is_not_the_readonly_snapshots_archive():
    """Regression pin: backend/snapshots/ is mounted `:ro` in production
    docker-compose (protects the frozen predictions-snapshot-*.csv files)
    — a real 2026-07-19 prod incident had this service default-pointed
    there and every "Run final audit" click 500'd with
    `OSError: [Errno 30] Read-only file system`. The real default must
    stay on a writable runtime mount (backend/data/, same as
    odds_cache.json), never backend/snapshots/."""
    assert final_audit.SNAPSHOT_DIR.name != "snapshots"
