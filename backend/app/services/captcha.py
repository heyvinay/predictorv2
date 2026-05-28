"""Cloudflare Turnstile verification for the sign-in CAPTCHA.

Gates the one unauthenticated, account-creating endpoint
(``/api/auth/request-magic-link``). In dev, with no
``TURNSTILE_SECRET_KEY`` set, verification short-circuits to success —
mirroring the Resend dev fallback — so local sign-in needs no widget.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

SITEVERIFY_URL: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str | None, remoteip: str | None = None) -> bool:
    """Return True if the Turnstile token is valid (or verification is
    disabled in dev).

    A missing/empty secret key means CAPTCHA is disabled → pass through.
    Otherwise a missing token, a failed challenge, or any network error
    all resolve to False so the caller rejects the request.
    """
    settings = get_settings()
    if not settings.turnstile_secret_key:
        return True  # dev / unconfigured — no gate

    if not token:
        return False

    data = {"secret": settings.turnstile_secret_key, "response": token}
    if remoteip:
        data["remoteip"] = remoteip

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(SITEVERIFY_URL, data=data, timeout=10.0)
        response.raise_for_status()
        return bool(response.json().get("success", False))
    except (httpx.HTTPError, ValueError) as exc:
        # Network failure or unparseable body — fail closed.
        logger.warning("[captcha] Turnstile verification failed: %s", exc)
        return False
