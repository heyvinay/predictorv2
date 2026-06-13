# Site Pulse panel — at-a-glance engagement on /admin

**Date:** 2026-06-13
**Status:** Approved (brainstorming §1) — building directly per user direction
**Author:** Vinay (via brainstorming session)
**Slice:** 1 of 1

## Summary

A 4-widget panel pinned to the top of `/admin`. Glance-able, no
pagination, no drill-down. Answers operational questions like
"is the site being used?" / "which features matter?" / "who logged
in recently?" without leaving the page.

Replaces the speculative `/admin/insights` dedicated page — that
surface was over-scoped for a transient ~100-user tournament product.

## Scope (in)

1. **4 widgets**, all top of `/admin` Overview tab:
   - **DAU sparkline (last 14 days)** — count + 14-bar sparkline
   - **Top 5 pages (rolling 7d w/ trend)** — current 7d count + week-
     over-week delta indicator
   - **Top 5 events (rolling 7d w/ trend)** — same shape as pages,
     restricted to custom events (no `$pageview`/`$autocapture`/`$identify`)
   - **Last 20 logins across the pool** — name + relative time, fed by
     `audit_events.event_type='auth.login_succeeded'`
2. **One new endpoint** `GET /admin/pulse → SitePulse` (admin-only).
3. **One new service module** `app/services/pulse.py` — thin assembler
   over PostHog + audit data sources.
4. **Three new PostHog helpers** in `posthog_read.py`:
   `get_dau_sparkline_14d`, `get_top_pages_7d`, `get_top_events_7d`.
5. **One new audit helper** in `audit.py`: `get_recent_logins(limit=20)`.
6. **New Pydantic schemas** in `schemas/admin.py`: `SitePulse`,
   `DauPoint`, `PageTrend`, `EventTrend`, `RecentLogin`.
7. **New Svelte component** `SitePulsePanel.svelte` mounted at the top
   of `/admin/+page.svelte` Overview tab.
8. **5-minute server-side TTL cache** for the PostHog widgets (reuses
   existing `posthog_read.py` cache pattern). Logins query runs live
   (cheap SQL).
9. **Pytest** for: each PostHog helper, the assembler, partial-failure
   degraded mode.

## Scope (out)

- A dedicated `/admin/insights` route — explicitly rejected.
- Clickable drill-downs from widgets (top pages aren't links).
- Filter controls / time-window toggles.
- Charts beyond the sparkline (no retention curves, no funnel views,
  no histograms).
- Real-time push or auto-refresh (5-min cache + manual page reload).
- Exports.
- Per-user activity drill-in (already on `/admin/users/[id]`).
- A "system status" tile for PostHog reachability (silent degradation
  is the contract — no UX hint when it's down).

## Architecture

### Data sources

| Widget | Source | Why |
|---|---|---|
| DAU sparkline | PostHog HogQL `$pageview` | Catches passive browsing (the dominant pattern post-deadline) |
| Top 5 pages | PostHog HogQL `$pageview` grouped by `$pathname` | Same |
| Top 5 events | PostHog HogQL filtered to custom events | Same |
| Last 20 logins | Postgres `audit_events` | Ad-block-immune; explicit login is the truthful "they were here" signal |

### Backend

**`backend/app/services/posthog_read.py`** — three new helpers,
following the existing silent-failure + TTL cache pattern:

```python
@dataclass(frozen=True)
class DauPoint:
    date: str          # ISO YYYY-MM-DD
    count: int

@dataclass(frozen=True)
class PageTrend:
    path: str
    current_7d: int
    prior_7d: int

@dataclass(frozen=True)
class EventTrend:
    event_name: str
    current_7d: int
    prior_7d: int


async def get_dau_sparkline_14d() -> list[DauPoint]:
    """14 daily DAU counts, oldest → newest. Empty list on any failure."""
    # SELECT toDate(timestamp) AS day,
    #        count(DISTINCT distinct_id) AS dau
    # FROM events
    # WHERE event = '$pageview' AND timestamp > now() - 14 DAY
    # GROUP BY day ORDER BY day
    # Zero-fill missing days client-side (frontend renders 14 bars).

async def get_top_pages_7d(limit: int = 5) -> list[PageTrend]:
    """Top pages by 7d view count + prior 7d for trend. Empty list on fail."""
    # SELECT properties.$pathname AS path,
    #        countIf(timestamp >= now() - 7 DAY) AS current_7d,
    #        countIf(timestamp >= now() - 14 DAY
    #                AND timestamp < now() - 7 DAY) AS prior_7d
    # FROM events WHERE event = '$pageview'
    #   AND timestamp >= now() - 14 DAY
    # GROUP BY path ORDER BY current_7d DESC LIMIT 5

async def get_top_events_7d(limit: int = 5) -> list[EventTrend]:
    """Top custom events by 7d count + prior 7d. Empty list on fail."""
    # Same shape, with event filter:
    # AND event NOT IN ('$pageview', '$autocapture', '$identify')
```

Each helper is cached at the existing `_cache_set / _cache_get` layer
with a 5-minute TTL (the `BATCH_TTL_S = 5 * 60` constant). Cache key
incorporates the limit + helper name.

**`backend/app/services/audit.py`** — one new helper:

```python
async def get_recent_logins(
    session: AsyncSession,
    limit: int = 20,
) -> list[tuple[UUID, str, datetime]]:
    """Return [(user_id, name, login_at)] for the most recent logins
    across the whole pool. Joined to User so the panel doesn't need a
    second hop.
    """
    stmt = (
        select(AuditEvent.actor_user_id, User.name, AuditEvent.created_at)
        .join(User, User.id == AuditEvent.actor_user_id)
        .where(AuditEvent.event_type == "auth.login_succeeded")
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [(uid, name, aware_utc(ts)) for uid, name, ts in rows]
```

Note the `aware_utc()` coercion at the service-return site — per the
"Datetime rule" in CLAUDE.md, this guards against aiosqlite tzinfo
strip in tests.

**`backend/app/services/pulse.py`** (new) — thin assembler:

```python
async def get_site_pulse(session: AsyncSession) -> SitePulse:
    """Build all 4 widgets. Partial failure tolerated — any widget that
    fails returns an empty list, the rest still render.
    """
    # Each PostHog helper internally silent-fails. The audit query is
    # cheap and reliable; we let it raise (it's a normal DB error path).
    sparkline = await posthog_read.get_dau_sparkline_14d()
    top_pages = await posthog_read.get_top_pages_7d(5)
    top_events = await posthog_read.get_top_events_7d(5)
    logins_raw = await audit.get_recent_logins(session, 20)

    return SitePulse(
        dau_sparkline=[DauPoint(date=d.date, count=d.count) for d in sparkline],
        top_pages=[PageTrend(path=p.path, current_7d=p.current_7d, prior_7d=p.prior_7d) for p in top_pages],
        top_events=[EventTrend(event_name=e.event_name, current_7d=e.current_7d, prior_7d=e.prior_7d) for e in top_events],
        recent_logins=[
            RecentLogin(user_id=uid, name=name or "(no name)", login_at=ts)
            for uid, name, ts in logins_raw
        ],
    )
```

**`backend/app/api/admin.py`** — one new endpoint:

```python
@router.get("/pulse", response_model=SitePulse)
async def get_pulse(
    session: DbSession,
    _admin: AdminUser,
) -> SitePulse:
    """At-a-glance engagement panel for /admin Overview tab."""
    return await pulse.get_site_pulse(session)
```

**`backend/app/schemas/admin.py`** — new Pydantic models:

```python
class DauPoint(BaseModel):
    date: str
    count: int

class PageTrend(BaseModel):
    path: str
    current_7d: int
    prior_7d: int

class EventTrend(BaseModel):
    event_name: str
    current_7d: int
    prior_7d: int

class RecentLogin(BaseModel):
    user_id: UUID
    name: str
    login_at: datetime

class SitePulse(BaseModel):
    dau_sparkline: list[DauPoint]
    top_pages: list[PageTrend]
    top_events: list[EventTrend]
    recent_logins: list[RecentLogin]
```

### Frontend

**`frontend/src/lib/api/admin.ts`** — fetcher + types mirrored from
backend (same pattern as existing admin API calls).

**`frontend/src/lib/components/admin/SitePulsePanel.svelte`** (new) —
self-contained component:

- Fetches `/admin/pulse` on mount.
- Renders 4 widgets in a responsive grid:
  - Desktop (lg+): 2×2 grid
  - Mobile: stacked
- Sparkline reuses the bar-rendering pattern from the existing
  `EngagementSummary` card on `/admin/users/[id]`.
- Trend indicator derivation in component (not backend):
  - `prior_7d >= 10` → percentage delta with arrow
  - `prior_7d < 10` → absolute delta with arrow
  - `prior_7d == 0 && current_7d > 0` → "new" badge
  - `prior_7d > 0 && current_7d == 0` → "gone" badge (rarely visible
    since rows sort by current_7d)
  - `|delta| within 5%` → "→ flat" neutral
- Graceful empty states:
  - PostHog widgets return `[]` → render placeholder "PostHog data
    unavailable — `POSTHOG_PERSONAL_API_KEY` + `POSTHOG_PROJECT_ID` not
    set or upstream unreachable."
  - Logins empty → "No recent logins."

**`frontend/src/routes/admin/+page.svelte`** — mount the new panel
above the existing first card. Single import + single `<SitePulsePanel />`
tag.

### Trend display rules (frontend)

| State | Display | Color token |
|---|---|---|
| `current > prior > 10`, `delta_pct >= 5%` | `↑ +47%` | `text-success` |
| `current < prior`, `prior > 10`, `delta_pct >= 5%` | `↓ -22%` | `text-warning-text` |
| `prior > 0`, abs delta within 5% | `→ flat` | `text-base-content/55` |
| `prior == 0`, `current > 0` | `new` | `text-success` |
| `prior > 0`, `current == 0` | `gone` | `text-error` |
| `prior < 10`, `delta != 0` | `↑ +N` or `↓ -N` absolute | matches sign-based token |

`text-warning-text` not `text-warning` per the surface-token rule.

## Audit, safety, testing

**Audit:** none. Read-only endpoint, admin-only. No state change.

**Safety:**

| Concern | Mitigation |
|---|---|
| PostHog down | Each helper returns empty; panel renders partial data + a "data unavailable" line for affected widgets. |
| PostHog slow | 5-min TTL cache absorbs the first hit; subsequent admin reloads are sub-ms. |
| Audit table huge | `LIMIT 20` + index on `(event_type, created_at DESC)` (the existing index from the audit service). |
| Admin-only | Endpoint uses the existing `AdminUser` dependency. |

**Pytest cases** (`backend/tests/test_pulse.py` new + extend
`test_posthog_read.py`):

```python
async def test_get_dau_sparkline_returns_14_points_zero_filled(stub):
    ...

async def test_get_top_pages_includes_prior_7d_for_trend(stub):
    ...

async def test_get_top_events_excludes_pageview_and_autocapture(stub):
    ...

async def test_get_recent_logins_orders_by_created_at_desc(session):
    ...

async def test_get_site_pulse_partial_posthog_failure(session, monkeypatch):
    # All PostHog helpers return []; pulse assembler still returns a
    # SitePulse with logins populated and posthog widgets empty.
    ...
```

**Frontend test:** none required — the panel reads a typed response
and renders. Existing component tests still pass.

## Risks

- **Empty top-pages on day 1-2** — with only 2 days of tournament data,
  the 7d / prior-7d split is degenerate. Pages with no prior history
  show `new`, which is correct but not very informative. Worth knowing.
- **`$pathname` precision** — PostHog records the raw URL path. SvelteKit
  dynamic routes (`/results/[fixture_id]`) appear as fully expanded
  paths (`/results/abc123`, `/results/def456`, …). This makes the top-
  pages list noisier than it could be. A future improvement could
  normalize via `properties.$current_url` parsing. Out of scope here.
- **PostHog quota** — three new HogQL queries per `/admin/pulse` call,
  cached 5 min. Negligible at this scale.
- **Sparkline bar magnitudes** — `max(1, max(values))` is the divisor
  so a sparkline with all-zero days doesn't divide by zero. Existing
  pattern (from `EngagementSummary` card).
