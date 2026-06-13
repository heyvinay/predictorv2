"""Site Pulse assembler (v2.176.0).

Thin orchestrator over :mod:`app.services.posthog_read` and
:mod:`app.services.audit` that builds the 4-widget Site Pulse panel
shown at the top of /admin.

Partial failure is tolerated by design: each PostHog helper is
silent-fail (returns empty), so if PostHog is down the three PostHog-
backed widgets render placeholders while the audit-backed "Recent
Logins" widget still loads. The endpoint never raises into the request
path on PostHog failure.

The audit query CAN raise on DB error — that's a normal failure path
the API layer handles (admin endpoints already surface 500s
appropriately for DB issues).
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.admin import (
    DauPoint,
    EventTrend,
    PageTrend,
    RecentLogin,
    SitePulse,
)
from app.services import audit, posthog_read

logger = logging.getLogger(__name__)


async def get_site_pulse(session: AsyncSession) -> SitePulse:
    """Build all 4 Site Pulse widgets.

    Order of operations doesn't matter — each query is independent.
    Sequential await keeps the implementation simple; the PostHog
    queries are TTL-cached so admin re-opens are sub-ms.

    Partial failures:
    * PostHog helpers return `[]` on any error (silent contract). The
      frontend renders a "data unavailable" placeholder per widget.
    * The audit query is allowed to raise — DB-level failures are
      surfaced as 500s by FastAPI.
    """
    sparkline = await posthog_read.get_dau_sparkline_14d()
    top_pages = await posthog_read.get_top_pages_7d(limit=5)
    top_events = await posthog_read.get_top_events_7d(limit=5)
    logins_raw = await audit.get_recent_logins(session, limit=20)

    return SitePulse(
        dau_sparkline=[
            DauPoint(date=p.date, count=p.count) for p in sparkline
        ],
        top_pages=[
            PageTrend(
                path=p.path,
                current_7d=p.current_7d,
                prior_7d=p.prior_7d,
            )
            for p in top_pages
        ],
        top_events=[
            EventTrend(
                event_name=e.event_name,
                current_7d=e.current_7d,
                prior_7d=e.prior_7d,
            )
            for e in top_events
        ],
        recent_logins=[
            RecentLogin(
                user_id=uid,
                name=name or "",
                login_at=ts,
            )
            for uid, name, ts in logins_raw
        ],
    )
