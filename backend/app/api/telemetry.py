"""Authenticated client telemetry → PostHog forwarder.

The frontend POSTs interaction events to `/api/telemetry/event`; we
capture via the server-side PostHog client (see services/analytics.py)
so we keep a single env-var configuration point (`POSTHOG_API_KEY`)
and stay ad-block-resistant — requests go to the same origin as the
rest of the app, not directly to PostHog.

An allow-list (`ALLOWED_EVENTS`) constrains which event names this
endpoint will forward. Open-ended forwarding would let any
authenticated session spray events into the PostHog quota; the
allow-list pins the contract. Add to it as new events are wired.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.dependencies import CurrentUser
from app.services import analytics

logger = logging.getLogger(__name__)

router = APIRouter()

# Allow-list of accepted event names. Extend as new instrumented
# surfaces ship. Unknown event names return 400 — the frontend wrapper
# swallows that so it doesn't break the app, but a 4xx surfaces in
# logs/inspection if a typo ships.
ALLOWED_EVENTS: set[str] = {
    "smartfill_opened",
    "smartfill_applied",
}


class TelemetryEvent(BaseModel):
    """Inbound telemetry payload from the frontend."""

    event: str
    properties: dict[str, Any] | None = None


@router.post("/event", status_code=status.HTTP_204_NO_CONTENT)
async def post_event(
    payload: TelemetryEvent,
    current_user: CurrentUser,
) -> None:
    """Forward a client interaction event to PostHog.

    Returns 204 No Content on success (and on PostHog-disabled, since
    `analytics.capture` is itself a no-op when the SDK isn't
    configured). Returns 400 when the event isn't in the allow-list.
    """
    if payload.event not in ALLOWED_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown event: {payload.event}",
        )
    analytics.capture(
        distinct_id=str(current_user.id),
        event=payload.event,
        properties=payload.properties or {},
    )
    return None
