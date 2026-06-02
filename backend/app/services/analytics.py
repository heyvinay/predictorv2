"""PostHog analytics client — singleton initialised from settings."""

import asyncio
import logging
from typing import Any

from posthog import Posthog

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: Posthog | None = None


def get_posthog() -> Posthog | None:
    """Return the shared PostHog client, or None if no API key is configured."""
    return _client


def init_posthog() -> None:
    global _client
    settings = get_settings()
    if not settings.posthog_api_key:
        logger.info("PostHog disabled: POSTHOG_API_KEY not set")
        return
    _client = Posthog(
        settings.posthog_api_key,
        host=settings.posthog_host,
    )
    logger.info("PostHog initialised (host=%s)", settings.posthog_host)


def shutdown_posthog() -> None:
    if _client is not None:
        _client.shutdown()


def capture(distinct_id: str, event: str, properties: dict[str, Any] | None = None) -> None:
    """Fire-and-forget event capture. Wraps the sync SDK call."""
    if _client is None:
        return
    _client.capture(distinct_id=distinct_id, event=event, properties=properties or {})


async def flush_async() -> None:
    """Flush pending events without blocking the event loop."""
    if _client is None:
        return
    await asyncio.to_thread(_client.flush)
