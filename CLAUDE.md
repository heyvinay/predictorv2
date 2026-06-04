# CLAUDE.md

Guidance for Claude Code when working in this repo.

## Project

**The Predictor v2** — self-hosted web app for running international football
prediction competitions (World Cup, Euros) among ~30 friends. Current focus:
**World Cup 2026**.

## Tech stack

**Backend:** FastAPI (Python 3.11+), SQLModel, PostgreSQL 16, Alembic.
Tournament config in YAML (`config/worldcup2026.yml`). External scores via
Football-Data.org (`backend/app/services/external/football_data.py`).

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

### Phases (backend: two-phase model · production: single-phase)

The backend still has two-phase code, but as of 2026-05-30 the live
competition runs **single-phase only**:

- **Phase 1** (pre-tournament): group-stage scores + knockout-bracket
  advancement + bonus questions. Every entry must be in before
  `competition.phase1_deadline`.
- **Phase 2** (admin-activated after groups): knockout-stage scores +
  re-predicted bracket. Points scaled by `phase_multipliers.phase_2`
  (currently 0.7 — `config/worldcup2026.yml`). **Code is dormant** for the
  current competition (`is_phase2_active = false`). Keep the code paths
  working but don't surface Phase 2 in user-facing copy unless the admin
  flips it on.
- The user-facing `/rules` page, landing page, and `FaqSection` all describe
  the single-phase model — no Phase I/II language anywhere. The
  `DeadlineBanner` component was also simplified to drop its `phase` prop.

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

### Testing

```bash
# Backend
docker-compose exec backend pytest tests/ -v

# Frontend type check (keep errors at 0; existing warnings are tolerated)
docker-compose exec frontend-dev npm run check

# Frontend unit tests
docker-compose exec frontend-dev npx vitest run

# Seed Phase 2 test data
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
