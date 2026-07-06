# CLAUDE.md

Guidance for Claude Code when working in this repo.

## Project

**The Predictor v2** — self-hosted web app for running international football
prediction competitions (World Cup, Euros) among ~100 friends. Current focus:
**World Cup 2026**.

## Tech stack

**Backend:** FastAPI (Python 3.11+), SQLModel, PostgreSQL 16, Alembic.
Tournament config in YAML (`config/worldcup2026.yml`). Two external HTTP
integrations: **Football-Data.org** for live match scores
(`backend/app/services/external/football_data.py`) and **The Odds API** for
live betting odds (`backend/app/services/odds_cache.py`), the latter
consumed by the Betting Odds Smart Fill method. Both are unauthenticated
read-only endpoints from the backend's perspective. A third, **optional**
integration (v2.177.0) writes *out* to **Google Sheets** via a service
account (`backend/app/services/sheets_sync.py`) — mirrors the all-entries
predictions matrix + live standings into a shared read-only sheet,
pushed from the score scheduler. Dormant unless `GOOGLE_SHEET_ID` +
`GOOGLE_SERVICE_ACCOUNT_JSON` are set; spec at
`docs/superpowers/specs/2026-06-15-google-sheets-sync-design.md`.

**Frontend:** SvelteKit + TypeScript, Tailwind + DaisyUI (themes
`premium-night` default / `hybrid` alternative), `svelte-motion`,
`flag-icons`. Vitest for unit tests.

**Infra:** Docker Compose for dev, Nginx + Cloudflare Tunnel in prod.

**Production deploy:**

```bash
ssh root@167.235.145.76 'cd /opt/predictor && git pull && docker compose --profile prod up -d --build'
```

→ https://wc26.heyvinay.com. Production lives at `/opt/predictor` on
the VPS; nginx config is bind-mounted from `nginx/nginx.conf` in the
repo.

**★ Never ship without an explicit instruction (mandatory rule).** Do
NOT run the SSH deploy command above, do NOT `git push origin main`
that triggers a deploy, and do NOT bump versions in anticipation of
shipping — unless the user has said "ship it" / "deploy" / "push it
to prod" / an unambiguous equivalent in the CURRENT message.
"Implement the plan," "fix that," "yes do it," or any other
implementation instruction is authorization to write code, run tests,
and commit locally — NOT to deploy. Design approval ≠ deploy approval.
When implementation completes, STOP and summarise what's ready; then
wait for the ship signal. If in genuine doubt about intent, ask —
one clarifying question is cheaper than an unwanted production
release. This rule overrides any "keep moving" heuristic; the cost of
a wrong deploy (leaderboard cache invalidation, cold-cache latency
spike, potential regressions for ~180 users mid-tournament) is
strictly greater than the friction of one more confirmation. **When the release touches `nginx/nginx.conf`, append
`&& docker compose --profile prod up -d --force-recreate nginx`** —
`up -d --build` does not restart `image:`-only services, so the
bind-mounted edit never reaches the running nginx process. The
force-recreate is a no-op when nginx.conf hasn't changed, so it is
safe to make permanent in the deploy line if you prefer.

**`JWT_SECRET_KEY` is fail-closed in production (v2.176.4+).** When
`DEBUG=false`, the Settings validator at
`backend/app/config.py:_enforce_secret_strength` rejects blank,
short (<32 chars), or known-placeholder signing keys — the backend
container refuses to boot rather than start with a forgeable key.
A fresh env (dev clone, new VPS, staging) MUST set `JWT_SECRET_KEY`
to a 32+ char random value (or set `DEBUG=true`) before the backend
will start. Generate one with
`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
Test coverage in `backend/tests/test_config_secret.py`. Rotating
the prod secret signs everyone out — pool members just re-request a
magic link. Before any deploy that adds a fail-closed startup
check (this validator, future migrations, new required env vars),
dry-run a throwaway container against the new code on the VPS:
`docker compose --profile prod run --rm --no-deps backend python -c
'from app.config import get_settings; get_settings()'`. The live
container keeps serving traffic during the dry-run; if the
throwaway crashes, fix `.env` without ever restarting the live
backend.

## Layout

```
/backend/app/{api,models,schemas,services}   FastAPI routes, SQLModel tables, Pydantic, business logic
/backend/alembic/versions                    Schema migrations (single source of truth)
/backend/tests                               pytest suite
/frontend/src/lib/{api,components,stores,types,utils}
/frontend/src/lib/components/{bracket,predictions,results}   feature subfolders
/frontend/src/routes                         SvelteKit pages
/config                                      tournament YAML
/docs                                        long-form docs (scoring system, etc.)
```

## Domain invariants

### Phases — SINGLE PHASE ONLY (mandatory rule, ★ read first)

**This competition has one phase. Phase 2 does not exist.** The database
still creates a `phase_2 = DRAFT` row alongside every entry's `phase_1`
row at creation time, and the codebase still has phase_2 code paths,
but those are **legacy noise** — the equivalent of a dormant feature
flag that will never flip
(`competition.is_phase2_active = false` permanently).

Rules for plans, analyses, debugging, queries, and any new code:

- **Always filter to `phase = PHASE_1`** when joining
  `prediction_entry_phases` (or `phase == PredictionPhase.PHASE_1` in
  Python). A join without this filter silently double-counts every
  entry — each carries two phase rows. This bug has bitten landing /
  admin / scoring stats multiple times; most recently the prize-pot
  count in v2.160.3.
- **Never propose Phase 2-dependent features.** No "support both
  phases," no "smoke-test when Phase 2 is re-enabled," no abstractions
  to handle both phases generically. Dormant means dormant. Plans that
  budget time for Phase 2 are wrong.
- **Never use "Phase 1" / "Phase 2" in user-facing copy.** Pages,
  emails, status pills, error messages, navbar chips — all use
  unphased language ("the deadline", "your entry", "submissions are
  closed"). The `/rules` page, FAQ, `DeadlineBanner`, landing
  components, and submission emails were rewritten in v2.149.x to drop
  phase language and must stay that way.
- **In call-site audits and refactors, silently skip Phase 2 paths.**
  Don't flag dormant phase_2 code as a follow-up. Don't propose
  cleaning it up. The cost of churning legacy paths outweighs any
  notional simplification — they pay for themselves by keeping
  migrations / tests passing.

If a plan, analysis, or fix seems to need Phase 2 to make sense, you
have misread the problem. Re-check.

- **Phase 1** (the only phase) — group-stage scores + knockout-bracket
  advancement + bonus questions. Every entry must be in before
  `competition.phase1_deadline`.

### Locking & visibility
- **One global deadline** is the practical lock for the current competition:
  every prediction (group scores, knockout bracket, bonus questions) must be
  in before `competition.phase1_deadline`. User-facing copy frames it as
  "the deadline" everywhere (`/rules`, `FaqSection` Q1, `CountdownBand`).
- The per-match 5-minute pre-kickoff lock still exists in
  `backend/app/services/locking.py` but is not reached in practice for the
  single-phase competition — the deadline trips first.
- Blind pool: users cannot see others' predictions until the deadline.
- 100% data integrity — never silently drop or overwrite a prediction.

### Scoring
Modes — `logarithmic` (default, Shannon-surprisal rarity bonus), `fixed`
(flat), and `hybrid` (legacy linear rarity). Selected via `scoring.mode` in
`config/worldcup2026.yml`. Engine in `backend/app/services/scoring.py`.
See `docs/scoring-system.md` for the formula, bonus table, and rationale.

**Rule:** no scoring logic changes without a corresponding `pytest` case.

**Stage values are SINGULAR (★ invariant, v2.161.0).**
`TeamPrediction.stage` stores `quarter_final` / `semi_final` — matching
`Fixture.stage`, the YAML `scoring.advancement` keys, and the email
recap. The plural spellings (`quarter_finals` / `semi_finals`) exist
ONLY as `BracketPrediction` API field names (a display convention).
`normalize_stage()` in `backend/app/models/prediction.py` is the
write-side guard that converts plural payloads from stale cached
frontend bundles; migration `b3c4d5e6f7a8` converted historical rows.
Never write plural stage values; never compare stored stages against
plural literals.

**`third_place` is an UNSCORED fixture stage (★ invariant, v2.164.0).**
Football-Data ingests the bronze-medal playoff (semi-final losers, the
day before the actual final) as `Fixture.stage = 'third_place'`. The
prediction pool does NOT collect picks for it and the scoring engine
does NOT award points for it — the YAML's `scoring.advancement` block
is the authoritative whitelist of scored stages, and `third_place` is
not in it. Any UI bucketer, scoring path, or results surface that
enumerates knockout stages MUST exclude `third_place`. The round
bucketer at [resultsRounds.ts:104-118](frontend/src/lib/utils/resultsRounds.ts:104)
returns `null` for it (regression-pinned in
`resultsRounds.test.ts`); previously it shared the Finals bucket and
produced a phantom second TBD-vs-TBD row in the V4 Results page.
Unrelated namesake: `bracketConfig.ts` uses `"third_place"` to mean
"best third-placed group team" (a seeding mechanism for R32) —
that's a different concept and stays.

**Advancement timing is lineup-based (v2.161.0).** Knockout "reached
stage X" credit fires when a team is seeded into a stage-X fixture
(`get_actual_advancement` scans ALL knockout fixtures, not just
FINISHED). Only the `winner` credit requires the final to be FINISHED +
scored. Group-stage match points still pay on match completion.

**KO lineup resolver chain (v2.184.x, ext_id mapping completed
v2.195.1).** Extends the v2.182.x R32-only `r32_resolver` to cover
every KO stage. Slot placeholders (`slot: {stage}:{ext}:{home|away}`)
on R16/QF/SF/F fixtures resolve at READ TIME as upstream matches
finish: R16 home = winner of source R32, QF home = winner of source
R16, etc. Implementation in `backend/app/services/ko_lineup_resolver.py`;
source maps in `backend/app/services/bracket_seeding.py` (`R32_SOURCES`,
`ROUND_OF_16_SOURCES`, `QUARTER_FINAL_SOURCES`, `SEMI_FINAL_SOURCES`,
`FINAL_SOURCES`). Applied in `backend/app/api/fixtures.py:fixture_to_read()`
and `backend/app/services/ko_match_detail.py`. DB rows stay untouched —
when Football-Data eventually backfills FIFA's official lineup, the
resolver becomes a no-op (placeholder no longer matches). Frontend
mirror in `frontend/src/lib/utils/bracketGeometry.ts` powers the
BracketQuadrant SVG. Memory note: `predictorv2-ko-lineup-resolver`.

**★ Match-number lookup is ext_id-based for EVERY KO stage — never
kickoff-sorted (v2.195.1 fix).** `EXT_ID_TO_MATCH_NUMBER` in
`bracket_seeding.py` is a single hand-verified map covering R32
through the Final (`537415..537430` → M73-M88, `537375..537382` →
M89-M96, `537383..537386` → M97-M100, `537387..537388` → M101-M102,
`537390` → M104; M103 third_place omitted, unscored). Before v2.195.1,
R16+ stages were indexed by sorting fixtures by kickoff and assigning
`stage_base + index` — this silently swapped Paraguay–France (M89)
with Canada–Morocco (M90) because FIFA scheduled M89 to kick off
FOUR HOURS AFTER M90 on Sat 4 Jul 2026, breaking the "match numbers
are chronological" assumption. **Never reintroduce a kickoff-sort
fallback for any KO stage** — FIFA match numbers are a STRUCTURAL
bracket-position concept; kickoff time is an independent broadcast-
scheduling decision, and the two can and do diverge. A KO fixture
whose ext_id isn't yet in the map should surface as an unresolved
slot placeholder, not be guessed at via kickoff order. Regression
tests: `backend/tests/test_r32_ext_id_mapping.py` (R32),
`backend/tests/test_ko_ext_id_mapping.py` (R16/QF/SF/Final — pins the
M89/M90 case by name). Frontend mirror
`EXT_ID_TO_MATCH_NUMBER` in `bracketGeometry.ts` (renamed from the old
R32-only `R32_EXT_ID_TO_MATCH_NUMBER`) follows the same rule.

**Bracket parity (v2.184.x).** The frontend `bracketConfig.ts` and the
backend `bracket_seeding.py` encode the same FIFA bracket structure.
They stay in sync via a checked-in snapshot at
`shared/bracket-sources-snapshot.json` (regenerated by
`backend/scripts/regen_bracket_parity_snapshot.py`) plus the pytest
suite at `backend/tests/test_bracket_parity.py` — CI fails if anyone
edits one source-of-truth file without regenerating the snapshot.
Workflow: edit `bracketConfig.ts` → run the regen script → mirror the
change in `bracket_seeding.py` → commit all three together. Memory
note: `predictorv2-bracket-parity-workflow`.

**KO fixture display — per-side seeded check (v2.184.x).** Any code
touching a KO fixture's home/away team names must use PER-SIDE
resolution checks (`!!f.home_team && !f.home_team.startsWith('slot:')`,
same for away), never a binary "either side is slot → both TBD" gate.
The downstream resolver chain produces partial-resolution states (one
side real, one side `slot:*`) during the tournament; the binary check
collapsed those to "TBD vs TBD" in v2.183.3 and hid user's banked
points from totals. The pattern got duplicated across four consumer
sites before being fully swept in v2.185.0. The `lineupSeeded()`
helper in `koPoints.ts` keeps its all-or-nothing semantic intentionally
— it gates the "missed R32 picks" surface that only makes sense once
the entire round's lineup is settled. Memory: `feedback-per-side-seeded-check`.

**Scoring parity harness (v2.161.0).** The pure
`compute_match_points()` (backend `scoring.py`) and `computeMatchPoints`
(frontend `matchBreakdown.ts`) are pinned to agree via the golden cases
in `shared/scoring-parity-cases.json` — run by both
`backend/tests/test_scoring_parity.py` and
`frontend/src/lib/utils/matchBreakdown.parity.test.ts`. Any change to
either implementation must keep both suites green; add new cases to the
shared JSON, not to one side only. The `shared/` dir is mounted into
both containers (`./shared:/app/shared:ro`).

**Rarity eligibility (v2.161.0).** Rarity-bonus denominators count only
eligible entries (SUBMITTED, not disabled, not withdrawn) via
`eligible_entry_ids_select()` — shared by `get_all_outcome_counts` and
`compute_agreements`. Draft/withdrawn/disabled predictions are invisible
to rarity math by design.

**Admin score editor (v2.162.0).** `/admin/sync` is the escape hatch
when Football-Data.org fails, lags, or serves a wrong score
mid-tournament. Every fixture row has an Edit button that expands inline
into a form: score inputs for any fixture, plus ET/penalty fields and
team-seeding text inputs on knockout rows. A confirm dialog spells out
the consequence ("marks the match FINISHED and updates the leaderboard
for everyone") before write. Manual saves go through
`PUT /api/scores/{fixture_id}` and set `verified=true` by default; the
60-second API sync **skips verified scores** (see
`score_sync._apply_external_score`), so a manual correction survives
the scheduler. The level-knockout guard forces ET/pens for any drawn
knockout result so `Score.outcome` can resolve a winner. Audit events
`score.manual_update` and `fixture.admin_update` (old → new values)
fire on every edit. Spec lives at
`docs/superpowers/specs/2026-06-10-admin-score-editor-design.md`.

**V4 Results + Match Detail + admin completeness (v2.163.0).** Shipped
2026-06-10. Three things landed:

1. **V4 `/results` redesign** — round-tabbed scoreboard with entry
   switcher (floating popover, submitted-only), points summary
   (Group / Knockout / Total), per-round group + KO fixtures tables
   with lineup-banked KO points, Summary tab + Winner tab.
2. **`/results/[fixture_id]` Match Detail** — prev/next nav (click,
   ←/→, swipe), hero + scoreline spread + rarity explainer + pool
   list (user's row(s) pinned to top).
3. **Admin completeness check** at `/admin/entries` — service
   `app.services.completeness` + `GET /api/admin/entries/
   completeness-check[.csv]`. Reports per-eligible-entry missing
   counts across match / bracket / bonus. Bracket expected = 63
   (32+16+8+4+2+1 — NO group_winners rows in real DB); bonus counts
   only current question ids (legacy 10→4 trim left stale rows).

**V4 Results gate (updated v2.164.0).** Two layers:
`V4_RESULTS_ENABLED = true` (the kill switch — flip to `false` and
redeploy for a 60-second rollback) AND `$user?.is_admin === true`
(the staged-rollout filter). Together: V4 ships behind an admin gate
on top of the deadline check; non-admins see the pre-tournament stub
until the `is_admin` clause is deleted from the gate in
`frontend/src/routes/results/+page.svelte`. Same shape as the V4
Leaderboard gate — both pages roll out via the same recipe (admin
verifies in prod, then one-line clause removal + redeploy opens it
to the pool).

**Backend additions are LIVE (additive, dormant until V4 enabled):**
- `MatchPredictionRead.points: PickPointsOut | None` populated for
  FINISHED fixtures via a single bulk-agreement query.
- `CommunityPrediction.rank: int | None` from the cached leaderboard.
- `GET /api/leaderboard/scoring-rules` exposed for client templating.
- `GET /api/admin/entries/completeness-check[.csv]` (admin-only).

**V4 types live OUTSIDE the barrel** at `frontend/src/lib/types/
results.ts` and `frontend/src/lib/types/admin.ts` because the user's
Mission Control WIP holds `types/index.ts` open. Always import V4
types directly (`from '$lib/types/results'`), never from `$types`.

**4 execution deviations from the spec (documented in commit
`6431e4d` + plan headers):**
1. Bracket expected = 63, not 87 (no "group" stage TeamPrediction rows
   in the real DB).
2. `BonusPrediction` has NO phase column; count CURRENT question ids
   only.
3. `str(MatchStatus.FINISHED)` is `"MatchStatus.FINISHED"` on Py3.11
   — unwrap `.value` before string compares (regression-tested).
4. CSV downloads need a Bearer token (no cookie auth) — use the blob
   pattern from `downloadAdminEntriesCsv`, never `window.location.href`.

**Group fixtures have `match_number = NULL` in prod** (verified
2026-06-10). The V4 round-bucketing util `deriveGroupMatchdays`
infers matchdays from per-team kickoff order; `match_number` path
remains primary when present so a future backfill works without code
change.

**V4 Leaderboard (v2.164.0, built 2026-06-11).** Full `/leaderboard`
rebuild from `mockups/Leaderboard-redesign/` — three views (Standings
table + pool filters, Race bump chart, Insights cards) plus an entry
detail drawer (open pool: any entry's full picks + scoring).
Components in `frontend/src/lib/components/leaderboard/v4/`; types in
`frontend/src/lib/types/leaderboard.ts` (outside the barrel); pure
derivations in `frontend/src/lib/utils/leaderboardV4.ts`
(vitest-covered).

- **Gate:** `V4_LEADERBOARD_ENABLED = true` AND `$user?.is_admin === true`
  in `frontend/src/routes/leaderboard/+page.svelte` — admin-only
  staged rollout (same pattern as V4 Results, see above). To open
  the page to the whole pool, delete the `is_admin` clause and
  redeploy. The `V4_LEADERBOARD_ENABLED` flag stays as a kill switch.
- **Backend additions (additive, no migrations):** `LeaderboardEntry`
  gained `employer`, `champion_pick`/`champion_alive`,
  `finalist_picks`/`finalists_alive`, `daily_movement` (vs yesterday's
  snapshot), `bonus_group_points`/`bonus_knockout_points` — all bulk
  queries per 30s cache rebuild, PHASE_1-filtered. New
  `GET /api/leaderboard/snapshots?days=N` (all entries' rank paths,
  blind-pool gated). Bonus prediction GETs carry
  `category`/`points`/`hit` (None until settled).
- **Pools:** Atlas/JMFA/Guests pills map onto `User.employer`
  (`atlas`/`jmfa`/`neither`|null → Guests). Filtering keeps GLOBAL
  ranks — server positions are never recomputed client-side.
- **Search box** in the your-entries strip filters by person OR entry
  name (accent-insensitive, `searchRows()` in `leaderboardV4.ts`).
  Composes with the pool filter; global ranks still survive.
- **Sparkline column** (Trend, desktop only) renders a 60×18 SVG of
  each entry's 14-day points trajectory — coloured by net delta —
  fed by the same `/leaderboard/snapshots` bulk endpoint as the Race
  view. No N+1 fetch.
- **Naming rule (★ consistency).** `rowDisplayName()` in
  `leaderboardV4.ts` is THE rule for surfacing entry identity:
  `Person — Entry name` when the owner holds multiple entries, just
  `Person` otherwise. Used by standings rows, drawer header, race
  chart labels + tip bar, every insights card. Computed from the
  UNFILTERED board so pool/search filtering can't flip a label.
- **Race chart x-axis anchors to fixture timeline:** start = first
  fixture's UTC kickoff date, end = today (advances each day). Snapshot
  points outside this window are filtered out per-entry, so seed
  snapshots from before kickoff can never pull the axis backwards.
- **Insights:** 8 of the spec's 14 cards ship (Atlas-vs-JMFA was
  dropped per user feedback); the 5 needing all-entries per-fixture
  data (herd, heartbreak, hauls, hot hand, pick twins) sit behind
  `INSIGHTS_EXTENDED = false` in `InsightsGrid.svelte` pending a
  backend insights endpoint. Tournament Superlatives now lists ALL
  teams tied at each criterion (capped at 5 + "+N more"); bonus Q3
  Dark Horse and Q4 Bottlers candidates surface in the same card
  once `groupStageComplete` flips true (every group fixture
  FINISHED), driven by `bonusMeta.fifa_top_teams` from
  `/predictions/bonus/meta`.
- **Elimination is conservative** (`get_eliminated_teams` backend,
  `eliminatedTeams` frontend mirror): KO-match losers + group
  non-qualifiers only once every R32 fixture holds real
  (non-placeholder) team names. Alive until provably out.
- **Dev-loop gotcha:** Vite file-watching is dead on the OneDrive
  bind mount — overlay copies are NOT picked up by HMR. Every
  frontend overlay test needs `docker compose restart frontend-dev`
  (~12s); stale module graphs otherwise produce phantom
  "does not provide an export" errors and SSR 500s.

**V4 Match Detail polish (v2.164.0).**

- **Upcoming-match panes now render** (`/results/{fixture_id}` for
  a not-yet-played fixture). The community endpoint
  (`GET /api/predictions/matches/{fixture_id}/community`) was gating
  on the per-fixture 5-min lock; now also accepts the global
  `is_phase1_locked` — open-pool post-deadline, every fixture's
  picks immediately surface. Pool split + scoreline bubble grid +
  "Who picked what" all appear pre-kickoff.
- **Scoreline-spread bubble grid:** responsive 4×4 with
  aspect-square cells, bubble fill `bg-amber-400` / `bg-emerald-400`
  / `bg-slate-400` for home/away/draw outcomes (NOT the surface
  `warning/success` tokens — those render too dark for chart fills,
  per the "text-warning is a surface trap" rule).
- **Per-round scoring explainer** moved from an always-on banner
  to a ℹ popover next to the table's Points column header
  (`PointsHelpButton.svelte`). Summary + Winner views still get the
  banner since they don't have a Points column.
- **Third-place playoff** (`Fixture.stage === 'third_place'`) is
  explicitly OMITTED from the Finals tab and every other surface —
  prediction game doesn't score it. ★ Invariant documented above
  and pinned in `resultsRounds.test.ts`.
- **Entry switcher** merged into the points-summary pill
  (`EntrySummaryBar.svelte`) — single right-aligned card with two
  sub-rows: identity ("Person — Entry · switch ▾") on top, score
  breakdown below. One click target for the whole thing. Identity
  sub-row lives INSIDE the pill chrome so the mobile navbar can't
  clip it (lesson learned this session: floating elements above
  sticky bars get clipped — always put them in a bordered card).

**Launch-week state (v2.170.0–v2.172.4, shipped 2026-06-11 deadline
night). Three temporary/operational surfaces are live:**

1. **Rarity bonus is PAUSED** — `scoring.mode: "fixed"` in
   `config/worldcup2026.yml` (was `logarithmic`) so eligible-pool churn
   during entry verification / fee collection can't re-price rarity on
   finished games. Base points are identical (5 outcome / 10 exact);
   the BreakdownCard hides its rarity column via the served
   `scoring-rules.mode`. **Flip-back is ONE release**: YAML mode back
   to `logarithmic` + remove the rules-page paused callout
   (`frontend/src/routes/rules/+page.svelte`, amber `role="status"`
   block) + retire the site banner (below). No backfill — the 30s
   leaderboard rebuild retro-applies rarity to all finished fixtures
   from the final denominators. Config is `@lru_cache`d: deploy restart
   required. Memory: `predictorv2_rarity_paused.md`.
2. **Site notice banner** (`SiteNoticeBanner.svelte`, mounted in the
   root layout next to `DeadlineCtaBanner`) — dismissible amber strip
   on every signed-in page except /admin explaining the rarity pause +
   live-scoring bedding-in, with a Help & Support link that opens the
   support panel. Kill switch `SITE_NOTICE_ENABLED`; re-message by
   changing `NOTICE_ID` (dismissals are keyed to it).
3. **All-entries CSV export** (transparency sheet) —
   `GET /api/predictions/export/all-entries.csv`
   (service `app/services/predictions_export.py`, spec in
   `docs/superpowers/specs/2026-06-11-all-entries-csv-export-design.md`)
   + "All entries CSV" button in the /leaderboard toolbar. Gate
   `is_admin OR post_deadline_live` — opens to the pool automatically
   at go-live, NO rollout clause to delete. Wide matrix (one column
   per eligible entry; knockout rows alphabetical per entry — stage
   sets, not slots), BOM-prefixed for Excel, formula-injection guarded.

**Verification gotcha:** all pages are client-rendered — served HTML
is a ~5KB shell, so `curl | grep` for page copy always comes back
empty even after a good deploy. Verify rendered copy with a browser;
curl only works for API endpoints.

**Scoring sync (resolved 2026-06-01).** `config/worldcup2026.yml` is the
single source of truth for both the scoring engine and rules-page copy.
The rules page hand-mirrors YAML values via the `BONUS_POINTS` map and the
`BRACKET_STAGES` constant — change one without the other and users will
see different numbers from what scoring actually pays out. The bonus
question structure was simultaneously trimmed from 10 questions to 4
(two group-stage, two knockout-stage with FIFA-aware dropdowns); the
internal `top_flop` category literal is preserved across code, DB, and
tests for backward compatibility, but the user-facing label is
"Knockout Stage — Top / Flop" everywhere.

### Smart Fill (FIFA + Betting Odds)

User-triggered "auto-populate my predictions" feature surfaced via the ⚡
SmartFill button in the entry wizard. Two methods, picked via radio in
`SmartFillModal.svelte`:

- **FIFA method** — predicts from each team's FIFA ranking points. Argmax:
  stronger team always wins; only the scoreline wobbles per (user, fixture)
  seeded variation. Engine in `frontend/src/lib/utils/smartFill.ts`.
- **Betting Odds method** — predicts from averaged head-to-head decimal
  odds across all bookmakers The Odds API returns. Argmax outcome too:
  market favourite always wins (as of v2.158.0 — previously this was
  stochastic and produced occasional underdog upsets). Engine in
  `frontend/src/lib/utils/simulateScore.ts`. **Don't regress to
  stochastic outcome sampling** — that was the v2.158.0 §8 bug. The
  scoreline picker is correctly RNG-driven; the *outcome* must stay
  argmax. Modal copy promises "picking winners" — that's the contract.

**Bracket fill** always uses FIFA, regardless of which method is picked.
Odds cover scorelines only.

**Alias preservation contract (★ mandatory).** Both Smart Fill paths share
the same canonical-name resolver at [teamMatch.ts:27-64](frontend/src/lib/utils/teamMatch.ts:27)
(`ALIASES` map + `canonicalize()` helper). Touch it carefully — losing any
existing alias entry breaks the Odds path silently (fixtures with the
"wrong" spelling stop matching API responses). Examples that must keep
working: `USA ↔ United States`, `Korea Republic ↔ South Korea`,
`Türkiye ↔ Turkey`, `IR Iran ↔ Iran`, `Côte d'Ivoire ↔ Ivory Coast`,
`Cabo Verde ↔ Cape Verde`, `DR Congo ↔ Congo DR`, `Czechia ↔ Czech Republic`,
`CuraÃ§ao ↔ Curacao` (latter is API mojibake — keep the entry).

**FIFA rankings data.** Lives in `frontend/src/lib/data/fifaRankings.json`
(211 teams, FIFA's canonical spellings as keys). The FIFA Smart Fill path
loads this at module init and builds a normalized lookup map keyed on
`canonicalize(team)` so fixture-side spellings resolve correctly. Refresh
via:
```bash
node scripts/refresh_fifa_rankings.mjs
```
Run roughly monthly per FIFA's publication cycle. The script validates the
upstream response (8 durability checks) and atomically writes the JSON; on
any failure the existing file is left untouched. **Future improvement**
(plan §7-B, deferred): admin-panel "Refresh now" button replaces the
script + commit + deploy cycle.

**Odds cache.** Lives server-side at `/app/data/odds_cache.json` on the
existing `./backend/data:/app/data` bind mount. Lazy read-through with a
4h TTL — first user to open Smart Fill after the cache goes stale triggers
a refresh; everyone else within the 4h window reuses. Service:
`backend/app/services/odds_cache.py`. Endpoint: `GET /api/odds/`
(unauthenticated; SvelteKit's `/odds` is now a thin proxy). **Durability
contract:** any upstream failure mode (HTTP error, timeout, parse error,
empty `Results`, validation failure) keeps the existing cache untouched.
Merge-on-refresh: fixtures absent from a new API response are preserved.

**Environment variable: `ODDS_API_KEY`** — **backend** env var as of
v2.158.0 (was on the frontend services pre-§9, when the SvelteKit `/odds`
endpoint hit The Odds API directly). Unset → backend returns
`{error: 'not_configured', matches: []}` and the modal disables the
Betting Odds radio (graceful degradation). The same docker-compose `.env`
variable now propagates to the `backend` service instead of `frontend` —
existing prod `.env` files don't need updating, only the service that
consumes the var changed.

### Transactional emails (v2.159+)

Three flows, all via Resend (`backend/app/services/email.py`) with a dev
fallback that prints to docker logs when `RESEND_API_KEY` is unset:

1. **Magic-link sign-in** (`send_magic_link_email`) — unchanged from v2.x.
2. **Submission confirmation with recap**
   (`send_submission_confirmation_email`) — fires after
   `POST /entries/{id}/submit` commits. Accepts an optional
   `recap: dict | None`. The recap is built by
   `backend/app/services/entry_recap.py:build_entry_recap()` (eager-loads
   predictions, buckets by group / round / bonus question) and rendered as
   monospace receipt-style HTML appended to the email body — no PDF
   attachment, no Jinja2 template, just f-string composition. Best-effort:
   recap-build failure logs and drops to `None` so the email still sends
   without the recap; email-send failure logs and the API still returns
   200 (the entry is already committed and audit-logged).
3. **Entry unlock notice** (`send_entry_unlocked_email`) — fires after
   `POST /entries/{id}/edit` flips SUBMITTED → DRAFT. Safety-net for users
   who unlock to tweak a pick, close the tab, and forget to resubmit (the
   entry would silently miss scoring otherwise). Body includes the
   `phase1_deadline` formatted via `aware_utc()`. One email per unlock
   event, no de-duplication, no rate-limit.

**Country-name shortening:** the email recap renderer uses
`backend/app/services/team_name.py`, a Python port of the frontend
`SHORT_NAMES` map at `frontend/src/lib/utils/teamName.ts:24-31`. Six
entries today (`Bosnia-Herzegovina → Bosnia`, `United States → USA`,
etc.). Keep the two in sync — any new entry in the frontend map needs
to be ported.

**Deploy gotcha** (`docker compose up -d --build`): a rename-conflict on
one service silently keeps that service on its old image while the others
swap. After every prod deploy, grep the output for
`Conflict. The container name` and run the targeted backend recreate if
present. Memory: `feedback_docker_compose_rename_conflict.md`.

### Broadcast email feature (v2.160.0, extended v2.176.0, v2.178.0, v2.180.0, v2.181.0)

**Admin "Broadcast Emails" card** at `/admin` fans out one email per
audience row via Resend, paced ~50ms per send. **Templates are
hardcoded per segment in `backend/app/services/email.py:
_broadcast_content_for_segment()`** — the admin UI is NOT a freeform
composer. Adding a new one-off announcement = add a new
`BroadcastSegment` enum value + a branch in the content function +
labels in `frontend/src/routes/admin/+page.svelte:SEGMENT_LABELS` +
the union in `frontend/src/lib/api/admin.ts:BroadcastSegment`.

**Audience cohorts** (all deduped by user — `query_audience` returns
one row per User via `EXISTS` subquery, so multi-entry holders get
exactly one email):

- `SUBMITTERS` (v2.160.0) — has ≥1 SUBMITTED entry phase. Pre-deadline
  "thanks for entering" nudge. CTA → `/entries`.
- `NO_ENTRY` (v2.160.0) — zero PredictionEntry rows. Last reminder to
  sign up. CTA → `/entries`.
- `DRAFT_HOLDERS` (v2.160.0) — has DRAFT but no SUBMITTED. CTA →
  `/entries`.
- `POOL_GHOST` (v2.176.0) — submitted-eligible AND no engagement since
  `TOURNAMENT_START`. CTA → `/results`.
- `LAPSING` (v2.176.0) — submitted-eligible AND last engagement
  3-7 days ago. CTA → `/results`.
- `GROUP_R1_RECAP` (v2.178.0) — one-off round-recap email. **Same
  audience query as SUBMITTERS** (shared `_has_submitted_phase_predicate`).
  Body is a tournament-progress recap (live standings + Google Sheet +
  €595/€183/€150 prize breakdown + Atlas €500 Soup Kitchen top-up).
  CTA → `/leaderboard?utm_source=email&utm_campaign=group_r1_recap`.
  Plain-text deliberately omits the raw spreadsheet URL; recipients are
  routed to the in-app "View All Entries" button instead.
- `GROUP_R2_RECAP` (v2.180.0) — Round 2 recap. Same audience predicate
  as R1. **CTA ships clean** (no UTM) — R1's UTM-tagged URL contributed
  to Gmail's promotional-bin classification, so R2 dropped it.
  Wording also avoids `winner+announced` / `prize+paid` / `prize+awarded`
  pairs. Trade-off: PostHog can no longer attribute per-round
  click-throughs — deliverability beats analytics. Tokens auto-fill at
  send time via `_compute_r2_highlights(session)` (top 5, R2 hero from
  snapshot diff, biggest climber from race_stories) — admins don't
  hand-fill placeholders.
- `GROUP_STAGE_FINAL` (v2.181.0, podium upgrade v2.183.x 2026-06-28) —
  Group Stage champion announcement. Same audience predicate as the
  recap segments. Body has tokens for winner name + 4-part points
  breakdown + narrative story line + audit-credibility closer, all
  composed server-side in `services/group_stage_winner.py` so the
  email and the `GroupStageWinnerCard` on the dashboard render
  identical data. **Token compute is gated on
  `Competition.group_stage_winner_released`** — admin flips that flag
  from `/admin` ("Group Stage Winner release" section); until then,
  test sends surface literal `{{WINNER_NAME}}` placeholders as a
  defensive signal that the admin pressed test-send before release.
  Same spam-filter rules as R2 (no UTM, no `winner+announced`-style
  word pairs). **Regression test in `test_admin_broadcasts.py`
  (`test_group_stage_final_template_tokens_interpolate`)** pins that
  every advertised token interpolates and no literal `{TOKEN}` /
  `{{TOKEN}}` fragment leaks through — catches the f-string-double-
  brace bug class (Python collapses `{{` to `{` in f-strings, breaking
  the `_interpolate` regex if a token's segment is inside an f-string).

### Group Stage Winner Card (★ invariants, v2.183.x)

The dashboard's `GroupStageWinnerCard.svelte` and the
`/api/leaderboard/group-stage-winner` endpoint (URL kept from v2.181.0;
payload upgraded) surface a **top-3 podium**, not a single winner.

- **★ Pinned to group-stage totals** — never the live leaderboard
  total. `get_group_stage_podium()` computes per-entry group-stage
  total as `phase1.match_outcome_points + phase1.exact_score_points
  + phase1.hybrid_bonus_points + bonus_group_points` (group-stage
  bonus only, NOT bonus_knockout_points). It sorts by that, takes
  top 3, and ranks them within that ordering. Once knockouts pay
  out, the live leaderboard reorders but the GSW card stays
  pinned at the group-stage podium (James/Kevin/John, not the
  shifting live top 3). This is THE rule that keeps "Group Stage
  Champion" a frozen historical statement.
- **Top-3 visual** — rows for #1/#2/#3, winner row amplified (gold
  halo, gold rail, brighter rank + total, animated trophy on the
  name). Each row clickable → opens that entry's drawer at
  `/leaderboard?entry={id}` (same convention as standings rows).
- **Audit footnote inline + Verified pill** — pill is the
  at-a-glance signal; the inline footnote below the story panel
  names the four sources (database modification log, deadline-night
  predictions snapshot, submission emails on Resend, fresh scoring
  engine re-run) and survives mobile screenshots (tooltip text
  doesn't).
- **Theme-aware colors** — every gold value routes through
  `hsl(var(--p))` rather than hardcoded hex, so the card reads
  correctly in BOTH premium-night (#D4AF37 champagne gold on dark
  navy) and hybrid (#B8941F deeper gold on cream). Light-mode QA
  is an explicit checklist item for any dashboard surface — see
  the feedback memory `feedback_check_light_mode_before_shipping`.

**Engagement-signal architecture for POOL_GHOST / LAPSING is HYBRID:**
`User.last_seen_at` column (primary, throttled per-request in
`get_current_user`) + PostHog `$pageview` fallback (best-effort, silent
degradation). See `backend/app/services/broadcast.py` module docstring
for the full rule.

**UTM tagging convention (introduced v2.178.0):** broadcast CTAs that
route into the app carry `?utm_source=email&utm_campaign=<segment>`.
PostHog `capture_pageview: true` records `$current_url` so filter by
`$current_url contains utm_campaign=group_r1_recap` to count
click-throughs. Sheet button clicks specifically fire the
`view_all_entries_clicked` event from
`frontend/src/routes/leaderboard/+page.svelte`. The email-direct →
docs.google.com path is **deliberately unattributable** (sheet on a
third-party domain).

### Feature awareness: What's New panel, nudges, rating & feedback (v2.196.0–v2.197.1)

Three shipped in quick succession (2026-07-05) to give pool members
in-app ways to discover shipped features and leave feedback —
previously only the admin Release Notes page listed changes.

**Two data sources, deliberately kept separate (★ never conflate).**
`frontend/src/lib/data/changelog.json` (raw per-semver dev log, 100s
of noisy rows — `internal`/`fix`/`merge` included) still powers only
the admin Release Notes page. `frontend/src/lib/data/featureHighlights.json`
is a SEPARATE, hand-curated, newest-first consolidation of many
releases into short user-facing themes (`{id, title, blurb, since,
date, href?, cta?}`) — it powers the What's New panel. **Never
auto-derive one from the other** — that's exactly the trap that would
leak dev jargon or phase language into user-facing copy. When a
feature ships, decide by hand whether it's worth a new
`featureHighlights.json` entry (trim the tail so the list stays
~6-10 items); every release still gets a `changelog.json` row
regardless. Shared helpers in `frontend/src/lib/utils/releases.ts`
(`currentVersion()`, `RELEASE_TYPE_BADGE`/`RELEASE_TYPE_LABEL` maps,
highlight helpers) serve both surfaces so admin and user framing never
drift on shared concepts like version numbers.

**What's New panel** (`WhatsNew.svelte`) — opened via a nav sparkle
button showing a passive "New" badge until the latest highlight is
seen (`latestHighlightId()`). Each card can carry a per-feature
👍/👎 "Was this useful?" control (`featureFeedback.ts` store,
`feature_rated` event) — low-friction, visible only inside the panel
a user chose to open, recorded once per device
(`localStorage['predictor:whatsnew:feedback']`), never re-asked.

**Feature nudges** — one-time contextual toasts (`toast` store +
`Toaster.svelte`, top-anchored to clear the mobile bottom nav) driven
by `frontend/src/lib/utils/featureNudges.ts`. Capped once per feature
and once per session.

**Rating prompt** (`RatingPrompt.svelte`) — gated by
`frontend/src/lib/stores/ratingPrompt.ts`: fires after
`VIEW_THRESHOLD` (4) meaningful page views in a session, asked at
most ONCE per device (`localStorage['predictor:rating:asked']`).
Tapping a star persists the "asked" flag immediately
(`markRatingAsked()`) — a user who rates and closes the panel without
sending written feedback is never re-prompted or double-counted.

**Feedback is EMAILED, not stored (v2.197.0 — replaced the Tally
hand-off).** After the star tap, an inline textarea appears; Send
POSTs to `POST /api/feedback/` (`backend/app/api/feedback.py`,
auth-required — keeps it from being an open email relay). Payload:
`rating` (1-5) + `message` (1-2000 chars, HTML-escaped, 422 if
empty/oversized). `email.send_feedback_email()` mirrors the
magic-link Resend path (dev prints to stdout; prod POSTs via Resend,
reply-to set to the submitter's email so the pool owner can reply
directly) — 502 on send failure so the client can offer a retry.
**No DB table, no migration** — there is no feedback audit trail
beyond the inbox. The footer's persistent "Feedback" link force-opens
the same rating card via `openRatingPrompt()` (gated to signed-in
users); the old `FeedbackPanel.svelte` / `feedbackPanel` store (Tally
iframe hand-off) was removed in the same release — the separate
Support-panel Tally "Help" flow is untouched and still exists.

**New analytics events:** `feature_nudge_shown`, `feature_nudge_clicked`,
`app_rating_submitted` (carries `rating` 1-5), `feedback_submitted`,
`feature_rated` (carries feature id + up/down), `whats_new_feature_clicked`.

### Live projected leaderboard (v2.198.0, deployed dormant)

Knockout-stage standings can re-rank **live**, mid-match, instead of
waiting for full time. Read-time-only overlay in
`backend/app/services/live_projection.py`, applied inside
`get_leaderboard()` — the banked leaderboard cache (30s TTL,
stale-while-revalidate) is **never mutated**; the live projection is
computed fresh per-request and layered on top. This snapshot/
trajectory purity is the same invariant that protects
`LeaderboardSnapshot`/daily-movement widgets elsewhere — read-time
and score-time must never blend into the same stored row.

- **Scope: knockout only.** Group-stage matches carry the rarity
  bonus, which can't be projected mid-match (denominators aren't
  final) — live projection only activates once a knockout fixture
  (`round_of_32` or later) is `LIVE`.
- **Penalty-blind by design.** A live KO match's projected winner
  comes from `Score.final_home_score`/`final_away_score` (ET-
  inclusive, penalty-BLIND) — a live draw shows **zero movement**
  even deep into a shootout, because `Score.outcome` (the penalty-
  aware field) only resolves once the match is FINISHED. Standings
  snap to the real result the instant full time + penalties are
  recorded; there is no "projected penalty winner."
- **Double-count guard (★ the trap here).** `get_actual_advancement()`
  credits "reached stage X" the moment ANY fixture of that stage
  shows a team's real (non-placeholder) name — not gated on FINISHED
  — because `score_sync.py` writes real team names into next-round
  fixtures as soon as Football-Data reports them, independent of
  whether the feeding match has finished. A naive live-projection
  overlay would double-award: once from the banked "reached round"
  credit (already seeded) and again from projecting the live match's
  winner into the SAME round. `_already_banked()` in
  `live_projection.py` checks `_STAGE_ORDER` before crediting a live
  delta — skip if the entry's actual advancement already reached that
  stage or later. Found by a whole-feature review, not any single
  task's isolated review — this class of bug only shows up when you
  reason about the read path and the write path together.
- **Fail-open.** `get_leaderboard()` wraps `apply_live_projection()`
  in try/except — any error falls back to the banked board silently.
  A live-projection bug should degrade to "provisional numbers,"
  never to a 500.
- **Seamless handoff at full time.** `score_sync.py` hard-invalidates
  the leaderboard cache the instant a KO fixture goes FINISHED
  (`ScoreSyncResult.points_relevant_ko`), vs. the existing soft-expire
  for group-stage finishes — so the projected numbers don't visibly
  "dip" back down before real points land; the cache rebuilds
  immediately with final numbers.
- **Two independent gates, both required:**
  `Competition.live_projection_enabled` (admin kill switch on
  `/admin`, defaults `false` via the migration's server default —
  **deployed OFF**, no behavior change for the pool until an admin
  explicitly flips it) AND an actual live KO match existing. Surfaced
  on `PhaseStatus.live_projection_enabled` for the frontend to key
  off.
- **Surfaces:** `/leaderboard` standings (green `LiveProjectionPill` +
  green "based on live: N matches" cue, red pulsing dot — matches the
  app's existing green/white "live" convention) and the home
  dashboard's mini-leaderboard both re-sort live
  (`displayRank`/`displayTotal` in `leaderboardV4.ts` prefer
  `projected_position`/`projected_total` over the banked fields when
  `live_projection_active` is true). `EntryDrawer` was a post-hoc fix
  (Task 15) — it was reading banked numbers straight through even
  while live projection was active elsewhere on the same page.

### Pool Distribution — full-pool histogram (v2.199.0)

`PoolDistribution.svelte` (dashboard + Leaderboard Race tab) redesigned
from a narrow ±window around one score to a full-pool points histogram
spanning every eligible entry, with **all** of a user's own entries
individually marked (not just their best) — mirrors the existing
"one result per submitted entry" convention from
`compute_personal_trail()`. Backend: `compute_pool_distribution()` in
`backend/app/services/dashboard_stats.py`, reading from
`LeaderboardSnapshot` (today's frozen snapshot) for consistency with
the other snapshot-driven dashboard widgets — not the live/cached
leaderboard.

- **`_nice_bucket_width()`** — D3-style tick-step rounding (1/2/5 ×
  10ⁿ) targeting ~12 buckets, so histogram buckets land on clean
  numbers instead of arbitrary point values.
- **Per-bar labels, not generic ticks.** Each bar's own
  `bucket_start` is rendered directly beneath it, rather than 5
  evenly-spaced axis ticks computed independently from
  `min_points`/`max_points`. The generic-tick approach was internally
  inconsistent — its spacing had no relationship to the backend's
  actual bucket boundaries, so labels could imply a continuous scale
  across gaps where no bucket (and no bar) exists. Deriving every
  label from the bar geometry itself means the axis can't lie about
  what the chart is showing.
- **SVG viewBox font-sizing gotcha (recurring).** This chart's
  `font-size` values are picked backwards from a target on-screen
  size — a 1080-wide viewBox rendered into a ~450px card shrinks
  "16px" text to ~7px on screen. Every label size in this component
  was tuned by rendering and reading it, not by picking a number that
  looks right in the SVG source.
- **Entry-label collision staggering** — labels within `COLLISION_PX`
  (90 viewBox units) of each other alternate onto a second vertical
  tier, so multi-entry players' clustered picks stay legible instead
  of overlapping.

### Datetime rule (system-wide)

**Every datetime is timezone-aware UTC.** Naive datetimes are a bug.

- **DB:** all datetime columns are `TIMESTAMPTZ`. Use the column factory in
  `backend/app/models/_datetime.py`.
- **Python:** use `utc_now()` from `app.models._datetime` — never
  `datetime.utcnow()` (deprecated and naive). Construct test datetimes with
  `datetime(..., tzinfo=timezone.utc)`.
- **API:** Pydantic serializes aware datetimes as ISO 8601 with explicit
  offset.
- **Frontend:** `new Date(string)` parses correctly thanks to the offset,
  then `Intl` renders local time.
- **Driver gotcha:** aiosqlite drops tzinfo on read; PostgreSQL preserves it.
  - **At compare sites:** Use `aware_utc()` from `_datetime.py` defensively
    at any compare site that touches DB-loaded values.
  - **At service-function return sites (CRITICAL):** When a service
    function returns datetimes pulled from the DB (e.g. `MAX(created_at)`
    aggregations, `select(Table.col)` projections), wrap each returned
    value through `aware_utc()` BEFORE returning. The service layer is the
    right place to coerce — callers (tests, API serializers) shouldn't
    have to know which driver answered. Tests against in-memory SQLite
    that assert `dt == datetime(..., tzinfo=timezone.utc)` will silently
    fail with `naive == aware → False` otherwise. Pattern:
    ```python
    return {uid: aware_utc(ts) for uid, ts in rows}
    ```
    This bug has recurred multiple times. Catch it at the return site, once.

Established in commit `c6089cc`; the conversion migration was later squashed
into `f06b6a2077d3`. Violating this silently shifts kickoffs/deadlines by the
user's UTC offset.

## Migrations

**Alembic is the single source of truth for schema.** Backend startup runs
`alembic upgrade head` automatically (`backend/app/database.py:init_db`). No
`SQLModel.metadata.create_all` fallback.

```bash
# Add/modify model under backend/app/models/, import it in models/__init__.py, then:
docker-compose exec backend alembic revision --autogenerate -m "describe change"
# Review the file under backend/alembic/versions/ (autogenerate misses
# data migrations, server_defaults, enum changes), then restart:
docker-compose restart backend
```

Manual inspection when needed:

```bash
docker-compose exec backend alembic current | history | downgrade -1 | stamp <rev>
```

A failing migration takes the app down at startup — that's the safe default.

## Versioning

**Bump the version before any production push.** Three files must stay
in sync — all at the same semver number:

- `frontend/package.json` (also `frontend/package-lock.json` — both
  top-level `"version"` AND the in-tree `packages[""]` self-reference)
- `backend/pyproject.toml`

**Baseline reset (2026-05-31):** versions were renumbered from `0.x.x`
to `2.x.x` starting at the first May 2026 commit (`2.0.0`). The full
chronological mapping commit → version lives in
`frontend/src/lib/data/changelog.json` and is exposed in the admin
console at `/admin` ("Release Notes" panel — filterable, latest first).
For the current `HEAD` version, read `frontend/package.json` — the
docs deliberately don't pin it because it changes every push.

Bump rule:
- **Minor** (`2.x.0` → `2.(x+1).0`) — anything that adds capability:
  `feat`, `refactor`, `perf`, or merges of those.
- **Patch** (`2.x.y` → `2.x.(y+1)`) — anything that doesn't add capability:
  `fix`, `chore`, `style`, `ui`, `docs`, `test`, `build`, `ci`, `revert`.

**Process per release:**
1. Land the feature/fix work.
2. Bump the three version files.
3. Append a new entry to the **end** of the `entries` array in
   `frontend/src/lib/data/changelog.json` (oldest-first; the admin
   Release Notes panel reverses for display, reading the last entry as
   the newest release). Keep the same shape
   `{ version, date, type, summary, commit }`. The `type` enum:
   `feature | improvement | fix | internal | merge`. The `summary` is
   one user-friendly sentence (no dev jargon; the admin Release Notes
   panel renders it verbatim to pool members on staff). `"commit":
   "pending"` is tolerated as a placeholder.
4. Commit as `chore(version): bump to X.Y.Z` so the deploy boundary
   stays visible in the log.
5. `git push origin main` to publish.

The bootstrap generator at `scripts/generate_changelog.py` walks
`git log` to re-build the JSON from history. It's idempotent and safe
to re-run, but the *source of truth* is the JSON file itself —
hand-edits to summary wording persist if you avoid re-running the
generator. Use the generator to seed a stale file; use direct JSON
edits for ongoing release entries.

## Development

```bash
docker-compose up -d                # backend :8000, frontend dev :5173 (--profile dev)
docker-compose logs -f backend
```

### Worktree-overlay testing pattern

When working in a Claude worktree under `.claude/worktrees/...`, the
running `docker-compose` stack is bound to the **main worktree path**, not
the Claude worktree. That means `docker-compose exec backend pytest` and
`docker-compose exec frontend-dev npm run check` from inside the Claude
worktree run against main-worktree code, not your edits. Verified across
many sessions.

**Pattern that works:**

1. Edit files in the Claude worktree.
2. `cp` the changed files into the main worktree's matching paths.
3. Run `docker-compose exec -T <service> <cmd>` from the main worktree path.
4. Restore the main worktree to clean state: `git checkout -- <path>` for
   modified files, `rm` for new files.
5. Commit in the Claude worktree (now the main worktree is back to clean).

**Why:** spinning up a separate compose stack from the worktree's own
`docker-compose.yml` is slow (fresh `npm install`, port conflicts on
5173 / 8000 / 5432). Overlay-then-restore is seconds.

**Important:** confirm the main worktree's `git status` before step 1 and
flag any pre-existing dirty state — overlay-then-restore can clobber
uncommitted user work otherwise. Always restore step 4 before committing
in the Claude worktree, or the main worktree stays dirty across sessions
and confuses the next person who opens it.

### Testing

```bash
# Backend
docker-compose exec backend pytest tests/ -v

# Frontend type check (keep errors at 0; existing warnings are tolerated)
docker-compose exec frontend-dev npm run check

# Frontend unit tests
docker-compose exec frontend-dev npx vitest run

# Seed Phase 2 test data (rarely needed — Phase 2 is dormant per the
# Phases invariant above; only run if you're actively working on Phase 2
# code paths during development)
docker-compose exec backend python scripts/seed_phase2_test.py
```

**Pre-commit gates (run before EVERY commit that touches service
functions, models, or Svelte templates):**

```bash
# Fast — under 30s combined on a warm cache.
docker-compose exec -T backend pytest tests/<your_new_files>.py
docker-compose exec -T frontend-dev npm run check    # MUST be 0 errors
```

These two gates catch the recurring failure modes this codebase has hit:

1. **SQLite tzinfo strip on aiosqlite reads** — tests asserting
   `dt == datetime(..., tzinfo=timezone.utc)` against naive returns
   fail because aiosqlite strips tzinfo on read. See the Datetime
   rule above — coerce at the service return site, not the test.
2. **Svelte compile errors and reactivity bugs** — `{@const}`
   misplacement, `as Type` template casts, `class:foo={fn()}`
   reactivity, `$page.params.X` typed as `string | undefined`. See
   the Frontend gotchas section. svelte-check reveals these
   immediately; the dev server's HMR overlay shows them too, but
   `npm run check` is the deterministic gate.
3. **`httpx.Response` mock needs explicit `request=`** for
   `raise_for_status()` to work on success responses — without it, the
   `raise_for_status` call on a 200 response *itself* raises
   `RuntimeError: Cannot call raise_for_status as the request instance
   has not been set`. Surfaced in `test_odds_cache.py` and any future
   async-httpx-mocking test. Pattern:
   ```python
   httpx.Response(
       200,
       json=matches,
       headers={...},
       request=httpx.Request("GET", "https://example.test/..."),  # ← required
   )
   ```
   Standard pytest+httpx tutorials don't always show this; document it
   here so future authors don't lose time on the cryptic error.
4. **Adding a NOT NULL model field or a new Pydantic schema field
   silently breaks every test that builds that row by hand** — 17
   tests across 6 files went stale this way as of v2.197.1 (schema
   drift accumulated invisibly because the full suite wasn't run after
   each of several feature merges). Two shapes recur:
   - `MagicMock(spec=Model)` fixtures don't auto-populate a field added
     to the model after the mock was written — pydantic then rejects
     the mock's default `MagicMock` sentinel as an invalid type (e.g.
     `FixtureRead.external_id: str` added in v2.184.x broke 5 mocks in
     `test_fixture_score.py` that predated it). Fix: explicitly set
     `mock.<new_field> = None` (or a valid value) in every fixture.
   - Real SQLModel row-builder helpers (e.g.
     `_make_eligible_submitted_entry` in `test_broadcast_cohorts_v2_176.py`)
     raise `sqlite3.IntegrityError: NOT NULL constraint failed` the
     moment a required column is added to the table after the helper
     was written (`PredictionEntry.competition_id` / `.reference` /
     `.display_name` all bit this). Fix: update the helper to populate
     every required field — don't just patch the one column the error
     message names; re-run and let the NEXT missing-field error surface
     the rest one at a time, or read the model definition once and fix
     all of them together.
   Run the FULL backend suite (`pytest tests/`, not just your new
   file) after adding any required field to a model or schema — that's
   the only gate that catches this class of drift before it compounds
   across releases.

Skipping the gates is how this codebase has historically shipped
patches to fix patches. Run them.

## Analytics

**One wrapper, one dashboard.** As of v2.155.0, all event tracking
flows through `frontend/src/lib/analytics/index.ts` and lands in
PostHog Cloud EU (`eu.i.posthog.com`). Umami was retired in the same
release. Cloudflare Web Analytics remains for Core Web Vitals only —
separate beacon in `app.html`, independent of the wrapper.

### Firing an event

```ts
import { track } from '$lib/analytics';

track('event_name', { prop: 'value' });
// Critical events (e.g. submissions) — also POST through the backend
// so ad-blocked users still get captured:
track('entry_submitted', { entry_id }, { alsoServer: true });
```

Adding a new event: append the name to the `EventName` union in
`lib/analytics/index.ts` AND to `ALLOWED_EVENTS` in
`backend/app/api/telemetry.py` (only required if any caller passes
`alsoServer: true` or if a backend service fires it via
`analytics.capture()`).

**Notable custom events** (browser-fired unless noted):
- `match_detail_opened` / `leaderboard_view_changed` (v2.176.2) — Site
  Pulse feature-usage signals.
- `view_all_entries_clicked` (v2.178.0) — click on the **View All
  Entries** button on `/leaderboard` (opens the public Google Sheet).
  Pairs with UTM-tagged broadcast links to give email→app and
  email→sheet attribution. Frontend-only; no backend allow-list entry.

### Privacy posture

- **No session recording** — `disable_session_recording: true` in init
- **DNT honoured** — `respect_dnt: true` + manual short-circuit in wrapper
- **Sensitive inputs masked** — `class="ph-no-capture"` on the `paid_to`
  field (PII-ish). Score inputs aren't masked — predictions aren't PII
- **distinct_id is the user UUID** — no name/email passed via `identify()`

### Environment variables

- `POSTHOG_API_KEY` (backend, server-side capture)
- `POSTHOG_HOST` (backend, defaults to EU instance)
- `PUBLIC_POSTHOG_KEY` (frontend, browser SDK — same `phc_*` value as
  backend; safe to expose per PostHog docs since it's write-only)
- `PUBLIC_POSTHOG_HOST` (frontend, defaults to EU instance)
- `PUBLIC_CF_WA_TOKEN` (frontend, Cloudflare Web Analytics beacon)

Project API keys (`phc_*`) are write-only ingestion keys; safe in
client bundles. Rotate via PostHog → Project Settings → API Keys.

### Backend-originated events

Some events make more sense fired from the backend (e.g.
`entry_submitted` after the DB transition commits). Fire those via
`app.services.analytics.capture(distinct_id=str(user.id), event=...)`
in the relevant service function — NOT through the `/api/telemetry/event`
endpoint (that's for frontend-originated events).

## UI

Two DaisyUI themes registered in `frontend/tailwind.config.js`: **`premium-night`** (dark, default — champagne gold on midnight navy) and **`hybrid`** (light — deeper gold on a dim slate canvas with white cards lifting above it). Themes change colour, not voice — same fonts, same hierarchy. The choice is persisted in `localStorage['predictor:theme']` and applied FOUC-safely by a script in `frontend/src/app.html`; the store lives at `frontend/src/lib/stores/theme.ts`. Legacy `'light'` / `'premium-day'` values migrate to `'hybrid'` on load. Layout + mobile bottom nav are in `frontend/src/routes/+layout.svelte`.

Components use **semantic DaisyUI classes** (`bg-primary`, `bg-base-100`, `text-base-content`, `text-success` …) — never raw hex. Dim/faint text is `text-base-content/55` / `/30`; soft accent fills are `bg-success/20` etc.

**Theme tokens** (in `frontend/tailwind.config.js`):

| Token | `premium-night` (dark) | `hybrid` (light) | Use |
|---|---|---|---|
| `primary` | `#D4AF37` champagne gold | `#B8941F` deeper gold | CTAs, brand, accents |
| `success` | `#059669` mint | `#059669` mint | Exact score, "good news" |
| `warning` | `#D97706` amber | `#B45309` amber | Outcome / lock |
| `error` | `#B91C1C` red | `#B91C1C` red | Miss |
| `base-100` | `#0B1329` midnight navy | `#E2E7F0` dim slate (NOT pure white — cards lift via base-200) | Canvas |
| `base-200` | `#1C2541` premium navy | `#FFFFFF` white | Surfaces, cards |
| `base-300` | `#2A3552` slate | `#D3DBE7` slate divider | Dividers, borders |
| `base-content` | `#E2E8F0` off-white | `#0B1329` navy | Body ink |

**`warning` is a surface token, paired with foreground `text-warning-text`.** Bare `text-warning` renders nearly invisible on dark chrome — in this design system `warning` is used for surface fills (`bg-warning/20` chips, `border-warning/40` outlines). The amber-text companion `text-warning-text` is defined via RGB channels in `app.css:7-10` for theme-aware switching. Asymmetric with `success` and `error`, which work as both foreground and surface because they aren't used as surface fills elsewhere. Memory: `feedback_text_warning_token_trap.md`.

Radii: `rounded-box` (14px / `0.875rem`), `rounded-btn` (10px / `0.625rem`), `rounded-badge` (8px / `0.5rem`).

**Typography** — one family pair, both themes:
- **Manrope** 700/800 (display, `font-display`) — wordmark, headlines, scores, big stats
- **Inter** 400/500/600/700 (body, `font-sans`) — UI text, labels, captions
- **JetBrains Mono** 500 (mono, `font-mono`) — timers, codes, monospace data
- **Bebas Neue** (opt-in via `font-hero`) — landing-page hero headlines only. Reach for it when you want a loud, broadcast-poster moment; Manrope still carries the rest of the system.

**Global classes** (`frontend/src/app.css`): `stadium-card`, `match-card` (+ `match-card-v2` for the redesigned variant), `stat-card`, `leaderboard-row`, `auth-bg`, `.noise`, `.score-input`. Custom utilities `pitch-pattern`, `stadium-glow`, plus shadow tokens `shadow-glow-gold`, `shadow-card` in `tailwind.config.js`. Prefer DaisyUI `shadow*` + `glow-gold` over hand-rolled box-shadows.

**Conventions:**
- Mobile-first: verify on 375px.
- Save actions: show success only after backend confirms.
- Mobile screens: one logical group at a time; avoid grid-of-cards.
- Phase tabs + section tabs (Groups / Knockout / Bonus) are stacked in the
  wizard hero.
- Bracket gating: in Phase 1 the Knockout sub-section is locked until every
  group prediction is filled (predicted standings seed R32).
- Score inputs cap at 15 goals per side, enforced on the input event.

**No `any` types** in TypeScript — define interfaces in `frontend/src/lib/types`.

**Backend-pending widgets** (rank sparklines, social signals, hot pick,
bracket exposure, underdog hits, steepest climb) fall back to deterministic
stubs via `frontend/src/lib/utils/widgetFallbacks.ts` when their endpoint is
empty or unavailable.

### Landing page composition (v2.159+)

`frontend/src/routes/+page.svelte` mounts the landing in two paired rows:

- **Row 1 — `LandingHero`**: Atlas TRIONDA prize hero on the LEFT (via the
  `PrizeHero` content fragment), Sign-in / WelcomeBack auth card on the RIGHT.
  Grid is `1.2fr / 1fr` at `lg+`, stacked on mobile. Image asset:
  `frontend/static/atlas-trionda-prize.{webp,jpg}`.
- **Row 2 — `TypographicHero`**: "MAKE EVERY WORLD CUP / MATCH MATTER." h1 +
  subhead + trust signals on the LEFT, `<CountdownBand variant="card" />` on
  the RIGHT.

`PrizeHero` is intentionally a content fragment (no outer section wrapper) —
geometry is `LandingHero`'s job, content is `PrizeHero`'s. Same separation
when adding future hero variants.

### Countdown urgency tiers (shared logic, v2.159+)

The navbar deadline pill (`CountdownTimer.svelte`) and the body countdown
(`CountdownBand.svelte`) both derive their state from
`frontend/src/lib/utils/countdownPhase.ts`. Single source of truth so both
timers escalate together. Five tiers:

- `calm` (> 7d) — green (`text-success`)
- `heads_up` (1–7d) — amber (`text-warning-text`, NOT `text-warning`)
- `urgent` (< 24h) — red (`text-error`)
- `critical` (< 1h) — red + `animate-pulse-soft`
- `locked` (≤ 0) — navbar hides; body shows "Locked" copy

`CountdownBand` has a `variant: 'band' | 'card'` prop. `'band'` = full-width
chrome (default, for standalone use). `'card'` = drops the wrapper +
shrinks the timer clamp for use in a grid column (consumed by
`TypographicHero`).

### Wizard groups accordion — inverted-state model

`frontend/src/routes/entries/[entryId]/+page.svelte` tracks
**`userCollapses: Set<string>`** (the rare action) rather than `openGroups`
(the default state). `openGroups` is derived as
`allGroupKeys − userCollapses`. Empty initial set ⇒ every group is open by
default; no async init, no `hasInit` flag, no race against `$groupFixtures`
hydration.

**Don't reintroduce a "fire-once init" pattern here.** The prior approach
gated on `allGroupKeys.length > 0`, but `allGroupKeys = [...filtered,
'thirdplace']` always has length ≥1 due to the literal append — so the init
fired pre-hydration with `Set(['thirdplace'])` and locked the flag. Real
groups stayed collapsed on cold loads. If you ever need a similar
"default broad, exception narrow" UX pattern (filter all on, multi-select
all selected, etc.), use the inverted-state model. Memory:
`feedback_inverted_state_for_async_default.md`.

The `activeGroupPill` default is `'all'` to mirror the all-expanded
accordion state; the right-rail `StandingsPanel` reads this to render the
stacked-all-groups view on first paint.

### Frontend gotchas

- **Svelte `<script lang="ts">` does NOT extend TypeScript into template
  expressions.** Only the script block is parsed as TS; everything inside
  `{...}` in the markup is parsed as plain JavaScript. Inline handlers like
  `on:click={(e) => (e.currentTarget as HTMLElement).foo()}` will throw a
  Vite compile error on the `as`. **The same rule catches typed-array
  literals in `{#each}`** — `{#each (['a','b'] as MyEnum[]) as c}` also
  fails. Extract to a named function (for handlers) or a typed const in
  the script block (for arrays). Pattern:
  ```svelte
  <script lang="ts">
    const COHORT_OPTIONS: UserCohort[] = ['active', 'all', /* ... */];
  </script>
  {#each COHORT_OPTIONS as c}
    <!-- ... -->
  {/each}
  ```
  When this breaks, Vite keeps the last-good build live and the dev server
  *silently* serves stale output — the error is only visible in the dev
  container's stdout (`docker logs predictorv2-frontend-dev-1`), not in the
  browser or via asset probes. Always check dev-server logs first when a
  change "doesn't show up."
- **`{@const}` placement rule.** `{@const x = ...}` MUST be the immediate
  child of a block tag (`{#if}`, `{#each}`, `{:else}`, `{:then}`,
  `{:catch}`, `<svelte:fragment>`, or `<Component>`). Placing it directly
  inside a plain `<div>` or other element fails at compile time with
  `must be the immediate child of {#if}…`. If you want a value computed
  once outside an `{#each}` loop (the common case — hoisting an invariant
  out of an iteration), **declare it as a `$:` reactive statement in the
  script section instead**. That sidesteps the placement constraint AND
  triggers correctly when dependencies change.
- **`class:foo={someFn()}` reactivity gotcha.** Calling a function inside
  a `class:` directive that reads a Svelte store does NOT reliably
  re-trigger when the store updates. Svelte's compile-time dependency
  analysis tracks store accesses at the top level of the script, not
  inside function bodies. **Surface the result via a `$:` reactive
  declaration in the script first**, then reference the plain variable in
  the `class:` directive. Common symptom: active-tab highlight in a
  sub-nav stays "stuck" on whatever was active at first render.
- **`$page.params.X` is typed `string | undefined`.** SvelteKit can't
  prove statically that a route param is present (even on routes like
  `/users/[id]` where it always is). When passing to a function expecting
  `string`, coerce: `$: userId = ($page.params.id ?? '') as string;`.
  Avoid the non-null assertion `!` unless the route guarantees it AND
  the assertion is in a unit-testable boundary.
- **`app.html` changes do not hot-reload.** Vite treats it as a boot-time
  document shell. Edits require `docker-compose restart frontend-dev`.
