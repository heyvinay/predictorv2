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
`premium-night` default / `light` alternative), `svelte-motion`,
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

### Phases
- **Phase 1** (pre-tournament): group-stage scores + knockout-bracket
  advancement. Locks per-match.
- **Phase 2** (admin-activated after groups): knockout-stage scores +
  re-predicted bracket. Points scaled by `phase_multipliers.phase_2`
  (currently 0.7 — `config/worldcup2026.yml`). Kept stored separately from
  Phase 1.

### Locking & visibility
- Predictions lock **5 minutes before kickoff** (`backend/app/services/locking.py`).
- Blind pool: users cannot see others' predictions until a match locks.
- 100% data integrity — never silently drop or overwrite a prediction.

### Scoring
Modes — `logarithmic` (default, Shannon-surprisal rarity bonus), `fixed`
(flat), and `hybrid` (legacy linear rarity). Selected via `scoring.mode` in
`config/worldcup2026.yml`. Engine in `backend/app/services/scoring.py`.
See `docs/scoring-system.md` for the formula, bonus table, and rationale.

**Rule:** no scoring logic changes without a corresponding `pytest` case.

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

Two DaisyUI themes are registered in `frontend/tailwind.config.js`:
**`premium-night`** (default — champagne gold CTAs on midnight navy) and
**`light`**. The choice is persisted in `localStorage['predictor:theme']` and
applied by the FOUC-prevention script in `frontend/src/app.html`; the store
lives at `frontend/src/lib/stores/theme.ts`. Layout + mobile bottom nav are
in `frontend/src/routes/+layout.svelte`.

**`premium-night` tokens** (the default):
- `primary` `#D4AF37` (champagne gold) · `primary-content` `#0B1329` (navy
  on gold buttons)
- `secondary` `#1C2541` (premium blue) · `accent` `#D4AF37` (same gold)
- `base-100` `#0B1329` (midnight navy canvas) · `base-200` `#1C2541` ·
  `base-300` `#2A3552`
- `success` `#059669` · `warning` `#D97706` · `error` `#B91C1C`

**Typography:** dual-font system, both bundles loaded unconditionally in
`app.html`; a CSS layer in `app.css` gates which is active per theme:
- `light` → Bebas Neue (display) + DM Sans (body)
- `premium-night` → Manrope (display / scores) + Inter (body)

**Global classes** (`frontend/src/app.css`): `stadium-card`, `match-card`
(+ `match-card-v2` for the redesigned variant), `stat-card`,
`leaderboard-row`, `auth-bg`, `.noise`, `.score-input`. Custom utilities
`pitch-pattern`, `stadium-glow`, `hero-gradient`, plus shadow tokens
`shadow-glow-green`, `shadow-glow-gold`, `shadow-card` in
`tailwind.config.js`. Standalone named colors `turf`, `pitch`, `gold`,
`trophy`, `navy` are available outside the theme. Prefer DaisyUI `shadow*`
+ the `glow-*` shadows over hand-rolled box-shadows.

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
