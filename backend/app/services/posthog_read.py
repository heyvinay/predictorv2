"""PostHog read-side service (v2.156.0).

Read-only counterpart of :mod:`app.services.analytics` (which writes
events). Used by the admin Engagement card on ``/admin/users/[id]`` and
the Users-list hover tooltip.

**Designed as a general service.** Admin pages are the first consumer,
but a future ``GET /api/me/engagement`` for personalized landing-page
copy will reuse the same two functions for the current user. No
admin-specific code lives in this module.

**Failure mode: silent.** Every public function returns an empty /
``None`` value when PostHog is unreachable, rate-limited, or
mis-configured. They MUST NOT raise into the request path — the
admin pages need to keep rendering when PostHog is down. Errors are
logged at WARNING level for ops visibility.

**Caching.** A small in-process TTL cache keeps batched queries cheap
even under repeated admin clicks. Cache is keyed on ``(function_name,
arg_hash)`` and entries expire after ``BATCH_TTL_S`` / ``SINGLE_TTL_S``.

**Auth.** Requires a PostHog personal API key (``phx_*``) — the project
key (``phc_*``) used by ``analytics.py`` is write-only and cannot read
events back. Generate one under PostHog → Account → Personal API Keys
with the "Read project events" scope, then set ``POSTHOG_PERSONAL_API_KEY``
and ``POSTHOG_PROJECT_ID`` env vars.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx

from app.config import get_settings
from app.models._datetime import aware_utc
from app.schemas.admin import EngagementSummary, RecentSeen


# Site Pulse / engagement-signal data shapes (v2.176.0). These are
# returned by the helpers added at the bottom of this module — kept as
# dataclasses (not Pydantic) because they live entirely inside the
# service layer; the API layer converts to Pydantic at the boundary.
@dataclass(frozen=True)
class DauPointRaw:
    date: str
    count: int


@dataclass(frozen=True)
class PageTrendRaw:
    path: str
    current_7d: int
    prior_7d: int


@dataclass(frozen=True)
class EventTrendRaw:
    event_name: str
    current_7d: int
    prior_7d: int

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache (in-process, TTL-bounded)
# ---------------------------------------------------------------------------
# Two TTLs: batch lookups (used for the Users-list tooltip — repeated
# admin browsing) cache longer than per-user detail (which the admin
# expects to be fresh-ish when they open a user page).
BATCH_TTL_S = 5 * 60   # 5 minutes
SINGLE_TTL_S = 2 * 60  # 2 minutes
HTTP_TIMEOUT_S = 8.0

_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str, ttl: int) -> Any | None:
    """Return cached value if fresh, else None."""
    item = _cache.get(key)
    if item is None:
        return None
    ts, value = item
    if time.time() - ts > ttl:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.time(), value)


def _clear_cache() -> None:
    """Test helper — purge the cache between test cases."""
    _cache.clear()


# ---------------------------------------------------------------------------
# HogQL HTTP transport
# ---------------------------------------------------------------------------
def _config() -> tuple[str, str, str] | None:
    """Return ``(host, project_id, api_key)`` or None if PostHog is disabled.

    PostHog is "disabled" when either the personal API key or project id
    is empty. Callers should short-circuit cleanly when this returns None.
    """
    settings = get_settings()
    if not settings.posthog_personal_api_key or not settings.posthog_project_id:
        return None
    return (
        settings.posthog_host,
        settings.posthog_project_id,
        settings.posthog_personal_api_key,
    )


async def _hogql(query: str) -> list[list[Any]] | None:
    """Execute a HogQL query against the PostHog query endpoint.

    Returns the result rows (list of lists matching the SELECT order) or
    ``None`` if the request failed for any reason. Failures are logged
    at WARNING but never raised — the read service is best-effort.

    Each row in the response is a list whose ordering matches the
    ``SELECT`` clause in the query. Callers know the schema they asked
    for and unpack accordingly.
    """
    cfg = _config()
    if cfg is None:
        return None
    host, project_id, api_key = cfg

    url = f"{host.rstrip('/')}/api/projects/{project_id}/query/"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {"query": {"kind": "HogQLQuery", "query": query}}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
            resp = await client.post(url, headers=headers, json=body)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("PostHog query timed out / network error: %s", exc)
        return None
    except httpx.HTTPError as exc:
        logger.warning("PostHog query HTTP error: %s", exc)
        return None

    if resp.status_code >= 400:
        # Log the body so 401/403/429 reasons are visible — but truncate
        # to avoid filling the logs on a verbose error page.
        body_snip = resp.text[:500] if resp.text else ""
        logger.warning(
            "PostHog query failed: HTTP %s · body=%s",
            resp.status_code,
            body_snip,
        )
        return None

    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        logger.warning("PostHog response not JSON: %s", exc)
        return None

    rows = data.get("results")
    if not isinstance(rows, list):
        logger.warning("PostHog response missing 'results' array: %s", data)
        return None
    return rows


def _ids_in_clause(user_ids: list[UUID]) -> str:
    """Render a list of UUIDs as a HogQL ``IN`` clause literal.

    PostHog's HogQL doesn't support parameterised queries the way SQL
    drivers do, but UUIDs are fixed-format hex strings so single-quoting
    them is safe — there's no escapable character class in the
    ``[0-9a-f-]`` UUID alphabet that could break out of the string.
    """
    return "(" + ", ".join(f"'{uid}'" for uid in user_ids) + ")"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def get_recent_seen_for_users(
    user_ids: list[UUID],
    days: int = 30,
) -> dict[UUID, RecentSeen]:
    """Batched ``last_seen`` + ``last_url`` lookup keyed by ``distinct_id``.

    One HogQL query, regardless of input size — PostHog handles the IN
    clause efficiently for the 100-id batches the Users list will send.

    Returns a partial dict — users with no events in the lookup window
    are simply absent from the result. The Users-list renderer should
    treat the missing key as "no PostHog data" and hide the hover
    tooltip for that row.
    """
    if not user_ids:
        return {}

    cache_key = (
        f"recent_seen:{days}:"
        + ",".join(sorted(str(uid) for uid in user_ids))
    )
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        f"SELECT distinct_id, max(timestamp) AS last_seen, "
        f"argMax(properties.$current_url, timestamp) AS last_url "
        f"FROM events "
        f"WHERE event = '$pageview' "
        f"AND distinct_id IN {_ids_in_clause(user_ids)} "
        f"AND timestamp > now() - INTERVAL {int(days)} DAY "
        f"GROUP BY distinct_id"
    )
    rows = await _hogql(query)
    if rows is None:
        return {}

    out: dict[UUID, RecentSeen] = {}
    for row in rows:
        try:
            distinct_id_str, last_seen, last_url = row[0], row[1], row[2]
            out[UUID(str(distinct_id_str))] = RecentSeen(
                last_seen=last_seen,
                last_url=last_url,
            )
        except (ValueError, IndexError, TypeError) as exc:
            # One malformed row shouldn't poison the whole batch.
            logger.warning("Skipping malformed PostHog row %r: %s", row, exc)
            continue

    _cache_set(cache_key, out)
    return out


async def get_engagement_summary(
    user_id: UUID,
    days: int = 30,
) -> EngagementSummary | None:
    """Full engagement mini-card for one user.

    Two HogQL queries:

    1. ``last_seen`` + ``last_url`` + ``session_count`` + ``avg_session_seconds``
       — all derived from the events table, using ``$session_id`` for
       distinct-session counting.
    2. Daily pageview counts over the last 14 days — used to render the
       sparkline. Zero-filled so the sparkline always has exactly 14
       elements regardless of how active the user was.

    Returns ``None`` when PostHog is disabled (missing env vars). Returns
    an EngagementSummary with all-zero fields when PostHog is reachable
    but the user has zero events. The frontend treats both as "show '—'".
    """
    cache_key = f"engagement:{user_id}:{days}"
    cached = _cache_get(cache_key, SINGLE_TTL_S)
    if cached is not None:
        return cached

    if _config() is None:
        return None

    # HogQL note (v2.176.3): PostHog stores `$session_duration` as a
    # String property; `avg()` rejects String columns with HTTP 400 —
    # "Illegal type String of argument for aggregate function avg".
    # Wrapping with `toFloat()` parses each value and returns NULL on
    # failure, which `avg()` excludes from the mean. Without this
    # coercion the entire summary query fails and the per-user
    # engagement card silently shows the "PostHog not configured"
    # placeholder, masking the real cause.
    summary_query = (
        f"SELECT "
        f"max(timestamp) AS last_seen, "
        f"argMax(properties.$current_url, timestamp) AS last_url, "
        f"count(DISTINCT properties.$session_id) AS session_count, "
        f"avg(toFloat(properties.$session_duration)) AS avg_session_seconds "
        f"FROM events "
        f"WHERE event = '$pageview' "
        f"AND distinct_id = '{user_id}' "
        f"AND timestamp > now() - INTERVAL {int(days)} DAY"
    )
    summary_rows = await _hogql(summary_query)
    if summary_rows is None:
        return None

    last_seen: Any = None
    last_url: Any = None
    session_count = 0
    avg_session_seconds: float | None = None
    if summary_rows:
        row = summary_rows[0]
        try:
            last_seen = row[0]
            last_url = row[1]
            session_count = int(row[2] or 0)
            avg_session_seconds = (
                float(row[3]) if row[3] is not None else None
            )
        except (IndexError, TypeError, ValueError) as exc:
            logger.warning("Malformed PostHog summary row %r: %s", row, exc)

    # Sparkline — separate query so the GROUP BY doesn't conflate with
    # the aggregates above.
    sparkline_query = (
        f"SELECT toDate(timestamp) AS day, count() AS pv "
        f"FROM events "
        f"WHERE event = '$pageview' "
        f"AND distinct_id = '{user_id}' "
        f"AND timestamp > now() - INTERVAL 14 DAY "
        f"GROUP BY day "
        f"ORDER BY day"
    )
    spark_rows = await _hogql(sparkline_query) or []

    # Zero-fill so the sparkline has exactly 14 buckets. PostHog returns
    # rows in chronological order; we don't reconstruct the date axis
    # because the frontend's "oldest left, newest right" rendering only
    # needs the magnitudes — the absence of a day is encoded as 0.
    counts_by_day: dict[str, int] = {}
    for row in spark_rows:
        try:
            counts_by_day[str(row[0])] = int(row[1] or 0)
        except (IndexError, TypeError, ValueError):
            continue
    # Take last 14 in chronological order. If fewer than 14 rows, left-pad
    # with zeros so the sparkline always has 14 bars.
    ordered = sorted(counts_by_day.values())
    if len(spark_rows) >= 14:
        sparkline = ordered[-14:]
    else:
        sparkline = [0] * (14 - len(ordered)) + ordered

    result = EngagementSummary(
        last_seen=last_seen,
        last_url=last_url,
        session_count=session_count,
        avg_session_seconds=avg_session_seconds,
        sparkline_14d=sparkline,
    )
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# v2.176.0 — broadcast-cohort engagement signal + Site Pulse helpers
# ---------------------------------------------------------------------------
# All four helpers below follow the same silent-failure contract: any
# failure (PostHog disabled, network error, malformed response, partial
# rows) returns an empty result (``{}`` / ``[]``) so the caller can
# degrade gracefully. They MUST NOT raise into the request path.
async def get_last_pageview_for_users_since(
    cutoff: datetime,
) -> dict[UUID, datetime]:
    """Return MAX($pageview.timestamp) per distinct_id since cutoff.

    Used by the broadcast Pool Ghost / Lapsing cohorts as the
    fallback engagement signal (B in the A+B hybrid — primary is
    User.last_seen_at). Empty dict on any failure: PostHog disabled,
    network error, malformed JSON, etc. Caller MUST tolerate empty
    result and degrade to column-only (predicate factory pattern).
    """
    if _config() is None:
        return {}

    cache_key = f"pageview_since:{cutoff.isoformat()}"
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        f"SELECT distinct_id, max(timestamp) AS last_seen "
        f"FROM events "
        f"WHERE event = '$pageview' "
        f"AND timestamp >= '{cutoff.isoformat()}' "
        f"GROUP BY distinct_id"
    )
    rows = await _hogql(query)
    if rows is None:
        return {}

    out: dict[UUID, datetime] = {}
    for row in rows:
        try:
            uid = UUID(str(row[0]))
            ts = aware_utc(row[1])
            if ts is not None:
                out[uid] = ts
        except (ValueError, IndexError, TypeError) as exc:
            logger.warning("Skipping malformed PostHog row %r: %s", row, exc)
            continue

    _cache_set(cache_key, out)
    return out


async def get_dau_sparkline_14d() -> list[DauPointRaw]:
    """14 daily DAU counts, oldest → newest. Zero-filled.

    Used by the Site Pulse panel. Returns ``[]`` on any failure so the
    panel renders a placeholder instead of an error.
    """
    if _config() is None:
        return []

    cache_key = "dau_sparkline_14d"
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        "SELECT toDate(timestamp) AS day, "
        "count(DISTINCT distinct_id) AS dau "
        "FROM events "
        "WHERE event = '$pageview' "
        "AND timestamp >= now() - INTERVAL 14 DAY "
        "GROUP BY day ORDER BY day"
    )
    rows = await _hogql(query)
    if rows is None:
        return []

    out: list[DauPointRaw] = []
    for row in rows:
        try:
            out.append(DauPointRaw(date=str(row[0]), count=int(row[1] or 0)))
        except (ValueError, IndexError, TypeError):
            continue

    _cache_set(cache_key, out)
    return out


async def get_top_pages_7d(limit: int = 5) -> list[PageTrendRaw]:
    """Top pages by 7-day pageview count + prior 7d for week-over-week trend.

    Used by the Site Pulse panel. Returns ``[]`` on any failure.
    """
    if _config() is None:
        return []

    cache_key = f"top_pages_7d:{limit}"
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        "SELECT properties.$pathname AS path, "
        "countIf(timestamp >= now() - INTERVAL 7 DAY) AS current_7d, "
        "countIf(timestamp >= now() - INTERVAL 14 DAY "
        "        AND timestamp <  now() - INTERVAL 7 DAY) AS prior_7d "
        "FROM events "
        "WHERE event = '$pageview' "
        "AND timestamp >= now() - INTERVAL 14 DAY "
        f"GROUP BY path ORDER BY current_7d DESC LIMIT {int(limit)}"
    )
    rows = await _hogql(query)
    if rows is None:
        return []

    out: list[PageTrendRaw] = []
    for row in rows:
        try:
            path = str(row[0]) if row[0] is not None else "(unknown)"
            out.append(PageTrendRaw(
                path=path,
                current_7d=int(row[1] or 0),
                prior_7d=int(row[2] or 0),
            ))
        except (ValueError, IndexError, TypeError):
            continue

    _cache_set(cache_key, out)
    return out


async def get_top_events_7d(limit: int = 5) -> list[EventTrendRaw]:
    """Top custom events by 7-day count + prior 7d for week-over-week trend.

    Excludes PostHog's internal events ($pageview, $autocapture, $identify)
    so the list shows only the events the app explicitly captures via
    the analytics wrapper. Returns ``[]`` on any failure.
    """
    if _config() is None:
        return []

    cache_key = f"top_events_7d:{limit}"
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    # Exclusion list = ambient telemetry that drowns out real behaviour.
    # See docs/superpowers/specs/2026-06-13-site-pulse-panel-design.md
    # for the rationale. The goal of this widget is "what are people
    # DOING?" — performance signals (web_vitals), pageview duplicates
    # (page_viewed), generic nav (nav_clicked, destination lives in
    # properties), and PostHog-internal events all belong elsewhere.
    # $rageclick is a real signal but dominates this widget when
    # included; it gets surfaced separately in a future iteration if
    # needed.
    query = (
        "SELECT event, "
        "countIf(timestamp >= now() - INTERVAL 7 DAY) AS current_7d, "
        "countIf(timestamp >= now() - INTERVAL 14 DAY "
        "        AND timestamp <  now() - INTERVAL 7 DAY) AS prior_7d "
        "FROM events "
        "WHERE timestamp >= now() - INTERVAL 14 DAY "
        "AND event NOT IN ("
        "  '$pageview', '$autocapture', '$identify', "
        "  '$pageleave', '$feature_flag_called', "
        "  '$web_vitals', '$rageclick', '$exception', '$dead_click', "
        "  'page_viewed', 'nav_clicked'"
        ") "
        f"GROUP BY event ORDER BY current_7d DESC LIMIT {int(limit)}"
    )
    rows = await _hogql(query)
    if rows is None:
        return []

    out: list[EventTrendRaw] = []
    for row in rows:
        try:
            out.append(EventTrendRaw(
                event_name=str(row[0]) if row[0] is not None else "(unknown)",
                current_7d=int(row[1] or 0),
                prior_7d=int(row[2] or 0),
            ))
        except (ValueError, IndexError, TypeError):
            continue

    _cache_set(cache_key, out)
    return out
