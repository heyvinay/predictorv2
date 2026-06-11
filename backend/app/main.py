"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.database import init_db
from app.services.analytics import flush_async, init_posthog, shutdown_posthog
from app.services.score_scheduler import scheduler_lifespan


# Root-logger handler for app INFO logs (score_scheduler ticks, snapshot
# inserts, email sends). Without this only WARNING+ reaches stdout via
# Python's last-resort handler, so a healthy scheduler is indistinguishable
# from a dead one in `docker compose logs`. Uvicorn and Alembic configure
# their own loggers with propagate=False, so no duplicate lines.
logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    init_db() runs Alembic migrations on every startup, so the DB always
    converges to the migration head before requests start serving. No
    manual `alembic upgrade head` step required in dev or prod.
    """
    init_posthog()
    await init_db()
    async with scheduler_lifespan():
        yield
    shutdown_posthog()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Football prediction competition API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Flush PostHog events after every request so nothing is lost between
    # process cycles in long-running async workers.
    @app.middleware("http")
    async def posthog_flush_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        await flush_async()
        return response

    # Include API routes
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": "0.1.0"}

    return app


app = create_app()
