# Dashboard widgets — Daily MVP + Personal Trail + Pool Distribution — Design

**Date:** 2026-06-22
**Status:** Pending user review
**Wireframe:** [docs/superpowers/wireframes/2026-06-22-dashboard-widgets.html](../wireframes/2026-06-22-dashboard-widgets.html)
**Scope:** Frontend-heavy. Three new components below the existing dashboard grid, three new backend endpoints. Ships in the same PR as the [leaderboard race redesign](2026-06-22-leaderboard-race-neighbourhood-design.md).
**Sister plan:** [2026-06-22-leaderboard-race-redesign.md](../plans/2026-06-22-leaderboard-race-redesign.md) — runs alongside this; both are subagent-driven.

## Purpose

The V4 Dashboard at `/` currently shows fixtures and the mini-leaderboard but lacks the daily-pulse signals that bring people back to the page on a non-matchday. Three additions surface the *temporal* texture of the tournament — who scored the most yesterday, where you're trending vs the pool, who's clustered near you in points.

All three are derivable from existing data (`LeaderboardSnapshot` + leaderboard rows). No schema migration. They respect the blind-pool gate.

## Composition

A NEW full-width region appears **below** the existing two-column grid in [DashboardV4.svelte](../../../frontend/src/lib/components/dashboard/v4/DashboardV4.svelte). Both the LEFT (Main) and RIGHT (Side) columns are completely untouched — every existing widget keeps its current position.

```
┌──────────────────────────────────────────────────────────┐
│ Existing header (unchanged)                              │
├──────────────────────────────────┬───────────────────────┤
│ LEFT — fixtures (unchanged)      │ RIGHT — mini lb       │
│ AnnouncementHero                 │ MiniLeaderboard       │
│ FixturesTable · Matchday         │ MoversCard            │
│ FixturesTable · Upcoming         │                       │
│ ResultsTable                     │                       │
└──────────────────────────────────┴───────────────────────┘
─── thin gold horizontal divider (visual zone marker) ────
┌──────────────────────────────────────────────────────────┐
│ ① Daily MVP — full-width, 5 floating chips               │
├──────────────────────────────────────────────────────────┤
│ ② Personal Trail — identity / chart / stat               │
├──────────────────────────────────────────────────────────┤
│ ③ Pool Distribution — histogram                          │
└──────────────────────────────────────────────────────────┘
```

The stacking order reads as a narrative: editorial first (pool-wide MVP), then personal (your trail vs average), then positional (your local cluster). Broad → specific.

## Goals

- Three new "daily pulse" widgets that make the dashboard worth opening on a non-matchday.
- Zero changes to the existing two-column grid — no relocations, no rewording, no prop changes.
- All three respect blind-pool (hidden pre-deadline) and degrade gracefully (each widget collapses to nothing when its data is unavailable).
- Mobile-friendly: each widget reflows for narrow viewports without media-query branches.

## Non-goals

- A separate `/insights` route. The widgets live on the dashboard.
- Replacing or moving any existing widget. `MoversCard` does NOT move; the new MVP widget is distinct ("biggest day-scorer" not "biggest rank-mover").
- Real-time updates within a day. Widgets refresh on dashboard mount and via the same 60s leaderboard cache cadence used elsewhere.
- Customisation (which widgets show, in what order). Out of scope for v1.
- Bundling with the leaderboard race redesign as a single plan. They share a PR but stay as two specs + two plans for reviewability.

## Widget ① — Daily MVP

A row of 5 floating chips showing the top scorer for each of the last 5 days (most-recent-first). Today's chip is gold-tinted; older chips share the standard surface chrome.

```
┌────────────────────────────────────────────────────────────────────┐
│ DAILY MVP — last 5 days                                            │
├──────────────┬──────────────┬──────────────┬──────────────┬────────┤
│ Today Jun 22 │ Jun 21       │ Jun 20       │ Jun 19       │ Jun 18 │
│ Lionel Z.    │ Brian A.     │ Jeffrey F.   │ Kevin V.     │ Christian B.
│ +18 pts ▲12  │ +16 pts ▲4   │ +14 pts ▲8   │ +13 pts ▼2   │ +15 ▲6 │
└──────────────┴──────────────┴──────────────┴──────────────┴────────┘
```

### Rules

- **Fixed at 5 days.** No scroll bar, no "show more." Older history lives on the leaderboard's per-entry trajectory chart.
- **Layout:** `flex: 1 1 200px; min-width: 180px;` chips inside a `flex-wrap: wrap` container. On desktop (~1180px container) chips lay out in a single row. On mobile they wrap to 2–3 rows.
- **Chip content:** Date (today is "Today · Jun 22", older is "Jun 21"). Name uses the same `rowDisplayName()` rule as the leaderboard — Person — Entry when multi-owner, just Person otherwise. Day-points in mint. Rank delta with ▲ gold for up, faded red ▼ for down.
- **Tie-break:** equal day-points → lower current rank wins (one MVP per day, deterministic).
- **Zero-points day:** chip omitted entirely. If all 5 days are zero-points, whole widget collapses.
- **Click a chip:** opens the existing `EntryDrawer` for the MVP's entry.

### Backend

`GET /api/leaderboard/daily-mvps` — no query params. Returns:

```python
class DailyMvp(BaseModel):
    captured_date: date
    subject_entry_id: str
    user_name: str
    entry_name: str
    day_points: int
    rank_delta: int  # positive = climbed, negative = dropped

class DailyMvpsResponse(BaseModel):
    mvps: list[DailyMvp]      # ≤ 5 entries, newest-first
    generated_at: datetime
```

Derived from `LeaderboardSnapshot` day-over-day diffs over the last 5 days. Cached 60s.

## Widget ② — Personal Trail

A horizontal strip showing the user's cumulative points trajectory vs the pool average over the tournament. Signed-in users only — hidden for anonymous visitors.

```
┌───────────────────────────────────────────────────────────────────┐
│ YOUR TRAIL — points vs pool average                               │
├───────────┬──────────────────────────────────────────┬────────────┤
│ Vinay 3rd │ ╱╱╲╱╱╲╱  pool avg (grey)  / you (gold)  │ +47        │
│ #27 · 30d │   ╱╱╱╱╲╱╲╱╱╱                            │ vs pool avg│
└───────────┴──────────────────────────────────────────┴────────────┘
```

### Layout

Three columns at desktop: identity (1fr) / sparkline (2.5fr) / stat (0.8fr). On mobile (<640px), stacks vertically to identity-row → sparkline → stat-row.

### Rules

- **Two lines on the sparkline:** user's cumulative points in gold (`#D4AF37`), pool-average cumulative points in `--ink-faint` grey.
- **Stat:** difference between your latest total and the pool average. Mint if positive ("+47"), red if negative ("−12").
- **Multi-entry users:** show the first 2 strips stacked with a 4px gap; render a "+N more" link if the user has 3+ entries. Click expands to show all entries; collapse-back via a top-right icon. Persistence not required — every dashboard load starts collapsed.
- **Day-1 / very-early-tournament:** if there are fewer than 3 snapshot points, render a faint "It's early — check back tomorrow" caption instead of a near-flat chart.
- **Pre-deadline:** widget hidden entirely (the pool average can't be computed before predictions lock).

### Backend

`GET /api/leaderboard/personal-trail` — no query params. Returns the requesting user's entries:

```python
class TrailPoint(BaseModel):
    captured_date: date
    your_points: int
    pool_avg_points: float

class EntryTrail(BaseModel):
    entry_id: str
    entry_name: str
    current_rank: int
    current_gap: float          # your_points - pool_avg_points (today)
    points: list[TrailPoint]

class PersonalTrailResponse(BaseModel):
    entries: list[EntryTrail]   # one per submitted entry the user owns; sorted by current_rank ASC
    generated_at: datetime
```

Reads `LeaderboardSnapshot` for the user's own entries plus a daily aggregate (mean total_points across eligible entries per day). Cached 60s per user.

## Widget ③ — Pool Distribution

A small histogram showing the local cluster of entries around the user's current points total. Helps gauge how reachable the next rank is.

```
┌─────────────────────────────────────────────────┐
│ POOL DISTRIBUTION — around your points total    │
│ 7 entries within 4 pts of you. Next rank: 2 pts │
│                                                 │
│ ▁▂▃▄▅▆▇█▇▆▅▄▃                                  │
│ −5pt    −2pt    YOU    +2pt    +5pt             │
└─────────────────────────────────────────────────┘
```

### Rules

- **Bins:** 1pt wide; default window is ±5pt around the user's current total (11 bins).
- **Sparse-pool fallback:** if fewer than 2 entries fall within ±5pt, widen the window to ±10pt.
- **Bar colour:** user's bar bright gold (`#D4AF37`); ±2pt neighbours `gold-mid`; outside that `ink-ghost` grey.
- **Next-rank marker:** dashed mint vertical line at the points value where the next-higher rank starts. Labelled with the rank number ("#26").
- **Caption above the chart** (dynamic):
  - default: "X entries within Y points of you. The next rank is Z points away."
  - user at #1: "Nobody within X points of you above. Closest pursuer N points behind."
  - user alone at their score: "You're alone at this points total — N points to the next-closest entry."
- **Pre-deadline:** hidden entirely.

### Backend

`GET /api/leaderboard/pool-distribution` — no query params. Returns:

```python
class DistBin(BaseModel):
    points_delta: int            # offset from user's current_points; can be negative
    count: int

class PoolDistributionResponse(BaseModel):
    user_points: int
    window_size: int             # 5 by default; 10 if widened
    bins: list[DistBin]          # always non-empty (includes the user's own bin)
    next_rank_points_away: int | None  # null if user is at #1
    next_rank_position: int | None     # the rank label ("#26")
    near_count: int              # entries within ±window_size pts
    caption: str                 # composed server-side, see "Caption above the chart"
    generated_at: datetime
```

Pure aggregate from the existing leaderboard rows. ~50ms cold.

## Architecture

### Frontend

**Files modified:**

- [frontend/src/lib/components/dashboard/v4/DashboardV4.svelte](../../../frontend/src/lib/components/dashboard/v4/DashboardV4.svelte) — append the new full-width region below the existing `<div class="grid ... grid-cols-[1.55fr_1fr]">` block. Two-column grid stays unchanged.
- [frontend/src/lib/types/leaderboard.ts](../../../frontend/src/lib/types/leaderboard.ts) — extend with `DailyMvp`, `DailyMvpsResponse`, `TrailPoint`, `EntryTrail`, `PersonalTrailResponse`, `DistBin`, `PoolDistributionResponse`.
- [frontend/src/lib/api/leaderboard.ts](../../../frontend/src/lib/api/leaderboard.ts) — add `getDailyMvps()`, `getPersonalTrail()`, `getPoolDistribution()`.

**Files created:**

- `frontend/src/lib/components/dashboard/v4/DailyMvpStrip.svelte` — owns its `getDailyMvps()` fetch; renders 5 floating chips. Collapses to nothing on empty.
- `frontend/src/lib/components/dashboard/v4/MvpChip.svelte` — one chip. Pure presentation. Click dispatches `open` event upward.
- `frontend/src/lib/components/dashboard/v4/PersonalTrailStrip.svelte` — owns `getPersonalTrail()`; renders the user's entries (first 2 + expand for 3+).
- `frontend/src/lib/components/dashboard/v4/PoolDistribution.svelte` — owns `getPoolDistribution()`; renders the histogram.

### Backend

**Files modified:**

- [backend/app/api/leaderboard.py](../../../backend/app/api/leaderboard.py) — add 3 new endpoints + Pydantic schemas.

**Files created:**

- `backend/app/services/dashboard_stats.py` — all three derivations live here (single module; they share data-loading patterns and a common entry-eligibility filter):
  - `compute_daily_mvps(session) -> list[DailyMvp]`
  - `compute_personal_trail(session, user_id) -> list[EntryTrail]`
  - `compute_pool_distribution(session, user_id) -> PoolDistributionResponse`
- `backend/tests/test_dashboard_stats.py` — pytest cases for all three derivations.

## Mobile (≤640px)

- Daily MVP chips wrap (flex-wrap default) — typically 1-2 per row at 375px.
- Personal Trail stacks: identity row → sparkline → stat row.
- Pool Distribution histogram bars are narrower; x-axis labels reduce to `−5pt / YOU / +5pt` (drops the intermediate −2pt / +2pt markers).
- All three widgets remain full-width within the container — they don't overlap or compete for space.

## Edge cases

- **Anonymous (signed-out) user:** Daily MVP shows; Personal Trail + Pool Distribution hidden.
- **Signed-in with zero entries:** Daily MVP shows; Personal Trail + Pool Distribution hidden.
- **User holds the leader's rank (#1):** Pool Distribution caption switches to "Nobody within X points above." Next-rank marker omitted.
- **User tied with one other entry on points:** Pool Distribution caption: "You're tied with N entries at this score."
- **Day-1 of tournament (very few snapshots):** Personal Trail renders the "It's early — check back tomorrow" caption variant. Daily MVP renders only the days that have data.
- **An endpoint 500s:** the failing widget collapses silently; other two widgets render. Whole-region collapse only when ALL three return empty/error.

## Versioning

Ships in the same release/PR as the [leaderboard race redesign](2026-06-22-leaderboard-race-neighbourhood-design.md). Single combined version bump (minor — feature addition). Single combined changelog entry covering both:

```
"Leaderboard 'The Race' tab redesigned with story cards, neighbourhood
chart and cohort race. Dashboard gains three new widgets below the
existing grid: Daily MVP, Personal Trail, and Pool Distribution."
```

## Tests

### Frontend (vitest)

- Pool Distribution caption-builder pure function (`buildDistributionCaption(state)`) — covers the 4 caption variants (default / leader / alone / tied).
- `composeRankDelta()` helper for MVP chip (returns `▲ N` / `▼ N` / `—` string) — table-driven.
- Multi-entry collapse logic for Personal Trail (`firstTwoPlusExpand(entries, expanded)` returns the slice + remaining count) — table-driven.

### Backend (pytest)

- `test_dashboard_stats.py`:
  - Daily MVP: tie-break (lower rank wins); zero-points day omitted; aware-UTC `generated_at`.
  - Personal Trail: pool-average math (mean across eligible entries per day); blind-pool returns empty list; multi-entry returns all of the user's entries.
  - Pool Distribution: sparse-pool widens window from ±5 to ±10; user at #1 → null next-rank; user tied → near-count includes themselves only in their own bin's `count`.

### Manual

- 375px mobile: verify Daily MVP chips wrap cleanly; Personal Trail stacks; histogram bars don't crush.
- Browser visual check on prod after deploy.

## Rollout

This widget set rides on the same PR as the leaderboard race redesign (per the **Bundle** decision). Two specs, two plans, one branch, one PR, one deploy, one version bump.

If the deploy needs to be reverted, the race redesign and dashboard widgets revert together. Both sit on top of the existing V4 leaderboard / V4 dashboard layouts and don't change any pre-existing user-visible surface — the only "uninstall" risk is the new widgets/region disappearing, which is graceful.

## Out of scope, deferred follow-ups

- Customisation (which widgets show, in what order, persistence).
- "Streak of the week" / weekly MVP roll-ups.
- Pool Distribution comparing against a peer cohort (Atlas-only / JMFA-only) rather than the whole pool.
- Daily MVP chip showing the user's entry too when the user IS the MVP (today's chip already does this implicitly; future: a faint "you" pip).
- Click-through on Pool Distribution bars to open a list of entries at that points value.

## References

- [Sister design — leaderboard race redesign](2026-06-22-leaderboard-race-neighbourhood-design.md)
- [Memory: V4 leaderboard rebuild](../../../../../../.claude/projects/C--Users-vinay-OneDrive---Atlas-Insurance-PCC-Projects-predictorv2/memory/predictorv2_results_leaderboard_rebuild.md)
- [Memory: SWR leaderboard cache invalidate vs expire](../../../../../../.claude/projects/C--Users-vinay-OneDrive---Atlas-Insurance-PCC-Projects-predictorv2/memory/predictorv2_v2173_live_polling_swr.md)
- [Memory: DaisyUI surface elevation ladder](../../../../../../.claude/projects/C--Users-vinay-OneDrive---Atlas-Insurance-PCC-Projects-predictorv2/memory/feedback_daisyui_surface_ladder.md)
- [CLAUDE.md — V4 Dashboard section + datetime rule + eligible-entries filter]
