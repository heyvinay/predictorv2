# Usage & Adoption dashboard — `/admin/usage`

**Date:** 2026-07-13
**Status:** Implemented (this session) — pending version bump + deploy
**Author:** Vinay (via brainstorming + iterative wireframe review)
**Slice:** 1 of 1

## Summary

A new, dedicated admin sub-page (`/admin/usage`) answering "how is the
app actually being used, and what isn't working" — frequent-visitor
ranking, feature adoption with recency, retention, and stickiness. A
deliberately separate, more analytical surface from the existing
**Site Pulse** panel on the Overview tab, which stays exactly as-is
(narrow/operational, no drill-downs, no time controls) per its own
2026-06-13 design doc.

The scope decision — new page vs. extending Site Pulse — was made
explicitly with the user rather than assumed; see the queued feedback
thread this session, where a wireframe (`scratchpad/
usage_adoption_wireframe.html`) was iterated live against real
production PostHog data before any backend code was written.

## Scope (in)

1. **Global control bar** — time range (`1h|24h|7d|30d|all`),
   granularity (`hour|day|week`, auto-picked per range), segment
   (`all|atlas|jmfa|neither`), compare-to-previous-period toggle.
2. **Funnel strip** — reuses the existing `GET /admin/broadcasts/
   audience` counts. No new backend for this widget.
3. **KPI scorecard** — Active users, Sessions/user, New vs returning,
   Stickiness (DAU/MAU %), each with a previous-period delta.
4. **Active users trend + Time of day** — both tied to the range
   selector; time-of-day is a 24-hour histogram, not a fixed 7-day
   window.
5. **Weekly retention** — cohort heatmap (diverging error→warning→
   success blend through DaisyUI's own theme tokens), capped at 5
   most-recent cohorts × 5 week-offsets.
6. **Engagement frequency** — active-days histogram with an explicit
   dormant (0-day) bucket, computed by diffing PostHog's "who fired
   ≥1 event" against the DB's full submitter population.
7. **Feature adoption** — 8 hand-curated features (`FEATURE_GROUPS` in
   `usage.py`), each with breadth %, "last used" recency, a `frozen`
   flag for entry-phase-only features (Smart Fill), a `rarely_used`
   flag under 15%, and a click-through adopter drawer.
8. **Uncategorized events** — self-surfacing list of any event
   PostHog has seen that isn't in `FEATURE_GROUPS` or the ambient-
   event exclusion list. Verified against LIVE production PostHog
   during design — caught 5 real events (legacy Tally feedback-panel
   events + ops/test noise) that a purely code-derived model missed.
9. **Power users table** — three modes (Most active / Least active /
   Never engaged), sortable, click-through to a lightweight per-row
   drawer that deep-links to the existing `/admin/users/[id]`.

## Scope (out)

- CSV export.
- A full custom segmentation / event-query builder (PostHog's own UI
  already does this — confirmed via live browser check that the
  user's only PostHog dashboard is the unused default template, so
  there's nothing to duplicate, but also no appetite to rebuild a
  query builder).
- Revenue metrics (not applicable to this product).
- A 7×24 day×hour punch-card heatmap — at ~150-180 users, most cells
  would be near-zero; day-of-week and hour-of-day are kept as two
  separate marginal distributions instead (each has enough density to
  be trustworthy).
- Real-time push/auto-refresh — range-driven refetch + the existing
  5-minute PostHog TTL cache is the model, matching Site Pulse.
- A per-user "features touched" + "recent activity" breakdown inside
  the drawer — the user-drawer shows only the fields already on its
  table row (logins, active days, sessions, last seen) plus a link to
  the full `/admin/users/[id]` profile, rather than duplicating that
  page's rendering.

## Architecture

### Data sources

| Section | Source |
|---|---|
| Funnel strip | Postgres, via existing `broadcast.count_all_audiences()` |
| KPIs, trend, time-of-day, retention, frequency, adoption, uncategorized | PostHog HogQL, via new `posthog_read.py` functions |
| Power users' logins | Postgres `audit_events`, via new `audit.get_login_counts_since()` |
| Power users' active days/sessions/last_seen | Hybrid — active_days/sessions from PostHog; `last_seen_at` from `User` (always available, no PostHog dependency) |

### Backend

**`app/services/posthog_read.py`** — 13 new functions, all following
the module's existing silent-fail + TTL-cache + `_hogql()` transport
pattern: `get_active_users_series`, `get_unique_active_users`,
`get_stickiness`, `get_sessions_per_user`, `get_new_vs_returning`,
`get_activity_by_hour`, `get_weekly_retention_cohorts`,
`get_engagement_frequency`, `get_unique_users_by_event`,
`get_all_events_last_seen`, `get_active_days_and_sessions_for_users`,
`get_adopters_for_events`, plus a public `is_configured()` wrapper.

**`app/services/audit.py`** — `get_login_counts_since()`, mirroring
`last_login_for_users()`'s shape but counting rows.

**`app/services/usage.py`** (new) — the assembler, mirroring
`pulse.py`'s role. Holds `FEATURE_GROUPS` (the authoritative
event→feature map — see the CLAUDE.md convention this establishes)
and `AMBIENT_EVENTS` (the deliberate-exclusion list). Resolves the
segment to a DB user-id set, resolves the submitter population (the
adoption denominator — "people actually playing," not all registered
users), and assembles every widget. Partial-failure contract: every
PostHog-sourced field degrades to empty/0/None; DB-sourced fields
(funnel, `last_seen_at`) always render. `UsageReport.posthog_available`
lets the frontend show one unified banner.

**`app/api/admin.py`** — two new admin-only routes: `GET /admin/usage`
(the whole report) and `GET /admin/usage/features/{key}/adopters`
(the feature-drawer drill-down).

### Frontend

**`frontend/src/routes/admin/usage/+page.svelte`** (new) — implements
every section above using the app's real DaisyUI classes (not a
hand-rolled design system — an earlier iteration used custom CSS
which the user correctly flagged as not matching the app's actual
`toggle toggle-primary` component). Retention-cell coloring routes
through DaisyUI's own `hsl(var(--er))`/`hsl(var(--wa))`/`hsl(var(--su))`
tokens rather than hardcoded hex, mirroring the Group Stage Winner
Card's theme-aware color convention.

**`frontend/src/lib/api/admin.ts`** — `getUsageReport()` +
`getUsageFeatureAdopters()` fetchers and mirrored TS types.

**`frontend/src/routes/admin/+layout.svelte`** — 9th nav tab
(`Usage`), same pattern as the existing 8.

### Approximations, documented rather than hidden

- **Feature adopter count** uses `max()` across a feature's event
  list rather than the true set-union (which would need one more
  HogQL query per feature). A documented lower bound, not silently
  wrong.
- **"New vs returning"** defines "new" as this `distinct_id`'s true
  first-ever PostHog pageview falling inside the window — correct,
  but only as good as PostHog's retained event history.
- **Retention cell text contrast** uses a fixed percentage threshold
  (`<35 or >85 → white, else dark`) tuned against the wireframe's
  measured luminance rather than a live per-cell computation — a
  reasonable v1 approximation to verify visually post-deploy.

## Risks

- **Adoption denominator drift.** If `FEATURE_GROUPS`' event lists
  ever drift from what actually fires (as happened once already this
  session — three "simulator_*" events I believed dead from a static
  `grep` turned out to fire live), adoption % would undercount. The
  Uncategorized-events row is the backstop, not a full guarantee —
  it only catches events outside the map, not stale entries inside it.
- **PostHog quota** — the page issues ~15 HogQL queries per load
  (more than Site Pulse's 3), each cached 5 minutes. Negligible at
  this scale but worth knowing if PostHog's free-tier query limits
  ever become relevant.
- **Retention/stickiness need daily+ granularity** — both show an
  explicit "needs a day+" state on sub-2-day ranges rather than a
  misleading number from one data point.

## Follow-ups (not done this session)

- Version bump (`frontend/package.json` + lockfile self-reference +
  `backend/pyproject.toml`) and a `changelog.json` entry — deliberately
  deferred per the "never bump versions in anticipation of shipping"
  rule; do this at actual ship time.
- Visual QA in both themes (light/hybrid + dark/premium-night) once a
  dev server is available — the retention-heatmap text-contrast
  threshold above is the one piece most worth a live look.
- `docker-compose exec backend alembic ...` is NOT needed — this
  feature adds no new DB columns or tables, only new service functions
  and read-only queries.
