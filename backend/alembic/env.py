"""Alembic migration environment configuration."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from app.config import get_settings

# Import every model so SQLModel.metadata can see it — required for
# `alembic revision --autogenerate` to detect new tables / columns.
from app.models import (  # noqa: F401
    AuditEvent,
    BonusAnswer,
    BonusPrediction,
    Competition,
    Fixture,
    LeaderboardSnapshot,
    MatchPrediction,
    PredictionEntry,
    PredictionEntryEvent,
    PredictionEntryPhase,
    Score,
    TeamPrediction,
    User,
)

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False is load-bearing: init_db() runs this
    # inside FastAPI startup, and the default (True) silently disables every
    # logger created before it — uvicorn's "Application startup complete",
    # the score_scheduler tick/warning lines, all app INFO+WARNING output.
    # That made a healthy scheduler indistinguishable from a dead one and
    # swallowed sync errors entirely.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = SQLModel.metadata


def get_url() -> str:
    """Get database URL from settings."""
    settings = get_settings()
    return str(settings.database_url).replace("postgresql://", "postgresql+asyncpg://")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
