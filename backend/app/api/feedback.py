"""User rating + written feedback → owner's inbox (via Resend).

The rating card (frontend) POSTs the star rating plus a short written
message here; we email it to the pool owner using the same Resend path as
the magic-link mailer. Auth is required — this keeps the endpoint from
being an open email relay. Feedback is emailed, not stored (no DB row).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.dependencies import CurrentUser
from app.services import analytics, email

logger = logging.getLogger(__name__)

router = APIRouter()

# Feature chips the rating card can attach to a feedback submission —
# "what did you use / like" tags shown alongside the free-text box.
# Keep this in sync with the frontend's chip list; anything the client
# sends outside this set is silently dropped rather than rejected, so a
# stale frontend build (extra/renamed chip) never 422s a feedback send.
ALLOWED_FEATURES = {
    "leaderboard",
    "insights",
    "match_detail",
    "compare",
    "smart_fill",
    "results",
}


class FeedbackIn(BaseModel):
    """Inbound feedback payload from the rating card."""

    rating: int = Field(ge=1, le=5)
    message: str = Field(min_length=1, max_length=2000)
    # Optional feature chips the submitter flagged as favourites. Capped
    # at 6 — the rating card only ever shows a handful of chips.
    features: list[str] = Field(default_factory=list, max_length=6)


@router.post("/", status_code=status.HTTP_204_NO_CONTENT)
async def post_feedback(
    payload: FeedbackIn,
    current_user: CurrentUser,
) -> None:
    """Email the submitter's rating + message to the pool owner.

    Returns 204 on success. Raises 502 if the mail send fails so the client
    can show a retry ("couldn't send — try again"). Empty/oversized messages
    and out-of-range ratings are rejected as 422 by the schema.
    """
    message = payload.message.strip()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Feedback message is empty.",
        )

    # Drop anything outside the known chip set (stale frontend build,
    # tampering) instead of 422ing — feedback delivery shouldn't fail
    # over an unrecognised chip. Order preserved from the client's list.
    features = [f for f in payload.features if f in ALLOWED_FEATURES]
    features_line = ", ".join(features)

    try:
        await email.send_feedback_email(
            rating=payload.rating,
            message=message,
            reply_to=current_user.email,
            user_name=current_user.name or "",
            features_line=features_line,
        )
    except Exception as exc:  # noqa: BLE001 — surface a retryable failure
        logger.error("feedback email send failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send feedback right now — please try again.",
        ) from exc

    # Best-effort server-side signal (mirrors the browser rating event).
    analytics.capture(
        distinct_id=str(current_user.id),
        event="feedback_submitted",
        properties={
            "rating": payload.rating,
            "has_message": True,
            "features": features,
        },
    )
    return None
