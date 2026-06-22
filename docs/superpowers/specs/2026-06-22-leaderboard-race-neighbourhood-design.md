# Leaderboard "The Race" — Neighbourhood focal view + Story cards grid — Design

**Date:** 2026-06-22 (mid-tournament, group stage finishing, KO underway — 40 of 104 matches played)
**Status:** Pending user review
**Wireframe:** [docs/superpowers/wireframes/2026-06-22-leaderboard-race-neighbourhood.html](../wireframes/2026-06-22-leaderboard-race-neighbourhood.html) · also published at the session-shared Artifact URL
**Scope:** Frontend-heavy. One new backend endpoint that returns the full story set.

## Composition

The new race tab stacks five regions vertically:

```
┌─────────────────────────────────────────────────────────┐
│ ① STORY CARDS GRID — 4 editorial cards                  │
│    Biggest climb · Steepest fall · Closest race · Streak│
├─────────────────────────────────────────────────────────┤
│ ② CHAMPION SURVIVAL — gauge + top-pick chips            │
├─────────────────────────────────────────────────────────┤
│ ③ VIEW PILLS — Around me · Top 10 · Top 25 · cohorts    │
├─────────────────────────────────────────────────────────┤
│ ④ NEIGHBOURHOOD BUMP CHART                              │
│    focal slice + match-result markers + minimap strip   │
├─────────────────────────────────────────────────────────┤
│ ⑤ COHORT RACE — Atlas vs JMFA vs Guests median rank     │
└─────────────────────────────────────────────────────────┘
```

The 183-line "Full field" chart is **removed entirely**. The race tab is no longer about seeing every entry's trajectory simultaneously — that was never readable. Standings tab continues to list all 183 entries, so no entry data is hidden from the user; just visualised differently.

Each region is independently collapsible to nothing when its data isn't available (pre-tournament, no qualifying stories, no champion picks committed). The page degrades gracefully — never shows placeholder boxes.

## Purpose

The current `/leaderboard` → **The Race** view ([RaceChart.svelte](../../../frontend/src/lib/components/leaderboard/v4/RaceChart.svelte)) renders all 183 eligible-entry trajectories as overlapping lines on a single bump chart. The result is unreadable spaghetti — bump charts top out around 15–20 lines perceptually, and we're ~10× past that. Two gold lines (the user's entries) and one mint line (the leader) carry signal; the other 180 grey threads are visual noise.

Replace the global-spaghetti chart with **two complementary surfaces**: a 2×2 **story cards grid** on top that names the day's drama (climb / fall / closest race / streak), and a **focal bump chart** below it centred on the viewer's rank. Together they answer the two questions people actually ask of a leaderboard race view: *what's happening in the pool right now* (top) and *where do I sit in it* (bottom).

## Goals

- Bump chart answers "where am I? who's near me? am I catching anyone? is anyone catching me?" in one glance (region ④).
- Story cards answer "what's interesting in the pool today?" without the user having to read the chart (region ①).
- Champion Survival answers "is my bracket still in play?" at a glance — surfaces the tournament-shape question hidden in everyone's predictions (region ②).
- Cohort Race answers "is Atlas / JMFA winning?" — the tribal angle a friends-and-colleagues pool naturally wants (region ⑤).
- Match-result markers on the chart's date axis turn rank drops into stories — *that's the day Brazil lost, that's why I dropped* (region ④ enhancement).
- Readable on 375px mobile (cards stack to one column; chart regions are independently scrollable if dense).
- Inherits the existing V4 leaderboard gate; no new feature flag required.
- Standings tab remains the authoritative all-entries surface.

## Non-goals

- Preserving the 183-line spaghetti chart. Removed entirely. Power users who want every entry visible at once use the Standings table.
- A Horizon Strip (Option C from brainstorming). Defer indefinitely — too novel for the cost.
- Replacing the V3 leaderboard chart. V3 is being retired; we don't touch it.
- Snapshots endpoint changes. The existing [`GET /api/leaderboard/snapshots`](../../../backend/app/api/leaderboard.py) already returns every trajectory; we only change which we render.
- Real-time intra-day rank movement. Stories are computed against daily snapshots, same cadence as the existing chart.
- A dedicated `/insights` page. The 4-card grid is folded directly into the race tab; no separate route.

## View modes (pill toolbar)

Six mutually exclusive pills above the chart. The active pill controls which subset of trajectories renders.

| Pill | Description | Trajectory selection |
|---|---|---|
| **Around me** *(default when signed in)* | 7 trajectories (viewer ± 3 ranks). Leader rendered as an 8th dashed ghost line when outside the slice, with a y-axis break (`⋮`) above the slice indicating compression. | User's best-ranked entry ± 3 ranks + leader if outside the ±3 window. |
| **Top 10** *(default when signed out)* | Top-10 ranked entries; user's entries always included (8th–11th line if user is outside top 10). | `rank ≤ 10 ∪ {user's entries}`. |
| **Top 25** | Top-25 + user's entries. Mobile renders this as a vertically-scrolling chart. | `rank ≤ 25 ∪ {user's entries}`. |
| **Atlas** / **JMFA** / **Guests** | Three separate pills, one per cohort. `User.employer` → `atlas` / `jmfa` / `neither`\|null. Matches the existing Standings cohort filter exactly. User's entries always included if they fall outside the active cohort. | `cohort filter ∪ {user's entries}`. |

**Total pill count = 6.** The "Full field" pill is deliberately removed — the 183-line view was the problem we're solving. On mobile the pills overflow horizontally with `snap-x snap-mandatory` per the scrollable-pills pattern; on desktop they fit on one row.

**Anonymous (signed-out) default**: "Top 10" — there is no "viewer" to centre on.

The pill state is **not persisted** across page loads. Each visit starts at default. Persisting feels powerful but introduces a question ("why is my view stuck on Atlas only?") that's higher-friction than re-clicking a pill.

## Chart rendering rules (delta vs current `RaceChart.svelte`)

The existing chart's geometry, hover/tip, label clustering, sparkline col, and dashed-line-for-leader logic all stay. Only **which** trajectories render changes.

- **Trajectories not in the active slice are removed from the SVG entirely** (not faded). Fading them is what gives the current chart its spaghetti texture.
- **The y-axis (rank) is zoomed to the active slice's range** with a 1-rank padding above and below. "Around me" shows `min(slice rank) − 1 … max(slice rank) + 1`; "Top 10" shows `1 … 11` or `1 … <user's rank + 1>` if user is outside.
- **When a slice includes a leader-ghost line at #1 and the focal entries are at e.g. #25-#30**, render the leader's dashed line at the **top of the chart** with an explicit `⋮ from #1` y-axis-break marker between it and the focal slice. This keeps the leader visible (the whole point of the ghost) without compressing the focal slice into the bottom 20% of the chart height. Implement as two SVG groups stacked vertically with a small gap and a styled `⋮` glyph between them.
- **The minimap strip below the chart** (new) shows where the visible slice sits in the full 1-183 field. Width = full-field width; the slice is a gold-tinted band; the leader and the user's entries are pinpointed as small dots. The minimap is a thin (~16px) strip — informational, not interactive.
- **Pill changes are animated**: 250ms transition on y-axis rescale + line fade-in/out, so switching feels like a smooth zoom rather than a chart swap. CSS transitions on the SVG transform, no JS animation library.

### Match-result markers (chart annotations)

Pin the **most-impactful FINISHED knockout matches** to the chart's date axis as small chips with a faint vertical dashed line running up through the chart. Each marker shows a one-line score summary (`🇧🇷 2-1 🇦🇷`) and on hover/tap opens a tooltip with "pool impact" details (median rank shuffle, % of pool who picked the loser).

- **Marker density cap:** at most 3 markers visible at any time, picked by "shuffling impact" score (how much the match shuffled ranks across the pool). Beyond that, additional markers cluster into a `+N more` chip.
- **Visual distinction for upsets:** when the match outcome contradicted the pool's pre-kickoff consensus (>60% of the pool picked the losing side), the marker renders in `gold-soft` background instead of neutral `bg-100` — calling out the moments that hurt the pool the most.
- **Group-stage exclusion:** group matches are too numerous (72 of them) and individually too low-impact to merit chart-level annotation. KO-only.
- **Data source:** a new derivation in [backend/app/services/race_impact.py](../../../backend/app/services/race_impact.py) `compute_match_impact(fixture, snapshots)`. Reads existing data — no schema change.

When the date range shown by the chart doesn't include any annotated matches (e.g. early-tournament view), the marker layer is empty. No placeholder.

## Champion Survival panel

A horizontal panel between the story cards and the view pills, showing **how much of the pool's collective "champion pick" is still alive** in the tournament. Two regions side-by-side: a radial gauge (large %) on the left, and a row of team chips on the right showing the top 5 most-picked champions with each team's `alive` / `eliminated` state.

```
┌────────────────────────────────────────────────────────────┐
│   ╭───────╮    124 of 183 entries still hold a champion    │
│   │ 68%   │    pick alive in the tournament. Three teams   │
│   │ alive │    account for 71% of those.                   │
│   ╰───────╯                                                │
│              🇧🇷 Brazil · 32 alive    🇦🇷 Argentina · 28    │
│              🇫🇷 France · 28 alive    🏴 England · 22 OUT   │
│              🇪🇸 Spain · 18 OUT      +8 more teams         │
└────────────────────────────────────────────────────────────┘
```

### Behaviour

- **Update cadence:** recomputed after every KO match completion. Cached for 5 minutes (same TTL as story stories endpoint).
- **Team chips clickable:** opens a side panel listing the entries that picked that team, sorted by current rank. (No new route — opens within the existing `EntryDrawer` pattern with a `cohort` variant.)
- **Pre-knockout:** the panel renders but every team chip is "alive" — useful pre-tournament to see the pool's collective bet, even before any eliminations.
- **Tournament end:** when the final is played and the winner is known, the panel transforms into a "These entries picked the champion 🏆" callout with the surviving entry chips. Still useful as a record of who got it right.
- **Pre-deadline:** hidden entirely (blind-pool rule). The panel's data is the entries' bracket picks, which must stay private until predictions lock.

### Backend

New endpoint:

```python
@router.get("/champion-survival", response_model=ChampionSurvivalResponse)
async def champion_survival(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ChampionSurvivalResponse:
```

```python
class ChampionSurvivalResponse(BaseModel):
    alive_count: int                       # entries with a live champion pick
    total_count: int                       # entries with any submitted champion pick
    teams: list[ChampionTeamCount]         # top 8 picks (alive + eliminated)
    generated_at: datetime                 # aware-UTC

class ChampionTeamCount(BaseModel):
    team_code: str                         # FIFA 3-letter code
    team_name: str                         # display name (post `SHORT_NAMES` mapping)
    count: int                             # entries that picked this team
    alive: bool                            # team still in the tournament
```

Pulls from `TeamPrediction` rows with `stage='winner'`, joined against `Fixture` to detect alive-vs-eliminated. Eligible-entry filter via `eligible_entry_ids_select()` per the v2.161.0 invariant.

## Cohort Race chart

Below the focal chart, a separate small bump chart plots **median rank** of each cohort (Atlas / JMFA / Guests) over time. Three lines, distinct colours from the chart-line palette (NOT the existing semantic tokens, since gold/mint/red are already taken):

- **Atlas:** `#38bdf8` (sky blue) — corporate/clean
- **JMFA:** `#a78bfa` (violet) — distinct from Atlas's blue
- **Guests:** `#94a3b8` (slate) — neutral, non-tribal

### Behaviour

- **Y-axis is inverted** so "up is good" (rank #1 at top). Helps the chart read intuitively without needing a legend explanation.
- **Median (not mean) rank** — large pool sizes with employer skew (Atlas 83 vs JMFA 14) would let outliers dominate the mean. Median is more honest about "where is a typical Atlas entry sitting."
- **Same x-axis range** as the focal chart above — tournament start to today. The two charts are visually aligned so a date column on the focal chart matches the same column below.
- **Click-through:** clicking a cohort's right-edge label applies that cohort's filter pill to the focal chart above. Two visualisations of the same data, the cohort label is the bridge.
- **Annotations:** when a cohort makes a significant move (e.g. Atlas crosses below median rank #75), pin a small annotation chip with the date and a one-line caption. Computed server-side, same cache cadence as the story stories.
- **Empty state:** if a cohort has fewer than 3 entries, that line is suppressed (statistical-noise threshold). For JMFA at 14 entries it stays in. For a Guests pool with only 2 sign-ups, the slate line would drop.

### Backend

Reuses the existing `LeaderboardSnapshot` data. New service [backend/app/services/cohort_race.py](../../../backend/app/services/cohort_race.py):

```python
async def compute_cohort_trail(
    session: AsyncSession,
    *,
    days: int = 30,
) -> CohortTrailResponse:
```

```python
class CohortTrailPoint(BaseModel):
    captured_date: date
    median_rank: float                     # 0.5 increments are fine for tied-rank medians

class CohortTrail(BaseModel):
    cohort: Literal["atlas", "jmfa", "guests"]
    entry_count: int                       # current member count
    points: list[CohortTrailPoint]
    current_median_rank: float

class CohortTrailResponse(BaseModel):
    cohorts: list[CohortTrail]             # cohorts with < 3 entries omitted
    annotations: list[CohortAnnotation]    # 0-3 pinned events
    generated_at: datetime
```

Endpoint: `GET /api/leaderboard/cohort-trail` with the same 60-second `Cache-Control: private, max-age=60` and blind-pool gate as the other new endpoints.

## Story cards grid (top of the race tab)

A 2×2 grid of four editorial cards on desktop, single column on mobile. Each card surfaces one of four story types, each computed independently from the daily snapshot trail. Cards present a one-line title, a one-sentence caption, and a 2–3 line mini bump-chart sparkline.

```
┌─────────────────────────────┬─────────────────────────────┐
│ ▲ BIGGEST CLIMBER           │ ▼ STEEPEST FALL             │
│ Lionel Zammit — up 47       │ Kate Camilleri — down 22    │
│ From #62 to #15 in 3 days.  │ Held #3 for four days;      │
│ Group-stage exact streak.   │ KO upsets hit her bracket.  │
│   ╱╱╱╱╱<sparkline>          │   ╲╲╲╲╲<sparkline>          │
├─────────────────────────────┼─────────────────────────────┤
│ ⚔ CLOSEST RACE              │ 🔥 HOTTEST STREAK           │
│ #1 vs #2 — 4-pt gap         │ Brian Aglius — 6 days top 5 │
│ Traded the lead 3 times.    │ Hasn't dropped below #5     │
│ KO points could flip daily. │ since opening day.          │
│  ╲╱╲╱<two sparklines>       │   ─────<flat sparkline>     │
└─────────────────────────────┴─────────────────────────────┘
```

### Card types

Four independent cards, each with its own qualification rule. A card that doesn't qualify is **omitted entirely** — the grid auto-flows to 3, 2, 1, or 0 cards depending on how many qualify. With <4 cards the grid still uses 2 columns on desktop (extra cells empty); on mobile cards stack regardless.

| Card | Subject | Qualifies when |
|---|---|---|
| **`BIGGEST_CLIMB`** | Entry with the largest positive rank delta over the last 3 days. | Subject is currently in top 50 AND has moved ≥ 15 ranks upward over the window. |
| **`STEEPEST_FALL`** | Entry with the largest negative rank delta over the last 3 days. | Subject was in top 25 at start of window AND has dropped ≥ 15 ranks. |
| **`CLOSEST_RACE`** | The #1 and #2 entries' parallel trajectories. | Current gap ≤ 5 points AND they have traded the lead at least once in the last 7 days. |
| **`HOTTEST_STREAK`** | Entry with the longest unbroken run in the top 5. | Streak ≥ 5 consecutive days. Skipped if the streak holder is the current leader and has held #1 every day (no story — they've just always been on top). |

Tie-break rule (consistent across all four cards): on equal delta / equal streak length, pick the entry with the lower current rank — current leaderboard position is the relevant tie-breaker, not entry creation order.

### When the entire grid is empty

Pre-tournament, opening day, and any other state where no card qualifies: **the whole grid collapses to nothing**, no "no stories yet" placeholder. The race tab starts at the pills + chart. This is the only acceptable empty-state — placeholders read as "this feature is broken" when they're often actually "the data just isn't dramatic enough yet."

### Privacy / blind-pool

Pre-deadline the grid is hidden entirely (consistent with the rest of the V4 leaderboard being deadline-gated). Post-deadline it shows everyone's stories — the pool has agreed to open visibility at that point.

### Click-through

Each card is clickable. Click opens the existing `EntryDrawer` (already present in V4) for the subject entry, scrolled to its rank trajectory section. `CLOSEST_RACE` opens a side-by-side drawer of #1 and #2 (a small new variant on `EntryDrawer` — pass two entry IDs instead of one). No new route, no modal.

## Architecture

### Frontend

**Files modified:**

- [frontend/src/routes/leaderboard/+page.svelte](../../../frontend/src/routes/leaderboard/+page.svelte) — inject the five new regions into the existing "race" view branch; remove the `Full field` branch.
- [frontend/src/lib/components/leaderboard/v4/RaceChart.svelte](../../../frontend/src/lib/components/leaderboard/v4/RaceChart.svelte) — accept new required prop `slice: RaceSliceDescriptor`, plus `showMinimap: boolean` and `matchMarkers: MatchMarker[]`. Delete the unreachable full-field code path.
- [frontend/src/lib/utils/leaderboardV4.ts](../../../frontend/src/lib/utils/leaderboardV4.ts) — add pure derivation `selectRaceSlice(trajectories, mode, userId, cohortMap)` returning `{ included: EntryTrajectory[], minimapMarkers: MinimapMarker[], rankRange: [number, number] }`.
- [frontend/src/lib/types/leaderboard.ts](../../../frontend/src/lib/types/leaderboard.ts) — extend with `RaceViewMode`, `RaceSliceDescriptor`, `MinimapMarker`, `MatchMarker`, `RaceStory`, `RaceStoryKind`, `RaceStoriesResponse`, `ChampionSurvivalResponse`, `ChampionTeamCount`, `CohortTrail`, `CohortTrailPoint`, `CohortTrailResponse`. Lives outside the barrel per the V4 type convention in [CLAUDE.md](../../../CLAUDE.md).
- [frontend/src/lib/api/leaderboard.ts](../../../frontend/src/lib/api/leaderboard.ts) — add `getRaceStories()`, `getChampionSurvival()`, `getCohortTrail()`, `getMatchMarkers(daysBack: number)`.
- [frontend/src/lib/components/leaderboard/v4/EntryDrawer.svelte](../../../frontend/src/lib/components/leaderboard/v4/EntryDrawer.svelte) — accept an optional secondary `compareEntryId` prop AND an optional `cohort` variant (a list of entry IDs to render as a stacked list, used by Champion Survival's "who picked Brazil" click-through).

**Files created:**

- `frontend/src/lib/components/leaderboard/v4/RaceViewPills.svelte` — the pills toolbar. Owns the active-pill state; emits `change` events with the chosen mode.
- `frontend/src/lib/components/leaderboard/v4/RaceMinimap.svelte` — the bottom strip. Pure presentation, accepts `markers + rankRange + totalParticipants` props.
- `frontend/src/lib/components/leaderboard/v4/RaceStoryGrid.svelte` — the 2×2 grid container. Owns the `getRaceStories()` fetch + collapses to nothing when the response is empty.
- `frontend/src/lib/components/leaderboard/v4/RaceStoryCard.svelte` — one card. Renders all four `RaceStoryKind` variants via a discriminated-union prop. Pure presentation; the grid owns fetch + composition.
- `frontend/src/lib/components/leaderboard/v4/ChampionSurvival.svelte` — the gauge + team chips panel. Owns `getChampionSurvival()` fetch + click-to-drawer dispatch. Renders nothing pre-deadline.
- `frontend/src/lib/components/leaderboard/v4/CohortRaceChart.svelte` — the three-line cohort chart. Owns `getCohortTrail()` fetch. Suppresses any cohort with fewer than 3 entries. Click on a label dispatches a cohort-pill change to the parent (parent forwards to `RaceViewPills`).
- `frontend/src/lib/components/leaderboard/v4/MatchMarkerLayer.svelte` — the chart-axis annotations. Pure presentation, accepts `markers: MatchMarker[]` and the chart's x-scale function. Mounted *inside* `RaceChart.svelte` so the markers share its coordinate space.

**Component composition** (inside the "race" tab of `+page.svelte`):

```svelte
<RaceStoryGrid />                                <!-- ① -->
<ChampionSurvival />                             <!-- ② -->
<RaceViewPills bind:mode />                      <!-- ③ -->
<RaceChart                                       <!-- ④ -->
  rows={lbRows}
  userId={$user?.id}
  fixtures={tournamentFixtures}
  slice={selectRaceSlice(trajectories, mode, $user?.id, cohortMap)}
  matchMarkers={matchMarkers}
  showMinimap
/>
<CohortRaceChart on:cohortClick={e => mode = e.detail.cohort} />  <!-- ⑤ -->
```

### Backend

**New service** [backend/app/services/race_stories.py](../../../backend/app/services/race_stories.py):

```python
async def select_race_stories(
    session: AsyncSession,
    *,
    today: date | None = None,
) -> list[RaceStory]:
```

Reads the same daily snapshots the chart already uses, runs all four candidate-story computations independently, and returns the qualifying stories in a stable display order: `BIGGEST_CLIMB → STEEPEST_FALL → CLOSEST_RACE → HOTTEST_STREAK`. Display order is **NOT** priority order — each card is independent and either qualifies or doesn't; we just want the grid to lay out consistently across requests. Cache the result for 5 minutes (matches the leaderboard cache's expire-not-invalidate pattern from v2.173.0).

Each `RaceStory` carries the data the card needs to render *without* a follow-up fetch:

```python
class RaceStory(BaseModel):
    kind: Literal["biggest_climb", "steepest_fall", "closest_race", "hottest_streak"]
    title: str                          # rendered headline, e.g. "Lionel Zammit — up 47"
    caption: str                        # one-sentence body copy
    subject_entry_id: str               # for click-through to EntryDrawer
    compare_entry_id: str | None        # populated only for closest_race
    sparkline: list[SparklinePoint]     # 7-day rank trail of the subject
    compare_sparkline: list[SparklinePoint] | None  # closest_race only
```

The headline + caption strings are **composed by the backend**, not by the frontend. Reason: the qualification rule and the prose explaining it are coupled — they should change together. Frontends that compose copy from data fields drift into inconsistencies (frontend says "up 47 places" while backend qualification was "since last Thursday"). Plain strings from the server are the simplest rule.

**Endpoint** in [backend/app/api/leaderboard.py](../../../backend/app/api/leaderboard.py):

```python
@router.get("/race-stories", response_model=RaceStoriesResponse)
async def race_stories(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RaceStoriesResponse:
```

```python
class RaceStoriesResponse(BaseModel):
    stories: list[RaceStory]            # 0–4 entries, in display order
    generated_at: datetime              # aware-UTC per CLAUDE.md datetime rule
```

- Blind-pool gate: returns `{"stories": [], ...}` pre-deadline (matches the rule the existing community endpoints follow). Empty list, not 403 — keeps the frontend collapse-to-nothing logic uniform.
- 60-second `Cache-Control: private, max-age=60` to amortise the daily-snapshot reads.

### Data the stories need

All four story types are derivable from `LeaderboardSnapshot` (existing table). No schema changes. No new daily job — stories are recomputed on each cache miss against the existing snapshot trail.

## Mobile (≤640px)

- Pills row becomes a scroll-snap horizontal strip (the established mobile sub-nav pattern from [feedback_scrollable_pills_mobile_subnav.md](../../../../../../.claude/projects/C--Users-vinay-OneDrive---Atlas-Insurance-PCC-Projects-predictorv2/memory/feedback_scrollable_pills_mobile_subnav.md)).
- Story cards grid collapses from 2×2 to a **single column**. Cards stack in their server-defined display order. No horizontal scroll — vertical scroll the page.
- Names-on-right-edge of the chart truncate to 14 chars; tap to expand.
- Minimap strip height drops from 16px to 12px.
- "Top 25" pill renders chart at a `min-height: 480px` with vertical scroll inside the chart wrapper, not the page.

## Edge cases

- **User has zero entries**: "Around me" pill is disabled with a tooltip ("Sign up to centre this view on your entries"). Default falls back to "Top 10".
- **User has multiple entries**: "Around me" centres on the user's *best-ranked* entry; the other entries are still highlighted in gold and ALWAYS included in the slice regardless of where they rank. Example: user has entries at #27 and #142; "Around me" shows ranks 24-30 *plus* #142 highlighted, with the y-axis broken (a `…` gap) between #30 and #142.
- **User's best entry is rank #1**: "Around me" shows ranks 1-7 (no gap above #1). Leader-ghost-line is suppressed (user IS the leader).
- **Cohort filters with very few members** (e.g. JMFA-only with 14 entries, user not in JMFA): chart shows the 14 + user's entries, y-axis spans full visible rank range, minimap shows two pin clusters.
- **All trajectories share the same rank on every day** (pre-tournament, all entries at #1): chart shows them stacked as a single flat ribbon; pills behave as no-ops; story card returns null.

## Versioning

This is a feature addition — minor bump (`2.x.0 → 2.(x+1).0`). Update the three version files per CLAUDE.md and append a `feature`-type entry to `changelog.json`:

```
"Race tab redesigned. Story cards highlight the day's biggest climbers,
falls, closest races and streaks. New 'Champion Survival' gauge shows
how much of the pool still has a live winner pick. The chart focuses
on entries near your rank with match-result markers pinned to the
dates — so you can see exactly which fixture moved you up or down. A
new cohort race chart compares Atlas vs JMFA vs Guests over time."
```

The "Full field" view is gone — flag this in the release notes so anyone who relied on it knows where the all-entries view moved (Standings tab).

## Tests

### Frontend (vitest)

- `selectRaceSlice.test.ts` — table-driven test cases covering every view mode × edge case combination listed in "Edge cases" above. Pinned to the 8 edge cases as regression fixtures.
- `RaceStoryGrid.test.ts` — empty response → component renders nothing (no placeholder); 1/2/3/4 stories in response → grid renders that many cards in the server-supplied display order.
- `RaceStoryCard.test.ts` — discriminated-union prop renders all four `RaceStoryKind` variants correctly; click dispatches the right `EntryDrawer` open event (single-entry vs compare).
- `RaceMinimap.test.ts` — marker positioning math (rank → x-coordinate), slice-band width math.
- `ChampionSurvival.test.ts` — gauge arc math (percent → arc-length); pre-deadline → renders nothing; click on a team chip dispatches the right `EntryDrawer` open event with the `cohort` variant.
- `MatchMarkerLayer.test.ts` — markers positioned at correct x-coordinates given the chart's x-scale; > 3 markers clusters into a `+N more` chip; upset variant applies the gold-soft chrome.
- `CohortRaceChart.test.ts` — cohorts with < 3 entries are suppressed (no line, no label); inverted y-axis math (lower rank → higher y position); cohort-label click dispatches the right `cohortClick` event.

### Backend (pytest)

- `test_race_stories.py` — fixture snapshots for each story type's qualifying and disqualifying conditions; tie-breakers (equal delta → lower current rank wins); pre-deadline blind-pool returns empty stories list; aware-UTC `generated_at` (regression-guard for the recurring tzinfo strip bug per CLAUDE.md datetime rule).
- `test_champion_survival.py` — alive-count math against fixture KO results; eliminated team detection uses `Fixture.status == FINISHED` only (in-progress matches don't eliminate); pre-deadline returns empty teams list; top-N chip selection on tie sorts by team_code for determinism.
- `test_cohort_race.py` — median math (odd-count → middle, even-count → average of two middles); cohort with < 3 entries omitted from response; annotation generation triggers at crossing thresholds; aware-UTC `generated_at`.
- `test_race_impact.py` — match-shuffling-impact score correctly identifies the top 3 most-disruptive KO matches over a date range; group fixtures excluded; upset detection (>60% picked losing side) sets the right flag.
- Use the worktree-overlay test pattern from CLAUDE.md for execution.

### Manual

- Mobile 375px verification on real device or DevTools simulator: pills scroll horizontally, story cards stack to one column, champion-survival panel stacks gauge above chips, cohort chart legible.
- Admin in production AFTER deploy: switch between all six pills, confirm chart transitions are smooth, confirm minimap aligns with the visible slice. Hover/tap a match marker — tooltip surfaces correctly. Click a champion-survival chip — drawer opens with the right entry list. Click a cohort label — focal chart switches to that filter.

## Rollout

This rides the existing V4 leaderboard gate. No new flag needed.

- Frontend changes are inside the V4 branch of `+page.svelte`, so flipping `V4_LEADERBOARD_ENABLED` to `false` reverts to V3 cleanly.
- Backend endpoint is additive — if the frontend doesn't call it, it's dormant.
- Land in one PR; ship as a minor version; admin-verify on prod; no staged rollout to a subset of users.

## Out of scope, deferred follow-ups

- Persisting the pill state in `localStorage`. Defer until usage data tells us the default mode is wrong for a meaningful slice of users.
- Allowing the user to compare themselves against a chosen opponent (a "follow this entry" pin). Powerful but adds a state model that pollutes the URL or storage. Defer.
- "Story of the week" / "story of the tournament" — the daily story grid covers the use case for now.
- Additional card types (longest cold streak, biggest single-day jump, most volatile entry). The four-card set is a deliberate ceiling — more cards become noise.
- A "back to the old chart" escape hatch. Deliberately removed; standings tab is the all-entries surface.

## References

- [Memory: v2.164.0 V4 leaderboard ship notes](../../../../../../.claude/projects/C--Users-vinay-OneDrive---Atlas-Insurance-PCC-Projects-predictorv2/memory/predictorv2_results_leaderboard_rebuild.md)
- [Memory: SWR leaderboard cache invalidate vs expire](../../../../../../.claude/projects/C--Users-vinay-OneDrive---Atlas-Insurance-PCC-Projects-predictorv2/memory/predictorv2_v2173_live_polling_swr.md)
- [Memory: DaisyUI surface elevation ladder + btn-active pattern](../../../../../../.claude/projects/C--Users-vinay-OneDrive---Atlas-Insurance-PCC-Projects-predictorv2/memory/feedback_daisyui_surface_ladder.md)
- [Memory: scrollable pills for mobile sub-nav](../../../../../../.claude/projects/C--Users-vinay-OneDrive---Atlas-Insurance-PCC-Projects-predictorv2/memory/feedback_scrollable_pills_mobile_subnav.md)
- [CLAUDE.md — V4 Leaderboard section](../../../CLAUDE.md)
