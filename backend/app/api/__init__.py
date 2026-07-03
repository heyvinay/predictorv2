"""API route modules."""

from fastapi import APIRouter

from app.api import (
    admin,
    announcements,
    auth,
    competition,
    entries,
    entry_predictions,
    fixtures,
    landing,
    leaderboard,
    odds,
    predictions,
    scores,
    simulator,
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
# Smart Fill — server-side cached odds (plan §9). Unauthenticated; SvelteKit
# /odds endpoint proxies through here. Note: trailing-slash-tolerant via the
# router's "/" path so both /api/odds and /api/odds/ work.
api_router.include_router(odds.router, prefix="/odds", tags=["odds"])
# Landing-page social-proof stats. Public, two simple counts.
api_router.include_router(landing.router, prefix="/landing", tags=["landing"])
# Dashboard announcements: signed-in feed at /announcements, admin CRUD
# nested under /admin/announcements (same split as entries.py).
api_router.include_router(
    announcements.user_router, prefix="/announcements", tags=["announcements"]
)
api_router.include_router(
    announcements.admin_router, prefix="/admin/announcements", tags=["admin"]
)
# What-if bracket simulator: bulk entry picks powering a client-side
# leaderboard re-rank.
api_router.include_router(simulator.router, prefix="/simulator", tags=["simulator"])
