# AGENTS.md

Guidance for Codex when working in this repo. Mirrors `CLAUDE.md`; keep both
in sync if either is materially updated.

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

**⚠ Rules-page vs. backend-config divergence (intentional, pending sync).**
The `/rules` page hardcodes a scoring scale that does NOT yet match the
backend config. Until you sync them, leaderboards reflect backend
values, not page advertising:

| Aspect | Page advertises (rules/+page.svelte) | Backend config (worldcup2026.yml) |
|---|---|---|
| Bracket: Round of 32 | **20** | 10 |
| Bracket: Round of 16 | **30** | 15 |
| Bracket: Quarter-final | **40** | 20 |
| Bracket: Semi-final | **50** | 40 |
| Bracket: Final | **75** | 60 |
| Bracket: Winner | 100 | 100 ✓ |
| Bracket: Group advance | (not mentioned) | 10 (still awarded) |
| Bracket: Group position | (not mentioned) | 5 (still awarded) |
| Bonus question points | **+20 flat** | 15 / 20 / 20 by category |
| Rarity worked example | Fixed at 100 predictors | Computed at live pool size |

To sync: change values in `config/worldcup2026.yml`, update tests in
`backend/tests/test_entry_scoring.py` and related, then a one-shot
leaderboard recompute on the next request will pick up new totals.

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
  Use `aware_utc()` from `_datetime.py` defensively at any compare site that
  touches DB-loaded values.

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
  Vite compile error on the `as`. Extract them to a named function in the
  script block (the pattern in `+layout.svelte` — `logoFallbackRail` etc.).
  When this breaks, Vite keeps the last-good build live and the dev server
  *silently* serves stale output — the error is only visible in the dev
  container's stdout (`docker logs predictorv2-frontend-dev-1`), not in the
  browser or via asset probes. Always check dev-server logs first when a
  change "doesn't show up."
- **`app.html` changes do not hot-reload.** Vite treats it as a boot-time
  document shell. Edits require `docker-compose restart frontend-dev`.
