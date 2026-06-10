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
read-only endpoints from the backend's perspective.

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
repo. **When the release touches `nginx/nginx.conf`, append
`&& docker compose --profile prod up -d --force-recreate nginx`** —
`up -d --build` does not restart `image:`-only services, so the
bind-mounted edit never reaches the running nginx process. The
force-recreate is a no-op when nginx.conf hasn't changed, so it is
safe to make permanent in the deploy line if you prefer.

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

**Advancement timing is lineup-based (v2.161.0).** Knockout "reached
stage X" credit fires when a team is seeded into a stage-X fixture
(`get_actual_advancement` scans ALL knockout fixtures, not just
FINISHED). Only the `winner` credit requires the final to be FINISHED +
scored. Group-stage match points still pay on match completion.

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

**Latent layout bug (filed, low priority).** The root `+layout.svelte`
throws a recurring `TypeError: Cannot read properties of null (reading
'pathname')` on every page load (since v2.156.0, commit `9301bbd`).
Doesn't break anything user-visible but is noisy in the console. Likely
cause: `nav.to?.url.pathname` at lines 68-69 — optional-chains the
container but not the nested `.url`. A deep optional-chain
(`nav.to?.url?.pathname ?? ''`) probably fixes it. If you're refactoring
the layout for any reason, fix this in the same change.

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
