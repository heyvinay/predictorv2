# V4 Results + Match Detail Rebuild + Admin Completeness Check — Design

**Date:** 2026-06-10 · **Target release:** v2.163.0 (bundled) · **Status:** spec — awaiting user approval

## Purpose

Replace the flag-gated stub at `/results` ([results/+page.svelte:21](frontend/src/routes/results/+page.svelte:21) — `SHOW_CONTENT = false`) with the V4 redesigned Results page + a new Match Detail page at `/results/[fixture_id]`. The visual contract is in `mockups/Results-redesign/V4-Results-MatchDetail-bundle.html` and the React reference at `mockups/Results-redesign/reference/v4-results.jsx` / `v4-match.jsx` — both validated across ~20 rounds of iteration with the product owner.

Bundle in an **admin completeness check** for entry-pick fullness so the V4 page renders against a clean dataset. Both ship as v2.163.0.

The current Results page is a "Results open at kickoff" stub. The V4 redesign carries:

- **Round-tabbed scoreboard** — `Summary · R1 · R2 · R3 · R32 · R16 · QF · SF · Finals · Winner`
- **Multi-entry support** — entry switcher pill bar (hidden for single-entry users)
- **Group-stage rounds** scored on result/exact/rarity; **knockout rounds** scored on bracket calls (not on the fixture score); **Winner tab** for the champion-pick payout
- **Match Detail with prev/next navigation** (click, arrows, swipe) for any fixture
- **Live indicators** on round pills and matching Summary rows
- **Page gating** — surfaced only after the deadline passes

## Decisions (user, 2026-06-10)

All decisions from the brainstorming session, locked verbatim:

- **C.1 No hardcoded points in copy.** Every user-facing string mentioning a point value reads its number from `GET /api/leaderboard/scoring-rules`. The `RoundExplainer` banner, Missed Picks subtitle, Winner card status chip, and any tooltip referencing scoring all template against the live config. The endpoint already returns the full `match` + `advancement` blocks ([leaderboard.py:91-109](backend/app/api/leaderboard.py:91)) — no backend change.
- **C.2 Strengthened KO banking-timing explainer.** Locked wording per round (`{round_of_32}` etc. templated from C.1):
  > *"How Round of 32 scoring works: you earn +{round_of_32} for each team in your bracket that reaches R32. **These points are banked from your bracket pick — you earned them when each team finished the group stage. The match score below decides who walks to R16, not these points.** No rarity bonus in the knockouts."*
- **C.3 "Upset of the round" badge is a client-side per-fixture heuristic.** A finished fixture qualifies when the winning team was picked by less than 30% of the eligible pool to win (1/X/2) **and** the pool size is ≥ 10 entries. Uses `Score.outcome` (`'1' | 'X' | '2'`) — the same axis rarity uses. No backend endpoint, no admin curation in V4. **No cross-fixture tie-break** (amended 2026-06-10): the original "only the lowest-share winner in a round wears the badge" rule would require fetching `/community` for every other fixture in the round (up to 24 requests per page view) just to render one badge. Each match's badge is now decided in isolation from its own pool data; multiple fixtures in a round may show it. Re-introducing the tie-break is a clean follow-up via an aggregate endpoint (e.g. `GET /api/results/rounds/{r}/upset`) or by precomputing the flag on the backend during score sync — neither in scope for v2.163.0.
- **B.1 `MatchPredictionRead.points` addition.** Schema extends with `points: PickPointsOut | None`. Populated for FINISHED fixtures via `app.services.scoring.compute_match_points`. **Implementation must use a single bulk-agreement fetch** (reuse `compute_agreements` with no fixture filter — already a one-query helper) then map per-fixture in memory. P95 < 200ms for the full list.
- **B.3 `CommunityPrediction.rank: int | None`.** Server-populated from cached `calculate_leaderboard()`. Null means "this entry is not in the current leaderboard ranking" (renders `—` in the pool list). Same blind-pool gate as before — visibility unchanged.
- **D.1 Auto-scroll to LIVE-containing pill on mount.** Overrides the "default to today's round" logic from §8.1 of the V4 handover when any pill contains a LIVE fixture. Falls back to today's round → last-completed round → R1. On WC2026 transition days (e.g. 18 Jun has both R1 and R2 fixtures live), tie-break is **earliest round in tab order** wins.
- **D.1b LIVE dot mirrored on Summary rows.** Each Summary row corresponds to a round pill. If a round has a LIVE fixture, the matching Summary row renders the same pulsing red dot (after the round label, before the date range). Single derived `roundsWithLive: Set<RoundId>` flows from `+page.svelte` to both `RoundTabs.svelte` and `SummaryView.svelte`.
- **D.2 Page gating + per-fixture cell rules.** Page is gated behind `phase1Deadline < now` — pre-deadline shows the existing "Results open at kickoff" stub. Once gated open: per-fixture Points column shows `—` for not-yet-played fixtures, computed points for finished fixtures (incl. literal 0 for a confirmed miss). Aggregate cells (Points summary card, Summary subtotals, Tournament Total) show `0` when no points are banked yet (honest math, not "—"). No-pick and no-entry empty states **dropped** — covered by invariants (E.1 + disabled-login rule).
- **D.3 "You vs average" column deferred.** Logged to §11 (Out of scope). Re-opens in v2.165-ish as a standalone follow-up.
- **D.4 Rarity-explainer microcopy templates — four variants.** All four locked, server-rendered into `RarityDetailOut.note`. See §7 for wording.
- **E.1 Admin completeness check — report-only + CSV export.** Bundled into v2.163.0. New `GET /api/admin/entries/completeness-check` (+ `.csv` variant). Button on `/admin/entries` runs the check; the admin downloads CSV and chases up users out of band. No disable affordance.
- **F.1 Missed Picks card drops the reason chip.** Was *"flag · name · reason chip"*, becomes *"flag · name"*. Avoids touching `/api/fixtures/standings/actual` (Phase 2 path; CLAUDE.md forbids extending Phase 2 features).

**Not in scope:**
- Phase 2 infrastructure cleanup (`/standings/actual`, `/knockout/actual`). Dormant code stays dormant.
- Bracket-vs-bracket comparison view.
- Per-entry sparklines on round tabs.
- Push notifications for live-match starts.
- Sharing a Match Detail page externally / server-side OG previews.
- Summary "you vs pool average" column (D.3, deferred).

## Constraints honoured

- **Blind pool** — already enforced backend-side at [leaderboard.py:146-156](backend/app/api/leaderboard.py:146) and [predictions.py:90](backend/app/api/predictions.py:90). The page-gating rule (D.2) lines up with the leaderboard's reveal moment.
- **Single-phase invariant** — no Phase 2 code paths touched. The dormant `phase_2` rows in `prediction_entry_phases` remain ignored; all reads filter to `phase == PHASE_1`.
- **No raw hex** — DaisyUI tokens only. Two themes (`premium-night` default / `hybrid` light).
- **Mobile-first** — 375px baseline. Every screen verifies there first.
- **Datetime rule** — every datetime returned by new endpoints is tz-aware UTC. `aware_utc()` at service-function return sites.
- **Scoring parity** — `computeMatchPoints` (frontend) and `compute_match_points` (backend) stay locked to `shared/scoring-parity-cases.json`. No changes to either; the V4 work consumes both, doesn't extend them.

## Backend changes

Three deltas. Surface area is small.

### 1. `MatchPredictionRead.points` — additive schema field

[backend/app/schemas/prediction.py:27-48](backend/app/schemas/prediction.py:27): extend `MatchPredictionRead` with an optional `PickPointsOut`.

```python
class PickPointsOut(BaseModel):
    base: int                                                  # 0 | 5 | 15
    base_kind: Literal["miss", "result", "exact"]
    rarity: int                                                # 0..rarity_cap
    total: int                                                 # base + rarity

class MatchPredictionRead(BaseModel):
    # ...existing fields...
    points: PickPointsOut | None = None                        # null until FINISHED
```

**Population path.** `list_match_predictions` at [entry_predictions.py:177-184](backend/app/api/entry_predictions.py:177) currently calls `_to_match_read(pred, fixture)` per row. The new path:

1. Fetch the entry's match predictions + fixtures (existing query, unchanged).
2. **Once per request:** call `compute_agreements(session, entry=entry, fixture_ids=None)` — returns `[{fixture_id, agrees_outcome, agrees_exact, total}]` for every fixture the entry has a pick on. One query.
3. Once per request: load the scoring config via `get_scoring_config()`.
4. For each `(pred, fixture)` pair where `fixture.status == FINISHED` and `fixture.score` exists, compute `points` via `compute_match_points(...)` — pure function, takes primitives, no IO.
5. Populate `MatchPredictionRead.points` and return.

**Performance gate.** P95 < 200ms for the full list (72 fixtures × 150 entries pool). Verify before merge.

**Why not just iterate `compute_agreements` per fixture.** The naive loop is quadratic in the entry pool. The bulk helper exists; use it.

### 2. `CommunityPrediction.rank: int | None` — additive schema field

[backend/app/schemas/prediction.py:86-100](backend/app/schemas/prediction.py:86): extend `CommunityPrediction`.

```python
class CommunityPrediction(BaseModel):
    user_name: str
    entry_reference: str
    entry_name: str
    home_score: int
    away_score: int
    rank: int | None = None                                    # null if not in leaderboard
```

**Population path.** In `get_community_predictions` at [predictions.py:67](backend/app/api/predictions.py:67):

1. After the existing join produces the predictions list, surface `MatchPrediction.entry_id` on each result row (one column add to the existing select).
2. Call `calculate_leaderboard(session, phase=None)` — already cached for 30s.
3. Build `rank_by_entry: dict[UUID, int]` from `response.entries`.
4. Map `rank = rank_by_entry.get(entry_id)` per row. Null for entries not in the ranking.

Visibility unchanged — same 403 pre-lock gate. Ties: leaderboard service already handles them (same rank for tied entries); we pass that through.

### 3. Admin completeness check — new endpoints

**New module:** `backend/app/services/completeness.py`

```python
class EntryCompletenessResult(BaseModel):
    entry_id: UUID
    entry_name: str
    user_name: str
    user_email: str
    missing_match_picks: int                                   # 0 .. expected count
    missing_bracket_picks: int                                 # 0 .. expected count
    missing_bonus_picks: int                                   # 0 .. number of YAML questions
    is_complete: bool                                          # convenience
    detail: EntryCompletenessDetail | None                     # only when ?detail=true

class EntryCompletenessDetail(BaseModel):
    missing_fixture_ids: list[UUID]
    missing_bracket: dict[str, int]                            # stage → missing count
    missing_bonus_ids: list[str]
```

**Per submitted-eligible entry** (`status == SUBMITTED`, `withdrawn_at IS NULL`, `is_disabled = false` — reuses `eligible_entry_ids_select()` from the scoring service), the check counts:

- **Match predictions:** expected = count of group-stage `Fixture` rows (72 for WC2026). Missing = expected − count of `MatchPrediction` rows for entry on group fixtures.
- **Bracket predictions:** expected = **63** — R32 (32), R16 (16), QF (8), SF (4), Final (2), Winner (1). **CORRECTED during implementation (2026-06-10):** there are no "group"-stage `TeamPrediction` rows — verified against the dev DB, complete wizard-written entries carry exactly these 63. Group standings are implied by the R32 selection, not stored separately. The original spec's `group_winners (24)` line was wrong.
- **Bonus predictions:** expected = `len(get_bonus_questions())` (4 today). Missing = expected − count of `BonusPrediction` rows whose `question_id` is in the **current** question set — legacy entries carry rows for retired ids (the 10 → 4 trim) which must not inflate the count. `BonusPrediction` has no `phase` column.

Implementation strategy: three SQL aggregates (one per pick category) joined against the entry table. One query per category, not per entry. Returns a list of all eligible entries with their gaps; the frontend filters to incompletes for display.

**New endpoints:** `backend/app/api/admin.py`

```python
@router.get("/entries/completeness-check", response_model=list[EntryCompletenessResult])
async def completeness_check(
    session: DbSession,
    admin: AdminUser,
    detail: bool = Query(False),
) -> list[EntryCompletenessResult]:
    # returns ALL eligible entries; frontend filters to incompletes
    ...

@router.get("/entries/completeness-check.csv")
async def completeness_check_csv(
    session: DbSession, admin: AdminUser,
) -> StreamingResponse:
    # returns only incompletes, formatted as CSV
    # columns: entry_id, entry_name, user_name, user_email,
    #          missing_match_picks, missing_bracket_picks,
    #          missing_bonus_picks, total_missing
    ...
```

Both admin-only via the existing `AdminUser` dependency.

## Frontend changes

### Page composition

`frontend/src/routes/results/+page.svelte` becomes a thin shell mounting V4 components. `frontend/src/routes/results/[fixture_id]/+page.svelte` is new.

### Files created (one component per file, mirrors V4 handover §4)

```
frontend/src/lib/components/results/v4/
  EntryPill.svelte
  EntryPillBar.svelte
  PointsSummary.svelte
  RoundTabs.svelte
  RoundExplainer.svelte
  SummaryView.svelte
  GroupRoundTable.svelte
  KnockoutRoundTable.svelte
  MissedPicksCard.svelte
  ProgressingCard.svelte
  FixtureRowGroup.svelte
  FixtureRowKo.svelte
  PointsCellGroup.svelte
  PointsCellKo.svelte
  BracketChip.svelte
  WinnerView.svelte

frontend/src/lib/components/results/v4-match/
  MatchNav.svelte
  MatchHero.svelte
  UpcomingHero.svelte
  YourPick.svelte
  UpcomingYourPick.svelte
  PointsBreakdown.svelte
  RarityExplainer.svelte
  ScorelineSpread.svelte
  PoolList.svelte
  PoolPickedWhat.svelte
  PoolSplit.svelte

frontend/src/lib/utils/
  upsetOfRound.ts                                              # heuristic for C.3
  roundsWithLive.ts                                            # derives the live-set for D.1 + D.1b
```

### Existing files touched

- `frontend/src/routes/results/+page.svelte` — rewrite.
- `frontend/src/routes/results/[fixture_id]/+page.svelte` — new.
- `frontend/src/lib/api/leaderboard.ts` (or wherever the scoring config helper lives) — wire `getScoringConfig()` into the page mount.
- `frontend/src/lib/stores/predictions.ts` — entry-scoped variant if needed (V4 handover §4 flagged this; verify before adding).
- `frontend/src/lib/utils/teamCodes.ts` — confirm flag codes for all 48 WC2026 teams; extend if needed.
- `frontend/src/lib/utils/teamName.ts` — `SHORT_NAMES` map; mirror any additions to `backend/app/services/team_name.py` per CLAUDE.md.
- `frontend/src/routes/+layout.svelte` — fix `nav.to?.url?.pathname` latent TypeError (CLAUDE.md latent layout bug) at lines 68-69 if the rebuild touches this file.

### Admin completeness UI

- `frontend/src/routes/admin/entries/+page.svelte` — add a **"Run completeness check"** button above the existing entries table.
- New `frontend/src/lib/components/admin/CompletenessModal.svelte` — modal that opens on click, fetches `/api/admin/entries/completeness-check`, filters to `!is_complete`, renders a table with `entry · user · missing counts · "View detail" link` per row.
- "Download CSV" action in the modal header → triggers a download of `/api/admin/entries/completeness-check.csv`.
- Empty result state: green banner *"All eligible entries are complete ✓"*.

## Page-by-page UI spec — `/results`

Mobile layout, top → bottom (375px baseline; desktop is grid-of-the-same-blocks).

### 1. Page title

`Results` h1 + sub.

### 2. Entry switcher pill bar

**Rendered only when the user has 2+ entries.** Single-entry users see no switcher; the points summary stretches full width. Horizontal scroll on mobile.

Each pill: name (+ DRAFT chip if applicable) · rank · total points. No avatar. Compact (≈6px/13px padding). Active pill: **faint gold outline + subtle gold-tinted fill, NO glow**.

Active-pill `scrollIntoView` uses `{ inline: 'center', block: 'nearest' }` to avoid page Y-shift (CLAUDE.md scrollIntoView caveat).

### 3. Points summary card

Right of entry pills on desktop; below on mobile. **Single-entry users:** full-width. Four cells on ONE line (never wraps): Result · Exact · Rarity · Total. Letters top-left of each cell. Cell tones: warning / success / primary / gold.

### 4. Round tabs

Horizontal scroll: `Summary · R1 · R2 · R3 · R32 · R16 · QF · SF · Finals · Winner`.

Active tab: faint gold outline + tinted fill, no glow. Sticky under page header on scroll.

**Live dot:** 7px circle, `bg-error`, `animate-pulse-soft`. Renders before the round label, inside the same flex row, on any tab whose round contains a LIVE fixture.

**Auto-scroll on mount (D.1):** when `roundsWithLive` is non-empty, scroll the strip so the earliest-in-tab-order LIVE-containing pill is in view AND set it active. Otherwise fall back to: today's round → last-completed round → R1.

### 5. Round explainer banner

Slim gold-tinted info strip, one line. Wording differs by round type. **All point numbers are templated from `/api/leaderboard/scoring-rules` (C.1)**.

| Round type | Copy template |
|---|---|
| Group (R1/R2/R3) | *"How Round {n} scoring works: +{correct_outcome + exact_score} for the exact score, +{correct_outcome} for the correct result — plus a rarity bonus on top when your correct pick was one few others made."* |
| KO (R32/R16/QF/SF/Final) | *"How {round_label} scoring works: you earn +{stage_points} for each team in your bracket that reaches this round. **These points are banked from your bracket pick — you earned them when each team finished {prev_stage_label}. The match score below decides who walks to {next_stage_label}, not these points.** No rarity bonus in the knockouts."* |
| Winner | *"How Winner scoring works: you earn +{winner_points} if your champion pick lifts the trophy. Points are awarded when the final whistle blows on {final_date}. No rarity bonus."* |
| Summary | *"Summary — points across every round of the tournament for the selected entry. Group stage rounds award +{correct_outcome + exact_score} exact / +{correct_outcome} result plus a rarity bonus; knockout rounds award stage-specific points per bracket pick that reaches the round. Tap any row to jump to that round."* |

`{prev_stage_label}` / `{next_stage_label}` are the human-readable adjacent stages — for R32 prev = "the group stage", next = "Round of 16"; for the Final, the next-stage clause is dropped.

### 6. Round content — Group rounds (R1 / R2 / R3)

`card` containing a fixtures table. Mobile re-layout: each fixture becomes a stacked card (handover §7.5):

```
┌────────────────────────────────────┐
│ 🇲🇽 Mexico              2 – 1   FT │
│ 🇿🇦 South Africa                  │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
│ Your pick: 2-1   ·   E15+R3: 18   │
└────────────────────────────────────┘
```

- **Score column:** centred, two-line — numeric score + small meta (date or `LIVE 67'` in red).
- **Loser side:** 60% opacity (not strikethrough).
- **Pick column:** `H-A` (e.g. `2-1`); muted if missing.
- **Points column:** `+R5+R3: 8` shorthand. Tones: green for exact, amber for result, muted for miss. **Pre-played → `—`**.
- **Live rows:** thin red left rail (`border-l-4 border-error`); `LIVE 67'` in red on the score line.
- **Row click:** navigate to `/results/[fixture_id]`.
- **Footer row:** round subtotal in gold.

### 7. Round content — Knockout rounds (R32 / R16 / QF / SF / Final)

`card` with a different 4th column (Your bracket call):

```
HOME            SCORE      AWAY              YOUR BRACKET    POINTS
🇲🇽 Mexico      2 – 1      🇸🇳 Senegal       ✓ MX  ✓ SN     +5×2: 10
```

- **Bracket call chips:** green ✓ chip when team is in user's bracket-pick for this round, grey otherwise.
- **Points cell:** `+{stage_points}×n: total` where n = number of picked teams in this fixture. Tones: green if both, amber if one, muted if neither.
- **CRITICAL:** KO points show for LIVE and not-yet-played fixtures too — banked at lineup-set, not at full-time. Live indicator stays under the score, NOT in the points cell.
- **Above the table (R32 only):** `MissedPicksCard.svelte`. Dashed red border. R32 picks that bombed out in the group stage. Pills: **flag · team name** (no reason chip — F.1). Subtitle: *"–{N × {round_of_32}} unrealised"* — number templated from scoring-rules.
- **Below the table (all KO except Final):** `ProgressingCard.svelte`. Green border. Winners of this round's fixtures, with green pills for those in the user's next-round bracket (`+{next_stage_points}` tag) and grey pills for those who aren't (`not picked` tag). Subtitle: *"{X} of {Y} fixture winners are in your {NextRound} bracket · locks in +{X × next_stage_points} on the {NextRound} page"*.
- **Footer row:** round subtotal in gold.

### 8. Summary tab

1. **Three subtotal cards** in a 3-column grid (stacks on mobile):
   - **Group stage** — total + E/R/★ counters across R1–R3.
   - **Knockouts** — total + ✓ bracket-hit count across R32→Final.
   - **Tournament total** — gold-glowed grand-total card. **This is the ONLY glow element on the page.**
2. **Per-round table** — one row per round (R1 → Final → Winner). Each row:
   - GP/KO chip (gold for GP, green for KO).
   - **LIVE dot if `roundsWithLive` contains this round (D.1b).** Renders after the round label, before the date range.
   - Round label + date range.
   - Hit chips (`E 2 · R 4 · ★ 3` for group, `✓ 6` for KO; Winner row: `pending` chip until the final, then `🏆 +25` or `✗ missed`).
   - Round subtotal (right-aligned, gold if > 0).
   - Arrow → on the right; entire row is clickable to jump to that round's tab.
3. **Footer row** — Tournament Total in gold (matches grand-total card).

### 9. Winner tab

A single centered champion card (gold-bordered, radial gold tint at the top):

- Badge: `🏆 World Cup 2026 · Champion`.
- Two columns (stack on mobile):
  - **Your pick** — flag 84×58 · team name in display face · status chip.
  - **Actual champion** — TBD dashed placeholder + "final not yet played" chip until decided; flag + `🏆 lifted the trophy` chip after.
- Your-pick status chip states: `pending · +{winner_points} if they lift it` (neutral, templated) → `✓ +{winner_points} banked` (green) or `✗ no points` (red).
- Entries without a champion pick show *"No champion pick on this entry."*

## Page-by-page UI spec — `/results/[fixture_id]`

Two layouts (played/live vs upcoming/locked) share the same shell.

### Nav strip at top — single horizontal pill

- Left: `← Back to Results`.
- Center: `‹` arrow · position counter (`3 of 24` + `ROUND 1` label) · `›` arrow.
- Arrows show prev/next fixture team names on hover/title attribute.
- Disabled at round edges (no cross-round wrap).
- **Keyboard:** ← / → for prev/next.
- **Touch:** horizontal swipe (60px threshold, must be more horizontal than vertical, < 600ms) → prev/next.

### Played-match body (2-col desktop, 1-col mobile)

- **Left col:**
  - Hero card. `UPSET OF THE ROUND` badge — present only when the C.3 heuristic fires. Big home/score/away strip with flags, group + date meta, storyline.
  - `PoolList.svelte` — banked / missed split. Per-row: avatar, name, pick, points, **rank** (from B.3 — renders `—` if null).
- **Right col:**
  - `YourPick.svelte` — your score · their score · result chip.
  - `PointsBreakdown.svelte` — Result, Exact, Rarity stat strip.
  - `RarityExplainer.svelte` — only when `pool_stats` is non-null AND the entry has a pick on this fixture. Renders `RarityDetailOut.note` verbatim (server-templated, D.4).
  - `ScorelineSpread.svelte` — 4×4 grid of pick counts, your-pick cell ringed in gold.

### Upcoming/locked-match body (same 2-col shell)

- **Left col:**
  - `UpcomingHero.svelte` — 🔒 LOCKED · KO HH:MM badge, big VS, "Kicks off in 2h 14m", group · date.
  - `PoolPickedWhat.svelte` — who picked what, with filter chips (All / Home / Draw / Away).
- **Right col:**
  - `UpcomingYourPick.svelte` — payout teaser dashed gold border: `+{outcome+exact}? IF IT'S A {OUTCOME}` (numbers from scoring-rules).
  - `PoolSplit.svelte` — 3-segment percentage bar + 3 outcome cards (Common/Uncommon/Rare bands).
  - Predicted-scorelines spread (bubble heatmap, side-tinted).

## Microcopy lock (D.4 + others)

Rarity explainer — server-rendered into `RarityDetailOut.note`, four variants. The frontend never picks a template; it just renders `note` verbatim.

| Band | Trigger | Template |
|---|---|---|
| Default | `1 < N < total/2`, not FINISHED | *"Only {N} of {total} entries called this outcome ({pct}%) — you'd earn +{pts} rarity if it holds."* |
| Solo | `N = 1`, not FINISHED | *"Only you out of {total} entries called this outcome — you'd earn +{pts} rarity if it holds."* |
| Banked | fixture FINISHED, rarity > 0 | *"Only {N} of {total} entries called this outcome ({pct}%) — banked +{pts} rarity."* |
| Consensus | `f ≥ 0.5`, no rarity awarded | *"Your outcome was the popular call ({N} of {total}, {pct}%) — no rarity bonus on consensus picks."* |

`pct` is `round(N/total × 100)` to one decimal place. `N` and `total` are integers. `pts` is integer.

The explainer block does NOT render when:
- The entry has no pick on this fixture.
- `pool_stats` is null (pre-lock).
- Fixture is FINISHED, rarity = 0, AND outcome was a miss (no bonus to explain).

## Behavior notes

### Auto-scroll to LIVE pill (D.1)

On mount, `+page.svelte` computes `roundsWithLive: Set<RoundId>` from the loaded fixtures (any fixture with `status ∈ {live, halftime}` contributes its round). If non-empty, the earliest-in-tab-order entry is set as the active tab and `RoundTabs.svelte` scrolls it into view. Tab order: `Summary, R1, R2, R3, R32, R16, QF, SF, Final, Winner`.

If empty, default per V4 handover §8.1: today's round → last-completed round → R1.

### LIVE dot mirroring (D.1b)

Single derived `roundsWithLive` set passed as a prop to both `RoundTabs.svelte` and `SummaryView.svelte`. Both render the same pulsing dot signal when their row/tab is in the set. No double-implementation — one source.

### Upset of the round heuristic (C.3)

`upsetOfRound.ts` helper:

```typescript
export function isUpsetOfRound(
  fixture: Fixture,
  community: CommunityPredictionsResponse | undefined,
  roundCommunities: Map<UUID, CommunityPredictionsResponse>,
): boolean {
  if (!community || !fixture.score || fixture.status !== 'finished') return false;
  if (community.predictions.length < 10) return false;
  const winnerOutcome = fixture.score.outcome; // '1' | 'X' | '2'
  const winnerShare = winnerOutcomeShare(community.predictions, winnerOutcome);
  if (winnerShare >= 0.30) return false;
  // Tie-break: lowest share across all qualifying fixtures in this round
  for (const [otherId, otherComm] of roundCommunities) {
    if (otherId === fixture.id) continue;
    const otherShare = winnerOutcomeShareFor(otherComm);
    if (otherShare !== null && otherShare < winnerShare) return false;
  }
  return true;
}
```

Pure function. Unit-tested per branch.

### Page gating (D.2)

The flag-gated stub at `results/+page.svelte:21` becomes:

```typescript
$: resultsOpen = $phase1Deadline ? new Date($phase1Deadline) < new Date() : false;
```

When `resultsOpen === false`, render the existing pre-tournament stub. When true, render the V4 shell. No manual flag flip needed for tournament day.

### Aggregate vs per-fixture cell rendering (D.2)

| Cell | Pre-tournament | Per-fixture not played | Per-fixture finished, no pick | Per-fixture finished, miss | Per-fixture finished, hit |
|---|---|---|---|---|---|
| Points summary card cells (R/E/★/Total) | `0` | n/a — aggregated below | n/a | n/a | n/a |
| Summary subtotal cells | `0` | n/a | n/a | n/a | n/a |
| Per-fixture Points column | n/a | `—` | `—` (defensive — invariant says shouldn't happen) | `0` | computed |

The completeness invariant (E.1) means the "finished, no pick" column should never light up for eligible entries — but the page still renders `—` defensively if it ever does.

## Domain invariants used by the design

These are guarantees the spec relies on. Documenting them so a future reader knows where the simplifications come from.

1. **Single-phase invariant** (CLAUDE.md §Phases): only `PHASE_1` exists in user reality. Any join touching `prediction_entry_phases` filters to `phase == PHASE_1`. Phase 2 paths are not extended.
2. **Eligibility invariant** (existing): entries with `status ∈ {SUBMITTED}`, `withdrawn_at IS NULL`, `is_disabled = false` are "eligible." Only eligible entries appear in leaderboard, rarity counts, and `/community`.
3. **Completeness invariant** (new — E.1): every eligible entry must have all required match + bracket + bonus picks before tournament start. Admin runs the completeness check and chases gaps. The Results page assumes this holds and renders defensively if it doesn't.
4. **Disabled-login invariant** (existing per user 2026-06-10): users with no submitted entry have their logins disabled. The Results page never needs to render a "you have no entry" state.
5. **Datetime invariant** (CLAUDE.md): every datetime is tz-aware UTC. `aware_utc()` at service return sites. SQLite aiosqlite strips tzinfo on read — coerce defensively.
6. **Stage values are singular** (CLAUDE.md v2.161.0): `quarter_final` / `semi_final` in storage and scoring. Plurals only exist as `BracketPrediction` API field names (display convention).
7. **KO advancement timing is lineup-based** (CLAUDE.md v2.161.0): `get_actual_advancement` scans ALL knockout fixtures, not just FINISHED. Only the `winner` credit requires the final to be FINISHED + scored. This is why KO points show on LIVE / not-yet-played fixtures.
8. **Scoring parity harness** (CLAUDE.md v2.161.0): `compute_match_points` (backend) and `computeMatchPoints` (frontend) are pinned via `shared/scoring-parity-cases.json`. No changes to either in this work.

## Test matrix

### Backend tests

`backend/tests/test_completeness.py` (new):
- Entry with all picks present → `is_complete = true`, all `missing_*` = 0.
- Entry missing 3 group fixtures → `missing_match_picks = 3`.
- Entry missing some R32 picks → `missing_bracket_picks` reflects the gap, per-stage breakdown in `detail`.
- Entry missing 1 bonus answer → `missing_bonus_picks = 1`.
- Mixed gaps → all three counters non-zero.
- Withdrawn / disabled entries → excluded from the response entirely.
- CSV endpoint returns only incompletes; complete entries absent.
- Admin-only — non-admin gets 403.

`backend/tests/test_match_predictions_points.py` (new):
- Exact pick on FINISHED fixture → `base_kind="exact"`, `base=15`, rarity matches engine.
- Result-correct pick on FINISHED fixture → `base_kind="result"`, `base=5`.
- Miss on FINISHED fixture → `base_kind="miss"`, `base=0`, `total=0`.
- No score row → `points=None`.
- LIVE fixture with score row → `points=None` (only FINISHED triggers populate).
- Pool with f ≥ 0.5 → rarity = 0 (consensus gate).
- Pool with f < 1/30 → rarity = rarity_cap (10).
- Bulk-agreement query runs once per request (assert via SQL spy / `caplog`).
- Performance: list endpoint P95 < 200ms with full WC2026 fixture set + 150-entry pool fixture.

`backend/tests/test_community_predictions_rank.py` (new):
- Predictions with ranks pre-populated → response includes ranks.
- Predictions for entries not in current leaderboard → `rank = None`.
- Tied entries → both show the same rank.
- Blind-pool gate unchanged — 403 pre-lock.

### Frontend tests (vitest)

`frontend/src/lib/utils/matchDetailV4.test.ts` (the `isUpset` block — file renamed during implementation):
- Pool < 10 → false even at 0% share.
- Pool ≥ 10, winner share = 31% → false.
- Pool ≥ 10, winner share = 29% → true.
- Fixture not FINISHED → false (caller's guard, not `isUpset`'s).
- Draw (`Score.outcome = 'X'`) with 28% draw share → true.
- (Cross-fixture tie-break removed 2026-06-10 — see §Decisions C.3.)

`frontend/src/lib/utils/roundsWithLive.test.ts`:
- Empty fixture list → empty set.
- One LIVE fixture in R1 → set contains `r1`.
- LIVE fixtures across R1 + R2 → set contains both.

`frontend/src/lib/components/results/v4/*.test.ts`:
- `PointsCellGroup` renders `—` for null points, computed value for non-null.
- `PointsCellKo` renders `+5×0: 0` for 0-pick, etc. (templated number sourced from prop, not hardcoded).
- `RoundExplainer` interpolates scoring-rules values; assert that hardcoded numbers don't appear in output.
- `MissedPicksCard` renders pills WITHOUT reason chip; subtitle uses templated point value.

### Manual QA — 375px baseline

- Page renders cleanly at 375px in both `premium-night` and `hybrid` themes. No horizontal scroll.
- Round-tabs auto-scroll on mount when LIVE exists; no jump when no LIVE.
- LIVE dot pulses synchronously on round-tab AND matching Summary row.
- Entry switcher persists across Results ↔ Match Detail (URL param or store).
- Match Detail prev/next: click, ←/→ keys, horizontal swipe — all three navigation paths work, disabled at round edges.
- Latent layout `TypeError: Cannot read properties of null (reading 'pathname')` — confirm fixed if `+layout.svelte` touched, OR confirm unaffected if untouched.
- Pre-tournament gate (set `phase1_deadline` in the future via admin) → see stub.
- Post-deadline → see V4 shell with `roundsWithLive` empty, defaulting to today's round.

## Release plan

**Bundled into v2.163.0.** One PR, one deploy. Per the user's choice on E.1.

**Pre-deploy workflow** (run during build, before V4 user-facing UI lands):
1. Land completeness-check backend on the branch first.
2. Run it once against prod data via `ssh root@... docker compose exec backend python -c "..."` to surface the gap list.
3. Email/Slack any users with gaps; ask them to log in and complete picks.
4. Re-run until the list is empty.
5. Land the V4 UI on the same branch.
6. Deploy.

This honours the "completeness invariant" before the page that depends on it ships.

**Version bumps** at deploy:
- `frontend/package.json` + `frontend/package-lock.json` → `2.163.0`
- `backend/pyproject.toml` → `2.163.0`
- Append a new entry to `frontend/src/lib/data/changelog.json` of type `feature` summarising the rebuild.
- Commit as `chore(version): bump to 2.163.0`.

This release is a **minor** bump (new capability) per CLAUDE.md bump rule.

## Open risks

1. **Performance of `MatchPredictionRead.points`**. Bulk-agreement query is the mitigation; the P95 < 200ms gate verifies it. If the gate fails, fallback option is the aggregate `/api/results/entries/{id}/rounds/{round_id}` endpoint specced in the V4 handover §6 — defer until proven needed.
2. **Latent layout TypeError**. If we don't touch `+layout.svelte`, the bug persists harmlessly. If we do touch it for any reason, fix per CLAUDE.md.
3. **Microcopy churn**. Scoring-rules-templated copy means a single source of truth — but if `config/worldcup2026.yml` changes mid-tournament, the strings update without a code deploy. Test that small-number edits (e.g. round_of_32 from 20 → 25) flow through the explainer correctly. Documented for completeness; not anticipated to happen.
4. **Component count**. ~30 new components — large for one PR. Mitigate by reviewing in subtree chunks: components/results/v4/ first, then components/results/v4-match/, then the two route files, then the admin completeness chunk.
5. **Manual QA load**. Two routes × two themes × three viewport widths × ten round tabs × upcoming-vs-played × multi-vs-single-entry = a real combinatorial explosion. Recommend a concrete walkthrough checklist as part of the verification step (separate doc, not in this spec).

## Out of scope

- **Summary "you vs pool average" column** (D.3). Adds one cell per Summary row showing pool-mean subtotal and a coloured delta. Reuses `/api/leaderboard/`; no new endpoint. Deferred because: (a) it changes the Summary table's column count and would re-open the locked mobile layout; (b) it requires post-deadline empty-state handling; (c) it's strictly additive — can ship in v2.165-ish as a standalone enhancement.
- **Bracket-vs-bracket comparison view.**
- **Match Detail external sharing / server-side OG previews.**
- **Per-entry sparklines on round tabs.**
- **Push notifications for live-match starts.**
- **Admin curation of "Upset of the round" badge.** V4 ships heuristic-only; editorial override deferred.
- **Phase 2 endpoint cleanup.** `/standings/actual` and `/knockout/actual` stay gated and untouched.

## Acceptance checklist

Before opening the PR for review:

- [ ] Both routes render at 375px with no horizontal scroll.
- [ ] Both routes render in `premium-night` AND `hybrid` themes without hardcoded colours.
- [ ] Round tabs auto-select per D.1 (LIVE → today → last-completed → R1).
- [ ] Live dot pulses synchronously on round tabs and matching Summary rows.
- [ ] Entry switcher hidden for single-entry users; points summary full-width.
- [ ] Winner tab renders champion card with pending → banked/missed states; Summary table includes Winner row.
- [ ] No glow halos on pills/tabs — faint gold outline only. The ONLY glow on the page is the Tournament-total card.
- [ ] Entry switcher persists across `/results` ↔ `/results/[fixture_id]`.
- [ ] Match Detail prev/next: click, ←/→ keys, horizontal swipe all work; disabled at round edges.
- [ ] KO points show for LIVE and upcoming fixtures.
- [ ] Missed Picks card renders above R32 table with **flag + name pills only (no reason chip)**.
- [ ] Progressing card renders below all KO rounds except Final.
- [ ] Summary view rows are clickable and jump to the round tab.
- [ ] Blind-pool gate respected on `pool_stats` (null pre-lock).
- [ ] All point values in user-facing copy templated from `/api/leaderboard/scoring-rules` — grep the codebase for hardcoded `+5`, `+15`, `+20`, `+25`, `+100` in `.svelte` files inside `components/results/`; none should exist.
- [ ] Backend tests cover the matrix in §10.
- [ ] Frontend tests cover the matrix in §10.
- [ ] `docker-compose exec -T backend pytest tests/` green.
- [ ] `docker-compose exec -T frontend-dev npm run check` reports 0 errors.
- [ ] All datetimes returned by new endpoints are tz-aware UTC.
- [ ] Vocabulary check: no instance of "Outcome" in V4 user-facing copy. No "Phase 1" / "Phase 2" anywhere in V4 copy.
- [ ] Completeness check button visible on `/admin/entries`; CSV download works; modal renders empty-state banner when all eligible entries are complete.
- [ ] Page gating uses derived `phase1Deadline < now` (not the hardcoded `SHOW_CONTENT` flag).
- [ ] Pre-deploy: completeness check run against prod data, list cleared OR escalated.
- [ ] Version bump committed: `2.163.0` across `frontend/package.json`, `frontend/package-lock.json`, `backend/pyproject.toml`, and changelog.json.

## Implementation order (informational — full plan comes from writing-plans)

A rough sequence for the implementation plan to follow:

1. **Backend foundations.** `PickPointsOut` schema + `MatchPredictionRead.points` population. Tests.
2. **`CommunityPrediction.rank` extension.** Tests.
3. **Completeness service + endpoints (JSON + CSV).** Tests.
4. **Admin completeness UI.** Button + modal + CSV download.
5. **Run completeness against prod data.** Email gap-list to users. Iterate.
6. **Frontend foundations.** `upsetOfRound.ts`, `roundsWithLive.ts`, the page-gating change, `getScoringConfig()` wiring.
7. **`/results` shell.** Page composition wiring all the round-tab/summary state.
8. **Group round components.** `GroupRoundTable`, `FixtureRowGroup`, `PointsCellGroup`.
9. **Knockout round components.** `KnockoutRoundTable`, `FixtureRowKo`, `PointsCellKo`, `BracketChip`, `MissedPicksCard`, `ProgressingCard`.
10. **Summary + Winner tabs.** `SummaryView`, `WinnerView`.
11. **`/results/[fixture_id]` page shell.** Played + upcoming variants of the body.
12. **Match Detail components** — hero, your-pick, rarity explainer, pool list/split, scoreline spread.
13. **Manual QA pass.** 375px both themes, all interaction paths.
14. **Version bump + changelog + commit.**

## References

- V4 handover: [mockups/Results-redesign/HANDOVER.md](mockups/Results-redesign/HANDOVER.md).
- V4 visual contract: `mockups/Results-redesign/V4-Results-MatchDetail-bundle.html`.
- React reference (data + page shapes): `mockups/Results-redesign/reference/v4-{results,match,data}.jsx`.
- Scoring system: [docs/scoring-system.md](docs/scoring-system.md).
- Scoring engine: [backend/app/services/scoring.py](backend/app/services/scoring.py).
- Existing Results stub: [frontend/src/routes/results/+page.svelte](frontend/src/routes/results/+page.svelte).
- Match-breakdown utility (reused, not modified): [frontend/src/lib/utils/matchBreakdown.ts](frontend/src/lib/utils/matchBreakdown.ts).
- Scoring parity goldens: `shared/scoring-parity-cases.json`.
- Domain invariants: [CLAUDE.md](CLAUDE.md).
