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


# ---------------------------------------------------------------------------
# Usage & Adoption dashboard (/admin/usage, v2.212.0)
# ---------------------------------------------------------------------------
# Every helper below takes an explicit [since, until) window and an
# optional `user_ids` allow-list — the segment filter (None = no
# segment, everyone). All follow the module's silent-failure contract:
# PostHog down/unconfigured/malformed → empty/None/zero, never raise.
# Cache keys incorporate the window + granularity + segment so
# different range/segment picks don't collide.
@dataclass(frozen=True)
class SeriesPoint:
    bucket: str  # ISO date/hour/week-start label, as PostHog returns it
    count: int


@dataclass(frozen=True)
class VisitFrequency:
    active_days: int
    sessions: int


def _granularity_trunc(granularity: str) -> str:
    return {
        "hour": "toStartOfHour",
        "day": "toStartOfDay",
        "week": "toStartOfWeek",
    }.get(granularity, "toStartOfDay")


def _uid_filter_clause(user_ids: list[UUID] | None) -> str:
    """Empty string when no segment filter; else an AND'd IN clause."""
    if not user_ids:
        return ""
    return f" AND distinct_id IN {_ids_in_clause(user_ids)}"


def _uid_cache_fragment(user_ids: list[UUID] | None) -> str:
    if not user_ids:
        return "all"
    return ",".join(sorted(str(u) for u in user_ids))


def is_configured() -> bool:
    """Public check for callers (e.g. ``usage.py``) that need to render
    a single "PostHog unavailable" banner rather than probing internals."""
    return _config() is not None


async def get_active_users_series(
    since: datetime,
    until: datetime,
    granularity: str = "day",
    user_ids: list[UUID] | None = None,
) -> list[SeriesPoint]:
    """Unique active users per bucket over [since, until). Empty on failure."""
    if _config() is None:
        return []

    trunc = _granularity_trunc(granularity)
    cache_key = (
        f"active_series:{since.isoformat()}:{until.isoformat()}:"
        f"{granularity}:{_uid_cache_fragment(user_ids)}"
    )
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        f"SELECT {trunc}(timestamp) AS bucket, count(DISTINCT distinct_id) AS c "
        f"FROM events WHERE event = '$pageview' "
        f"AND timestamp >= '{since.isoformat()}' AND timestamp < '{until.isoformat()}'"
        f"{_uid_filter_clause(user_ids)} "
        f"GROUP BY bucket ORDER BY bucket"
    )
    rows = await _hogql(query)
    if rows is None:
        return []

    out: list[SeriesPoint] = []
    for row in rows:
        try:
            out.append(SeriesPoint(bucket=str(row[0]), count=int(row[1] or 0)))
        except (ValueError, IndexError, TypeError):
            continue

    _cache_set(cache_key, out)
    return out


async def get_unique_active_users(
    since: datetime,
    until: datetime,
    user_ids: list[UUID] | None = None,
) -> int | None:
    """Total unique active users across the whole window — a single
    distinct count, NOT the sum of :func:`get_active_users_series`'s
    per-bucket counts (which would double-count anyone active in more
    than one bucket). Powers the KPI scorecard's headline number.
    ``None`` on failure.
    """
    if _config() is None:
        return None

    cache_key = (
        f"unique_active:{since.isoformat()}:{until.isoformat()}:"
        f"{_uid_cache_fragment(user_ids)}"
    )
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        f"SELECT count(DISTINCT distinct_id) AS c FROM events "
        f"WHERE event = '$pageview' "
        f"AND timestamp >= '{since.isoformat()}' AND timestamp < '{until.isoformat()}'"
        f"{_uid_filter_clause(user_ids)}"
    )
    rows = await _hogql(query)
    if not rows:
        return None
    try:
        result = int(rows[0][0] or 0)
    except (IndexError, TypeError, ValueError):
        return None

    _cache_set(cache_key, result)
    return result


async def get_stickiness(
    since: datetime,
    until: datetime,
    user_ids: list[UUID] | None = None,
) -> float | None:
    """DAU/MAU-style stickiness (%) — average daily unique users divided
    by unique users across the whole window.

    Needs at least a 2-day window to mean anything; returns ``None``
    below that (the "Last hour" / "24h" ranges) so the frontend shows
    "needs a day+" rather than a number computed from one data point.
    Also ``None`` on any PostHog failure or when the window has zero
    active users (avoids a divide-by-zero).
    """
    span_days = max((until - since).total_seconds() / 86400, 0)
    if span_days < 2 or _config() is None:
        return None

    cache_key = (
        f"stickiness:{since.isoformat()}:{until.isoformat()}:"
        f"{_uid_cache_fragment(user_ids)}"
    )
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    uid_clause = _uid_filter_clause(user_ids)
    daily_query = (
        f"SELECT avg(dau) AS avg_dau FROM ("
        f"  SELECT toDate(timestamp) AS d, count(DISTINCT distinct_id) AS dau"
        f"  FROM events WHERE event = '$pageview'"
        f"  AND timestamp >= '{since.isoformat()}' AND timestamp < '{until.isoformat()}'"
        f"  {uid_clause}"
        f"  GROUP BY d"
        f")"
    )
    mau_query = (
        f"SELECT count(DISTINCT distinct_id) AS mau FROM events "
        f"WHERE event = '$pageview' "
        f"AND timestamp >= '{since.isoformat()}' AND timestamp < '{until.isoformat()}'"
        f"{uid_clause}"
    )
    daily_rows = await _hogql(daily_query)
    mau_rows = await _hogql(mau_query)
    if not daily_rows or not mau_rows:
        return None

    try:
        avg_dau = float(daily_rows[0][0] or 0)
        mau = int(mau_rows[0][0] or 0)
    except (IndexError, TypeError, ValueError):
        return None
    if mau == 0:
        return None

    result = round(avg_dau / mau * 100, 1)
    _cache_set(cache_key, result)
    return result


async def get_sessions_per_user(
    since: datetime,
    until: datetime,
    user_ids: list[UUID] | None = None,
) -> float | None:
    """Average distinct PostHog sessions per active user in the window."""
    if _config() is None:
        return None

    cache_key = (
        f"sessions_per_user:{since.isoformat()}:{until.isoformat()}:"
        f"{_uid_cache_fragment(user_ids)}"
    )
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        f"SELECT count(DISTINCT properties.$session_id) AS sessions, "
        f"count(DISTINCT distinct_id) AS users "
        f"FROM events WHERE event = '$pageview' "
        f"AND timestamp >= '{since.isoformat()}' AND timestamp < '{until.isoformat()}'"
        f"{_uid_filter_clause(user_ids)}"
    )
    rows = await _hogql(query)
    if not rows:
        return None
    try:
        sessions = int(rows[0][0] or 0)
        users = int(rows[0][1] or 0)
    except (IndexError, TypeError, ValueError):
        return None
    if users == 0:
        return None

    result = round(sessions / users, 1)
    _cache_set(cache_key, result)
    return result


async def get_new_vs_returning(
    since: datetime,
    until: datetime,
    user_ids: list[UUID] | None = None,
) -> tuple[int, int] | None:
    """(new_count, returning_count) among users active in [since, until).

    "New" = this distinct_id's earliest pageview in PostHog's retained
    history falls inside the window (true first-ever visit, not just
    first-in-window) — computed via a correlated all-time MIN() scoped
    to the users active in the window. None on failure.
    """
    if _config() is None:
        return None

    cache_key = (
        f"new_vs_returning:{since.isoformat()}:{until.isoformat()}:"
        f"{_uid_cache_fragment(user_ids)}"
    )
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        f"SELECT "
        f"  countIf(first_ts >= '{since.isoformat()}') AS new_count, "
        f"  countIf(first_ts < '{since.isoformat()}') AS returning_count "
        f"FROM ("
        f"  SELECT distinct_id, min(timestamp) AS first_ts "
        f"  FROM events WHERE event = '$pageview' GROUP BY distinct_id"
        f") AS all_time "
        f"WHERE distinct_id IN ("
        f"  SELECT DISTINCT distinct_id FROM events "
        f"  WHERE event = '$pageview' AND timestamp >= '{since.isoformat()}' "
        f"  AND timestamp < '{until.isoformat()}'{_uid_filter_clause(user_ids)}"
        f")"
    )
    rows = await _hogql(query)
    if not rows:
        return None
    try:
        new_count = int(rows[0][0] or 0)
        returning_count = int(rows[0][1] or 0)
    except (IndexError, TypeError, ValueError):
        return None

    result = (new_count, returning_count)
    _cache_set(cache_key, result)
    return result


async def get_activity_by_hour(
    since: datetime,
    until: datetime,
    user_ids: list[UUID] | None = None,
) -> list[int]:
    """24-length list (index = UTC hour 0..23) of unique active users in
    that hour bucket, summed across every day in [since, until).
    ``[]`` on failure so the frontend shows a placeholder instead of a
    misleading all-zero chart.
    """
    if _config() is None:
        return []

    cache_key = (
        f"activity_by_hour:{since.isoformat()}:{until.isoformat()}:"
        f"{_uid_cache_fragment(user_ids)}"
    )
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        f"SELECT toHour(timestamp) AS h, count(DISTINCT distinct_id) AS c "
        f"FROM events WHERE event = '$pageview' "
        f"AND timestamp >= '{since.isoformat()}' AND timestamp < '{until.isoformat()}'"
        f"{_uid_filter_clause(user_ids)} GROUP BY h ORDER BY h"
    )
    rows = await _hogql(query)
    if rows is None:
        return []

    by_hour: dict[int, int] = {}
    for row in rows:
        try:
            by_hour[int(row[0])] = int(row[1] or 0)
        except (ValueError, IndexError, TypeError):
            continue

    result = [by_hour.get(h, 0) for h in range(24)]
    _cache_set(cache_key, result)
    return result


async def get_weekly_retention_cohorts(max_cohorts: int = 5) -> list[dict[str, Any]]:
    """Weekly cohort retention grid: for each week's first-time visitors,
    what % returned in each subsequent week (offsets 0..4).

    Returns up to ``max_cohorts`` most-recent cohorts, oldest first —
    matches the grid's top-to-bottom reading order. Each row:
    ``{"cohort_week": "YYYY-MM-DD", "pct_by_offset": [100, 82, 74, ...]}``
    with ``None`` for offsets not yet observed (a cohort only 2 weeks
    old has no W2+ data). ``[]`` on any failure.
    """
    if _config() is None:
        return []

    cache_key = f"retention_cohorts:{max_cohorts}"
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        "SELECT toStartOfWeek(f.first_seen) AS cohort_week, "
        "toStartOfWeek(e.timestamp) AS active_week, "
        "count(DISTINCT e.distinct_id) AS c "
        "FROM events e "
        "INNER JOIN ("
        "  SELECT distinct_id, min(timestamp) AS first_seen "
        "  FROM events WHERE event = '$pageview' GROUP BY distinct_id"
        ") AS f ON e.distinct_id = f.distinct_id "
        "WHERE e.event = '$pageview' "
        "GROUP BY cohort_week, active_week "
        "ORDER BY cohort_week, active_week"
    )
    rows = await _hogql(query)
    if rows is None:
        return []

    # Bucket into {cohort_week_str: {offset: count}}, cohort size =
    # count at offset 0 (the cohort's own founding week).
    from datetime import date as _date

    def _to_date(v: Any) -> _date | None:
        try:
            return _date.fromisoformat(str(v)[:10])
        except ValueError:
            return None

    buckets: dict[str, dict[int, int]] = {}
    for row in rows:
        try:
            cohort_d = _to_date(row[0])
            active_d = _to_date(row[1])
            count = int(row[2] or 0)
        except (IndexError, TypeError, ValueError):
            continue
        if cohort_d is None or active_d is None:
            continue
        offset = (active_d - cohort_d).days // 7
        if offset < 0 or offset > 8:  # guard against stray rows
            continue
        buckets.setdefault(cohort_d.isoformat(), {})[offset] = count

    ordered_weeks = sorted(buckets.keys())[-max_cohorts:]
    out: list[dict[str, Any]] = []
    for week in ordered_weeks:
        offsets = buckets[week]
        size = offsets.get(0, 0)
        pct_by_offset: list[int | None] = []
        for i in range(5):
            if i not in offsets or size == 0:
                pct_by_offset.append(None)
            else:
                pct_by_offset.append(round(offsets[i] / size * 100))
        out.append({"cohort_week": week, "pct_by_offset": pct_by_offset})

    _cache_set(cache_key, out)
    return out


async def get_engagement_frequency(
    since: datetime,
    until: datetime,
    user_ids: list[UUID] | None = None,
) -> dict[int, int]:
    """Map of ``active_days -> user_count`` for users with >=1 active
    day in [since, until). PostHog only knows about users who fired at
    least one event, so a "0 active days" bucket must be added by the
    caller by diffing against the full segment population (which
    usage.py has from the DB). ``{}`` on failure.
    """
    if _config() is None:
        return {}

    cache_key = (
        f"engagement_freq:{since.isoformat()}:{until.isoformat()}:"
        f"{_uid_cache_fragment(user_ids)}"
    )
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        f"SELECT active_days, count(*) AS n FROM ("
        f"  SELECT distinct_id, count(DISTINCT toDate(timestamp)) AS active_days"
        f"  FROM events WHERE event = '$pageview'"
        f"  AND timestamp >= '{since.isoformat()}' AND timestamp < '{until.isoformat()}'"
        f"  {_uid_filter_clause(user_ids)}"
        f"  GROUP BY distinct_id"
        f") GROUP BY active_days ORDER BY active_days"
    )
    rows = await _hogql(query)
    if rows is None:
        return {}

    out: dict[int, int] = {}
    for row in rows:
        try:
            out[int(row[0])] = int(row[1] or 0)
        except (ValueError, IndexError, TypeError):
            continue

    _cache_set(cache_key, out)
    return out


async def get_unique_users_by_event(
    events: list[str],
    since: datetime,
    until: datetime,
    user_ids: list[UUID] | None = None,
) -> dict[str, int]:
    """Unique-user adoption count per event name in [since, until).

    ``events`` are our own literal event-name strings (from
    ``FEATURE_GROUPS`` server-side), never user input — safe to inline
    into the HogQL ``IN`` clause the same way ``_ids_in_clause`` treats
    UUIDs. ``{}`` on failure or empty input.
    """
    if _config() is None or not events:
        return {}

    cache_key = (
        f"unique_by_event:{','.join(sorted(events))}:{since.isoformat()}:"
        f"{until.isoformat()}:{_uid_cache_fragment(user_ids)}"
    )
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    events_clause = "(" + ", ".join(f"'{e}'" for e in events) + ")"
    query = (
        f"SELECT event, count(DISTINCT distinct_id) AS c FROM events "
        f"WHERE event IN {events_clause} "
        f"AND timestamp >= '{since.isoformat()}' AND timestamp < '{until.isoformat()}'"
        f"{_uid_filter_clause(user_ids)} GROUP BY event"
    )
    rows = await _hogql(query)
    if rows is None:
        return {}

    out: dict[str, int] = {}
    for row in rows:
        try:
            out[str(row[0])] = int(row[1] or 0)
        except (ValueError, IndexError, TypeError):
            continue

    _cache_set(cache_key, out)
    return out


async def get_all_events_last_seen(
    lookback_days: int = 180,
) -> dict[str, tuple[int, datetime | None]]:
    """Every event name PostHog has seen in the lookback window, with
    its total count and most-recent timestamp: ``{event: (count,
    last_seen)}``.

    Powers the Feature Adoption card's "last used" recency chips and
    the self-surfacing "Uncategorized events" row — ``usage.py`` diffs
    this against ``FEATURE_GROUPS`` plus the ambient/internal exclusion
    list so anything firing-but-unmapped (a forgotten feature mapping,
    or a legacy event PostHog still remembers) shows up automatically
    instead of silently vanishing. ``{}`` on failure.
    """
    if _config() is None:
        return {}

    cache_key = f"all_events_last_seen:{lookback_days}"
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        f"SELECT event, count() AS c, max(timestamp) AS last_seen FROM events "
        f"WHERE timestamp > now() - INTERVAL {int(lookback_days)} DAY "
        f"GROUP BY event ORDER BY c DESC"
    )
    rows = await _hogql(query)
    if rows is None:
        return {}

    out: dict[str, tuple[int, datetime | None]] = {}
    for row in rows:
        try:
            name = str(row[0])
            count = int(row[1] or 0)
            last_seen = aware_utc(row[2]) if row[2] else None
            out[name] = (count, last_seen)
        except (IndexError, TypeError, ValueError):
            continue

    _cache_set(cache_key, out)
    return out


async def get_adopters_for_events(
    events: list[str],
    since: datetime,
    until: datetime,
    user_ids: list[UUID] | None = None,
    limit: int = 20,
) -> list[tuple[UUID, datetime]]:
    """Most-recent adopters of any event in ``events``, newest first —
    powers the Feature Adoption card's click-through drawer.
    ``[(user_id, last_used)]``. ``[]`` on failure or empty input.
    """
    if _config() is None or not events:
        return []

    cache_key = (
        f"adopters:{','.join(sorted(events))}:{since.isoformat()}:"
        f"{until.isoformat()}:{_uid_cache_fragment(user_ids)}:{limit}"
    )
    cached = _cache_get(cache_key, SINGLE_TTL_S)
    if cached is not None:
        return cached

    events_clause = "(" + ", ".join(f"'{e}'" for e in events) + ")"
    query = (
        f"SELECT distinct_id, max(timestamp) AS last_used FROM events "
        f"WHERE event IN {events_clause} "
        f"AND timestamp >= '{since.isoformat()}' AND timestamp < '{until.isoformat()}'"
        f"{_uid_filter_clause(user_ids)} "
        f"GROUP BY distinct_id ORDER BY last_used DESC LIMIT {int(limit)}"
    )
    rows = await _hogql(query)
    if rows is None:
        return []

    out: list[tuple[UUID, datetime]] = []
    for row in rows:
        try:
            uid = UUID(str(row[0]))
            ts = aware_utc(row[1])
            if ts is not None:
                out.append((uid, ts))
        except (ValueError, IndexError, TypeError):
            continue

    _cache_set(cache_key, out)
    return out


async def get_active_days_and_sessions_for_users(
    user_ids: list[UUID],
    since: datetime,
) -> dict[UUID, VisitFrequency]:
    """Batched per-user (active_days, session_count) since ``since`` —
    powers the Power-users table. Mirrors the batching shape of
    :func:`get_recent_seen_for_users`. ``{}`` on empty input or failure.
    """
    if not user_ids or _config() is None:
        return {}

    cache_key = (
        f"visit_freq:{since.isoformat()}:"
        + ",".join(sorted(str(u) for u in user_ids))
    )
    cached = _cache_get(cache_key, BATCH_TTL_S)
    if cached is not None:
        return cached

    query = (
        f"SELECT distinct_id, "
        f"count(DISTINCT toDate(timestamp)) AS active_days, "
        f"count(DISTINCT properties.$session_id) AS sessions "
        f"FROM events WHERE event = '$pageview' "
        f"AND distinct_id IN {_ids_in_clause(user_ids)} "
        f"AND timestamp >= '{since.isoformat()}' "
        f"GROUP BY distinct_id"
    )
    rows = await _hogql(query)
    if rows is None:
        return {}

    out: dict[UUID, VisitFrequency] = {}
    for row in rows:
        try:
            uid = UUID(str(row[0]))
            out[uid] = VisitFrequency(
                active_days=int(row[1] or 0),
                sessions=int(row[2] or 0),
            )
        except (ValueError, IndexError, TypeError):
            continue

    _cache_set(cache_key, out)
    return out
