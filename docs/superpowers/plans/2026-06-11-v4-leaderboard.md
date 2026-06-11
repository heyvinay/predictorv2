# V4 Leaderboard Implementation Plan (v2.164.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rebuild `/leaderboard` per `mockups/Leaderboard-redesign/` — Standings
table + pool filters, entry detail drawer, Race bump chart, Insights cards —
wired to real backend data, feature-complete for production tomorrow.

**Architecture:** Mostly frontend (new `components/leaderboard/v4/` tree +
page rewrite), with three additive backend extensions: V4 fields on
`LeaderboardEntry` (employer pool, champion/finalist picks + alive flags,
snapshot-based daily movement), a bulk snapshots endpoint for the Race chart,
and `hit`/`points` on bonus prediction reads for the drawer. No schema
migrations. No changes to dormant phase-2 paths. Everything PHASE_1-filtered.

**Tech stack:** FastAPI + SQLModel (backend), SvelteKit + TS + Tailwind/DaisyUI
(frontend), existing `getFlagUrl`/`teamCode` utils (NOT flag-icons npm — repo
convention wins), pytest + vitest + svelte-check gates, worktree-overlay test
pattern.

---

## Decisions locked (deviations from mock, repo wins per ACCEPTANCE.md)

| Mock says | Repo reality | Decision |
|---|---|---|
| Pools Atlas/JMFA/Guests | `User.employer` enum `atlas/jmfa/neither` | Map employer→pool; `neither`/`null` → Guests |
| flag-icons CDN, `fi fi-xx` | `getFlagUrl()` flagcdn + `teamCode()` TLA | Use repo utils |
| exact 15 / result 5 base | `correct_outcome: 5`, `exact_score: 10` (exact total base = 15) | Identical net; pill totals from `PickPoints.total` |
| +40 champ / +15 finalist insight constants | `winner: 100`, `final: 75` | Use `/leaderboard/scoring-rules` values |
| Rank history per checkpoint R1…QF | Daily `LeaderboardSnapshot` (UTC date) | Race chart x-axis = days; movement chip = vs yesterday's snapshot |
| Bonus folded: Q1–Q2 → Group, Q3–Q4 → KO | `category: group_stage` (15) / `top_flop` (20) | Fold by category; `bonus_question_points` split via per-question hits |
| 14 insight cards | 5 need all-entries per-fixture data (not served) | Ship 9 real cards; 5 behind `INSIGHTS_EXTENDED = false` flag (pre-authorized by ACCEPTANCE M4) |
| Virtualize 200 rows | ~100 entries, compact 36px grid rows | No virtualization (YAGNI); sticky header yes |
| `v4lb:view`/`v4lb:pool` localStorage | repo uses `predictor:` prefix | `predictor:lb:view`, `predictor:lb:pool` |
| Drawer "story line" sentence | derivable client-side | Build from movement + champion alive + finalists alive |
| Stage group/knockout | lineup-based advancement (v2.161.0) | `stage='knockout'` when any non-group fixture has a team seeded |
| Feature flag default | V4 Results pattern is `false` | `V4_LEADERBOARD_ENABLED = true` **and** deadline-gated (tournament starts today; user needs prod tomorrow; current page is a stub either way — flag stays as 60-second rollback) |

**Tie-break note:** backend sorts by `(total_points, exact_scores)` and ties
share rank — matches ACCEPTANCE "standard competition ranking is fine".
Do NOT re-rank client-side; pool filtering keeps the server's global ranks.

---

## File map

### Backend (modify)
- `backend/app/schemas/leaderboard.py` — add V4 fields to `LeaderboardEntry`
- `backend/app/services/leaderboard.py` — compute V4 fields in `_rebuild_leaderboard`; new helpers `_load_team_picks`, `get_eliminated_teams`, `_load_yesterday_positions`
- `backend/app/api/leaderboard.py` — new `GET /snapshots` (bulk), schema
- `backend/app/schemas/prediction.py` (or wherever `BonusPredictionResponse` lives) — add `hit`, `points`, `category`
- `backend/app/api/entry_predictions.py` — populate bonus hit/points
- `backend/tests/test_leaderboard_v4.py` — new (champion/alive/pool/movement)
- `backend/tests/test_bonus_read_scoring.py` — new (bonus hit fields)

### Frontend (create)
- `frontend/src/lib/types/leaderboard.ts` — ALL V4 types (outside barrel — never touch `types/index.ts`)
- `frontend/src/lib/utils/leaderboardV4.ts` — pure derivations: pool mapping, stage detection, bonus fold, DNA extraction, ceiling calc, story line; unit-tested
- `frontend/src/lib/utils/leaderboardV4.test.ts`
- `frontend/src/lib/components/leaderboard/v4/` —
  `YouTag.svelte`, `MoveChip.svelte`, `FlagCode.svelte`, `RankChip.svelte`,
  `LbHeader.svelte` (title + view pills), `YourEntriesStrip.svelte` (+ pool pills),
  `StandingsTable.svelte`, `StandingRow.svelte`,
  `EntryDrawer.svelte`, `DnaBar.svelte`, `BracketSection.svelte`,
  `GroupPicksSection.svelte`, `BonusSection.svelte`,
  `RaceChart.svelte`, `InsightsGrid.svelte` + card components (one file per card, shared `InsightCard.svelte` shell + `MiniRow.svelte`)
### Frontend (modify)
- `frontend/src/lib/api/leaderboard.ts` — V4 types on existing fns + `getAllTrajectories`, bonus questions fetch
- `frontend/src/routes/leaderboard/+page.svelte` — full rewrite (stub preserved pre-deadline/flag-off)

---

## Task 1 — Backend: V4 fields on LeaderboardEntry

**Files:** `backend/app/schemas/leaderboard.py`, `backend/app/services/leaderboard.py`, test `backend/tests/test_leaderboard_v4.py`

- [ ] Add to `LeaderboardEntry` schema (all defaulted → additive, no caller breaks):
```python
    employer: str | None = None          # "atlas" | "jmfa" | "neither"
    champion_pick: str | None = None     # team name as stored in TeamPrediction
    champion_alive: bool = True
    finalist_picks: list[str] = []       # 0-2 team names (stage='final')
    finalists_alive: int = 0
    daily_movement: int | None = None    # vs yesterday's snapshot; None = no snapshot yet
```
- [ ] Service: bulk-load picks once per rebuild (PHASE_1 ONLY — ★ invariant):
```python
async def _load_team_picks(session, entry_ids):
    """{entry_id: {"winner": [teams], "final": [teams]}} for eligible entries."""
    rows = (await session.execute(
        select(TeamPrediction.entry_id, TeamPrediction.stage, TeamPrediction.team)
        .where(TeamPrediction.entry_id.in_(entry_ids))
        .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
        .where(TeamPrediction.stage.in_(["winner", "final"]))
    )).all()
```
- [ ] Service: `get_eliminated_teams(session) -> set[str]` —
  (a) losers of FINISHED knockout matches (winner via `Score.outcome` semantics
  already used in `get_actual_advancement` — reuse its fixture+score query
  shape); (b) once EVERY round_of_32 fixture has both teams seeded, any team
  appearing in group fixtures but in no knockout lineup. Conservative: alive
  until provably out.
- [ ] Service: `_load_yesterday_positions(session) -> dict[entry_id, int]` —
  one query: latest `LeaderboardSnapshot` per entry with `captured_date < today`
  (use `DISTINCT ON` / window or group-by-max; aware_utc not needed — date col).
- [ ] Wire all three into `_rebuild_leaderboard` (after `eligible` is loaded;
  `entry.user.employer` is already eager-loaded via `entry.user`— verify, else add selectinload).
  `champion_alive = champion_pick not in eliminated`; `finalists_alive = sum(t not in eliminated for t in finalist_picks)`;
  `daily_movement = prev - position if prev else None`.
- [ ] Tests (async sqlite fixtures per existing test conventions — copy setup from `backend/tests/test_leaderboard*.py`):
  1. employer + champion/finalist picks appear on response rows
  2. eliminated KO loser → `champion_alive=False`
  3. team not in any KO lineup while R32 fully seeded → eliminated
  4. R32 only partially seeded → group teams NOT eliminated
  5. `daily_movement` from snapshot rows; `None` with no snapshots
  6. phase_2 TeamPrediction rows are ignored (double-count guard)
- [ ] Run: overlay to main worktree, `docker-compose exec -T backend pytest tests/test_leaderboard_v4.py -v` → PASS; restore overlay
- [ ] Commit `feat(leaderboard): V4 row fields — pool, champion/finalists alive, daily movement`

## Task 2 — Backend: bulk snapshots endpoint (Race chart)

**Files:** `backend/app/api/leaderboard.py`, `backend/app/services/snapshots.py`, test `backend/tests/test_snapshots_bulk.py`

- [ ] `GET /api/leaderboard/snapshots?days=N` (N 2–90, default 30) →
```python
class AllTrajectoriesResponse(BaseModel):
    days: int
    entries: list[EntryTrajectory]   # entry_id, entry_name, user_name, points: list[RankSnapshotPoint]
```
  One query over `LeaderboardSnapshot` joined to eligible entries, ordered by
  entry/date. Append live current position per entry from cached
  `calculate_leaderboard` (same trick as `/snapshots/me`). Blind-pool: pre-lock
  return only requester's entries (mirror `/api/leaderboard/` gate).
- [ ] Tests: shape, ordering oldest→newest, live point appended, blind-pool gate.
- [ ] Overlay-run, commit `feat(leaderboard): bulk rank-trajectory endpoint for race chart`

## Task 3 — Backend: bonus read scoring fields

**Files:** schema holding `BonusPredictionResponse`, `backend/app/api/entry_predictions.py:411-427`, test

- [ ] Add `category: str`, `points: int`, `hit: bool | None = None` (None = unsettled).
  In the GET route: load questions (`get_bonus_questions()`), load settled
  `BonusAnswer` rows for the competition, mark `hit` via the same
  `answer_in()` matcher `calculate_bonus_points` uses (import, don't copy).
- [ ] Tests: unsettled → `hit=None`; settled match → `hit=True, points=15/20`;
  settled miss → `hit=False`; multiple tied correct answers honoured.
- [ ] Overlay-run, commit `feat(predictions): bonus reads expose settled hit + points`

## Task 4 — Frontend: types + API client + pure utils

**Files:** create `frontend/src/lib/types/leaderboard.ts`, `frontend/src/lib/utils/leaderboardV4.ts` (+`.test.ts`); modify `frontend/src/lib/api/leaderboard.ts`

- [ ] `types/leaderboard.ts`: `LbEntryV4` (server row incl. V4 fields + breakdown),
  `LbView = 'table'|'race'|'insights'`, `LbPool = 'All'|'Atlas'|'JMFA'|'Guests'`,
  `Stage = 'group'|'knockout'`, `EntryTrajectory`, `AllTrajectoriesResponse`,
  `BonusPredictionRead` (with hit/points/category), `DnaSplit {exact,result,rarity,bracket}`.
  Import shared bits from `$lib/types/results` (PickPoints, ScoringRules) — NEVER from `$types` barrel for new stuff.
- [ ] `api/leaderboard.ts`: `getLeaderboardV4()` (same URL, V4 response type),
  `getAllTrajectories(days)`, `getEntryBonusPredictions(entryId)`,
  `getBonusQuestions()` (reuse if an api fn exists — check `api/predictions.ts` first).
- [ ] `utils/leaderboardV4.ts` pure fns (each unit-tested):
  - `poolOf(employer: string|null): LbPool` (`atlas→Atlas, jmfa→JMFA, else Guests`)
  - `filterByPool(rows, pool)` — keeps server `position` untouched
  - `deriveStage(fixtures): Stage` — knockout iff any non-group fixture has a seeded team
  - `dnaOf(breakdown): DnaSplit` — exact=`exact_score_points`, result=`match_outcome_points`, rarity=`hybrid_bonus_points`, bracket=`bracket_total` (phase1+2 computed props already)
  - `foldBonus(bonusReads): {group: number, knockout: number, perQuestion}` — category `group_stage`→group else knockout
  - `ceilingOf(row, rules, remainingFixtures, stage)` — banked + alive champion×`advancement.winner` + alive finalists×`advancement.final` + shared remaining match max
  - `storyLine(row): string` — e.g. "Climbed 2 after yesterday · Brazil title pick alive · 2 of 2 finalists standing"
  - `bestOwnSummary(rows, userId): {bestRank, ptsOffLead} | null`
- [ ] Run vitest via overlay → PASS; `npm run check` → 0 errors; commit
  `feat(leaderboard): V4 types, api client, derivation utils`

## Task 5 — Frontend M1: page shell + standings table

**Files:** rewrite `frontend/src/routes/leaderboard/+page.svelte`; create primitives + `LbHeader`, `YourEntriesStrip`, `StandingsTable`, `StandingRow`

Match `screenshots/standings.png` + mock HTML (`V4 - Leaderboard.html`) for
exact spacing/colors, translated to DaisyUI tokens (`bg-base-200` cards,
`border-base-300`, gold = `primary`, green `#34d399`→`text-success`, red→`text-error`).

- [ ] Page gate mirrors results page exactly:
```svelte
const V4_LEADERBOARD_ENABLED = true; // 60-second rollback: flip to false
$: lbOpen = V4_LEADERBOARD_ENABLED && !!$phase1Deadline &&
            new Date($phase1Deadline).getTime() < Date.now();
```
  `!lbOpen` → keep the existing pre-tournament stub markup verbatim.
- [ ] Data load on mount (parallel): `getLeaderboardV4()`, `fetchAllFixtures()`,
  `getScoringRules()`, `getBonusQuestions()`; reactive `$user` pattern copied
  from results `+page.svelte:119-123`. 60s refresh via existing polling store
  OR a local `setInterval` re-fetching leaderboard only.
- [ ] Header per spec §1 (eyebrow gold 10–11px tracking .12em; `Leaderboard`
  in `font-hero` 44px; subtext entries · round · locked line; 3 view pills
  right, active = gold border + soft glow ring).
- [ ] Your-entries strip §2: gold-tint band; "best is **#n** · m pts off the
  lead"; pool pills with count badges; active pill gold; persists
  `localStorage['predictor:lb:pool']`; filtering keeps global ranks; empty
  pool → "No entries in this pool" row.
- [ ] Standings table §3, desktop grid
  `70px minmax(0,1fr) 104px 56px 80px 90px 80px` (Final col only when
  `stage==='knockout'` — omit from grid entirely in group stage);
  `<880px` hide Group/Knockout cols. Compact rows (~36px), sticky header,
  hover bg, whole row a `button` (Enter opens drawer — a11y per ACCEPTANCE).
  - RankChip: gold/silver/bronze tints top 3 (reuse `.position-badge` palette)
  - MoveChip: `▲n` success / `▼n` error / `—` muted from `daily_movement`
    (`null`→`—`); aria-label "up n places"
  - Entry cell: 30px initials avatar, name, owner beneath; own entries =
    gold ring + `YouTag` + glow row (left 3px gold inset + gradient) + gold Total
  - Champ cell: `FlagCode` (24×17 flag img via `getFlagUrl` + `teamCode()` TLA)
    + ✓/✗ dot; eliminated = greyscale flag 45% + muted code
  - Final dots (KO only): 2 dots, alive = green glow; title tooltip
  - Group/KO pts cells: title tooltip with bonus fold breakdown (Q ✓/✗)
  - Skeleton rows while loading; inline retry banner on error
- [ ] `npm run check` 0 errors (overlay); browser smoke (Task 9 harness) at
  1280px + 375px; commit `feat(leaderboard): V4 standings table + pool filters (M1)`

## Task 6 — Frontend M2: entry detail drawer

**Files:** `EntryDrawer.svelte`, `DnaBar.svelte`, `BracketSection.svelte`, `GroupPicksSection.svelte`, `BonusSection.svelte`

- [ ] Drawer chrome: fixed right panel `min(480px,94vw)`, full height,
  `bg-base-200`, scrim `rgba(2,6,18,.55)`; Svelte `transition:fly={{x:40,duration:250}}`
  + `fade` scrim; close on ✕ / Esc / scrim; internal scroll only
  (`overflow-y-auto`, body scroll locked while open); focus trap + restore
  (focus drawer on open, return focus to row on close).
- [ ] On open fetch in parallel: `getEntryBreakdown(id)`,
  `api: /entries/{id}/predictions/matches` (has `points: PickPoints`),
  `/entries/{id}/predictions/bracket`, `getEntryBonusPredictions(id)`.
  Spinner center panel while loading; retry banner on failure. Works for ANY
  entry post-deadline (open pool — backend already enforces).
- [ ] Sections in spec order §4: header (avatar/name/YOU/rank+move) → story
  line box → summary cells (Total gold / Group / Knockout with `+n bonus`
  inline via `foldBonus`) → DNA stacked bar + counts line
  (`exact_scores` exact · `correct_outcomes - exact_scores` results · rarity
  hits from breakdown presence · `n/4 bonus`) → champion row → bracket
  (Finalists, Semis, QFs — latest first; chip states hit/out/pend derived
  from fixtures store lineups + eliminated logic client-side: hit = team
  seeded into that stage, out = `champion-style` eliminated before it,
  pend = otherwise; per-round header `hits/picks through · n alive · +pts`
  using `rules.advancement`) → group picks R3→R2→R1 latest-first (reuse
  `deriveGroupMatchdays` from `resultsRounds.ts` for round bucketing;
  fixture row grid `1fr 40px 104px`; coin pill: EXACT green tint / RESULT
  amber / MISS muted no coin / LIVE red / upcoming `–`; totals from
  `points.total`, tooltip base+rarity split) → bonus questions (hit = faint
  green bg + `+15/+20` pill; unsettled = muted "pending" pill) → open-pool
  footer note.
- [ ] `npm run check`; browser smoke incl. keyboard (Esc, focus return),
  375px (94vw width); commit `feat(leaderboard): entry detail drawer (M2)`

## Task 7 — Frontend M3: Race chart

**Files:** `RaceChart.svelte`

- [ ] Fetch `getAllTrajectories(30)` lazily on first switch to Race view.
  SVG: x = snapshot dates (label MMM d), y = rank 1..total; field lines
  1.4px `stroke-base-content/22`; leader (current rank 1) `text-success`
  2px; own entries gold 2.6px. Right edge `rank. name` labels. Hover (12px
  invisible hit stroke): thicken hovered, dim others to 18%, checkpoint
  dots, tip bar below with name · owner · pts · rank path. Legend chips
  top-right. Mobile: horizontal scroll container, min-width chart.
- [ ] Empty state (≤1 snapshot day): "Race chart unlocks after the first
  full day of scoring."
- [ ] `npm run check`; smoke; commit `feat(leaderboard): race bump chart (M3)`

## Task 8 — Frontend M4: Insights grid

**Files:** `InsightsGrid.svelte`, `InsightCard.svelte`, `MiniRow.svelte`, one component per card

- [ ] `const INSIGHTS_EXTENDED = false;` — gates the 5 cards needing
  all-entries per-fixture data (Herd & mavericks, Heartbreak, Biggest hauls,
  Hot hand, Pick twins). Ship 9 real cards, all computed client-side from
  already-loaded leaderboard + fixtures + rules:
  1. **Points DNA** (wide) — top 8 + own entries, `dnaOf()` stacked bars
  2. **Who picked whom for champion** — group rows by `champion_pick`; eliminated grey + OUT tag; YOU markers
  3. **If they lift the trophy…** — per alive champion: leader after `+rules.advancement.winner` to its backers; NEW LEADER tag on flip
  4. **Points still on the table** (wide) — `ceilingOf()`; banked bar + striped extension; `cur → ceiling`
  5. **Tournament superlatives** — goals for/against per team from FINISHED group fixtures; flop = highest FIFA-ranked team eliminated (use `fifaRankings.json`); dark horse = lowest-ranked team alive deepest
  6. **Atlas vs JMFA** (wide) — avg pts, exacts, alive champions, top-10 counts; scoreline footer
  7. **Contrarian index** — top 5 by `rarity/total` share, % bar
  8. **Exact-score snipers** — top 5 by `exact_scores`, dot strip
  9. **Movers** — `getSteepestClimbers(…)`; ▲3 climbing / ▼3 sliding
- [ ] 2-col grid, 1-col `<860px`; wide cards span 2; YOU rows gold-tinted everywhere.
- [ ] `npm run check`; smoke; commit `feat(leaderboard): insights grid, 9 cards (M4)`

## Task 9 — Verification + ship prep (NO prod deploy)

- [ ] Overlay full surface to main worktree; run **all** gates:
  `pytest tests/ -v` (full suite), `npx vitest run`, `npm run check` (0 errors)
- [ ] Browser smoke in dev (chrome/preview tools): `/leaderboard` desktop
  1280 + 375px, BOTH themes (`premium-night`, `hybrid`); all three views;
  drawer open/close/keyboard; pool filters; flag-off check (set const false
  → stub renders). Verify against screenshots.
- [ ] Restore main worktree clean (`git status` must match pre-session state)
- [ ] Version bump to **2.164.0** (frontend/package.json, package-lock ×2 spots,
  backend/pyproject.toml) + changelog entry appended (`type: feature`,
  user-friendly summary) + `chore(version): bump to 2.164.0`
- [ ] Update CLAUDE.md (V4 Leaderboard section: flag location, gotchas) +
  memory file `predictorv2_results_leaderboard_rebuild.md`
- [ ] Merge worktree branch → main `--no-ff` locally; **do not push/deploy**
  (user deploys tomorrow); write next-session handover note

## Self-review checklist (run after Task 8)
- Every ACCEPTANCE M1–M4 checkbox addressed or consciously flagged
- No `$types` barrel imports for new types; `types/index.ts` untouched
- No phase_2 logic anywhere; every TeamPrediction query PHASE_1-filtered
- No raw hex in Svelte (semantic tokens; `text-warning-text` not `text-warning`)
- All datetimes aware; no `datetime.utcnow()`
