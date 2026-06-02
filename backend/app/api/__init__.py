"""API route modules."""

from fastapi import APIRouter

from app.api import (
    admin,
    auth,
    competition,
    entries,
    entry_predictions,
    fixtures,
    leaderboard,
    predictions,
    scores,
    telemetry,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(competition.router, prefix="/competition", tags=["competition"])
api_router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
api_router.include_router(fixtures.router, prefix="/fixtures", tags=["fixtures"])
api_router.include_router(scores.router, prefix="/scores", tags=["scores"])
api_router.include_router(leaderboard.router, prefix="/leaderboard", tags=["leaderboard"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
# Entries: user-facing routes at /entries, admin routes nested under /admin
# so the URL surface is /api/entries/* and /api/admin/{entries,competition}/*
api_router.include_router(entries.user_router, prefix="/entries", tags=["entries"])
api_router.include_router(entries.admin_router, prefix="/admin", tags=["admin"])
# Entry-scoped predictions: /api/entries/{entry_id}/predictions/*
api_router.include_router(
    entry_predictions.router, prefix="/entries", tags=["entries"]
)
# Authenticated client telemetry → server-side PostHog forwarder
api_router.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
