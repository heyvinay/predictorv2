# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The Predictor v2** is a self-hosted web application for managing international football prediction competitions (World Cup, Euros) for ~30 friends.

Current focus: **World Cup 2026**

## Tech Stack

**Backend:**
- FastAPI (Python 3.11+)
- SQLModel (Pydantic + SQLAlchemy ORM)
- PostgreSQL 16
- Alembic for migrations
- YAML-based tournament configuration
- External data: Football-Data.org or API-Football (planned)

**Frontend:**
- SvelteKit with TypeScript
- Tailwind CSS + DaisyUI — two themes defined in `frontend/tailwind.config.js`: **`premium-night`** (dark, default — gold `#D4AF37`, midnight navy canvas `#0B1329`) and **`premium-day`** (light — deeper gold `#B8941F` for AA contrast on ice canvas `#F8FAFC`). Same voice across both; themes change colour, not typography.
- Fonts: **Manrope** (display, 700/800) + **Inter** (body, 400–700) + **JetBrains Mono** (500, for timers/codes). Single family pair for both themes. Loaded in `frontend/src/app.html`.
- Svelte stores for state management
- Vitest for unit tests (pure utilities + widget fallbacks)
- svelte-motion for animations (planned)

**Infrastructure:**
- Docker Compose (development)
- Nginx reverse proxy (production)
- Cloudflare Tunnel (for self-hosting)

## Project Structure

```
/predictorv2
├── /backend
│   ├── /app
│   │   ├── /api             # FastAPI routes
│   │   ├── /models          # SQLModel tables
│   │   ├── /schemas         # Pydantic request/response models
│   │   └── /services        # Business logic (scoring, locking, standings)
│   └── /tests               # pytest tests
├── /frontend
│   ├── /src
│   │   ├── /lib
│   │   │   ├── /api         # API client functions
│   │   │   ├── /components  # Shared UI: MatchCard, GroupTable, ResultCard,
│   │   │   │                #   SaveButton, ErrorAlert, Icon, ScatterPlot,
│   │   │   │                #   EntrySelector, Sparkline, GoogleLoginButton …
│   │   │   │   ├── /bracket # Interactive knockout bracket (KnockoutBracket,
│   │   │   │   │            #   BracketMatch) — state machine in bracketResolver
│   │   │   │   └── /predictions # Wizard sub-views (Phase1Groups, Phase1Bracket,
│   │   │   │                    #   Phase2Content, DeadlineBanner, ProgressBar)
│   │   │   ├── /stores      # Svelte stores
│   │   │   ├── /types       # TypeScript interfaces
│   │   │   └── /utils       # Helper functions (incl. teamCodes.ts,
│   │   │                    #   bracketResolver.ts, standings.ts,
│   │   │                    #   widgetFallbacks.ts)
│   │   └── /routes          # SvelteKit pages
├── /config                  # Tournament YAML configuration
├── /docs                    # Documentation
├── /nginx                   # Proxy config (production)
└── docker-compose.yml
```

## Key Domain Concepts

### Competition Phases
- **Phase 1**: Pre-tournament predictions
  - Group stage match scores
  - Knockout bracket advancement (predict which teams reach each round)
  - Locks at tournament start or per-match (5 min before kickoff)

- **Phase 2**: Knockout stage predictions (activated by admin after groups complete)
  - Knockout match scores
  - Updated bracket predictions based on actual group results
  - Points reduced to 70% (configurable multiplier)

### Scoring System

Configured in `config/worldcup2026.yml`. See `docs/scoring-system.md` for full documentation.

**Scoring Modes:**
- `fixed`: Flat points for correct predictions
- `hybrid`: Base points + rarity bonus (fewer correct = higher bonus)

**Match predictions:**
- 5 pts: correct outcome (1-X-2)
- +10 pts: exact score bonus

**Advancement predictions:**
- 10 pts: team advances from group
- 5 pts: correct group position
- 10-100 pts: knockout stage advancement (scales by round)

### Critical Constraints
- Predictions lock 5 minutes before kickoff
- Users cannot see others' predictions until match locks (blind pool)
- Phase 1 and Phase 2 predictions are stored separately
- 100% data integrity required - no lost predictions

### Datetime Rule (system-wide invariant)

**Every datetime in this system is timezone-aware UTC.** Naive datetimes are forbidden — comparing or storing one is a bug.

- **DB**: every datetime column is `TIMESTAMPTZ` (PostgreSQL `TIMESTAMP WITH TIME ZONE`). See `backend/app/models/_datetime.py` for the column factory and `default_factory`.
- **Python**: use `utc_now()` from `app.models._datetime`, never `datetime.utcnow()` (deprecated and naive). Construct test datetimes with `datetime(..., tzinfo=timezone.utc)`.
- **API**: Pydantic serializes aware datetimes as ISO 8601 with explicit offset (`...Z` or `+00:00`).
- **Frontend**: `new Date(string).toLocaleString(...)` parses correctly because of the explicit offset, then renders in the user's local timezone via `Intl`.
- **DB-driver gotcha**: aiosqlite drops tzinfo on read even when the column is declared aware; PostgreSQL preserves it. Use `aware_utc()` (also in `_datetime.py`) at any compare site that touches DB-loaded values, defensively.

The rule was established in commit `c6089cc`. The original conversion migration was subsequently squashed into the consolidated initial migration (`f06b6a2077d3`) during pre-production prep. Violating the rule silently shifts kickoffs and deadlines by the user's UTC offset — a data-integrity disaster for a prediction app where lock timing matters.

## Key Files

| File | Purpose |
|------|---------|
| `config/worldcup2026.yml` | Tournament and scoring configuration |
| `backend/app/services/scoring.py` | Scoring strategies and point calculation |
| `backend/app/services/locking.py` | Prediction locking logic |
| `backend/app/services/standings.py` | Group standings calculation |
| `backend/app/api/admin.py` | Admin endpoints (users, paid status, phase ops, score sync) |
| `frontend/tailwind.config.js` | DaisyUI `premium-night` / `premium-day` theme tokens, font families (Manrope / Inter / JetBrains Mono), legacy custom utilities (pitch-pattern, stadium-glow, glow-*, noise) earmarked for cleanup |
| `frontend/src/app.css` | Global styles — `stadium-card`, `match-card`, `stat-card`, `leaderboard-row`, `auth-bg`, `.noise`, font setup |
| `frontend/src/app.html` | Sets `data-theme="premium-night"` (FOUC-safe), migrates legacy `'light'` → `'premium-day'`, loads Manrope + Inter + JetBrains Mono |
| `frontend/src/routes/+layout.svelte` | Root layout — dark navbar + mobile bottom nav, mounted on every route |
| `frontend/src/lib/components/bracket/KnockoutBracket.svelte` | Interactive knockout bracket (wall chart desktop / swipeable mobile) |
| `frontend/src/lib/components/bracket/BracketMatch.svelte` | Single match card inside the bracket |
| `frontend/src/lib/components/EntrySelector.svelte` | Multi-entry switcher used in the wizard, profile, and leaderboard |
| `frontend/src/lib/components/Sparkline.svelte` | Rank-trajectory sparkline (leaderboard + dashboard) |
| `frontend/src/lib/stores/predictions.ts` | Prediction state management |
| `frontend/src/lib/utils/widgetFallbacks.ts` | Deterministic fallbacks for backend-pending dashboard/leaderboard widgets |
| `frontend/src/lib/utils/bracketResolver.ts` | FIFA 2026 knockout bracket logic |
| `frontend/src/lib/utils/teamCodes.ts` | Team name → FIFA 3-letter code mapping for flag swatches |

## Development

### Running Locally

```bash
# Start all services
docker-compose up -d

# Backend: http://localhost:8000
# Frontend dev: http://localhost:5173 (with --profile dev)
```

### Common Commands

```bash
# Run backend tests
docker-compose exec backend pytest tests/ -v

# Check frontend types
cd frontend && npm run check

# View logs
docker-compose logs -f backend
```

## Development Rules

1. **Scoring Engine Safety**: No scoring logic changes without a corresponding `pytest` test case
2. **Mobile First**: Verify all UI on 375px viewport width
3. **Type Safety**:
   - Backend: Strict Pydantic models
   - Frontend: No `any` types - define interfaces in `/lib/types`
4. **Phase Separation**: Phase 1 and Phase 2 data must be kept separate (different stores, filtered queries)

## Database migrations

**Alembic is the single source of truth for schema.** Every backend startup
runs `alembic upgrade head` automatically (`backend/app/database.py:init_db`,
called from the FastAPI lifespan). There is no `SQLModel.metadata.create_all`
fallback — tables only ever exist because a migration created them.

Workflow for adding a new table or column:

```bash
# 1. Add/modify the SQLModel class under backend/app/models/ and
#    import it in backend/app/models/__init__.py
# 2. Generate the migration:
docker-compose exec backend alembic revision --autogenerate -m "describe change"
# 3. Review the file under backend/alembic/versions/ — autogenerate is good
#    but not perfect (data migrations, default values, server_default
#    semantics, enum changes all need a human pass)
# 4. Restart the backend. init_db() picks up the new revision and applies it.
docker-compose restart backend
```

The migration is applied on every environment the backend boots in — dev,
staging, prod. A failing migration takes the app down at startup, which is
the safe default for a schema-versioned system. Logs surface the underlying
error.

If you ever need to manually stamp / downgrade / inspect:

```bash
docker-compose exec backend alembic current
docker-compose exec backend alembic history
docker-compose exec backend alembic downgrade -1
docker-compose exec backend alembic stamp <revision>   # rarely needed now
```

## Testing

```bash
# Backend unit tests (scoring, auth, locking)
docker-compose exec backend pytest tests/test_scoring.py -v

# Frontend type checking
cd frontend && npm run check                           # or via container:
docker-compose exec frontend-dev npm run check

# Frontend unit tests (vitest — widget fallbacks, sparkline path, standings,
# bracketResolver, leaderboard helpers, entry selector logic)
docker-compose exec frontend-dev npx vitest run

# Manual testing with test data
docker-compose exec backend python scripts/seed_phase2_test.py
```

**Pre-existing svelte-check baseline:** ~59 warnings (mostly `@apply` and a11y), 0 errors. New code should keep the error count at zero; a couple of new warnings is acceptable.

## UI Guidelines

The site uses the DaisyUI **`premium-night`** theme by default — a dark, sports-broadcast editorial palette: champagne-gold CTAs on a midnight-navy canvas, mint-green success, amber/red urgency. A second theme **`premium-day`** swaps the canvas to an ice white (`#F8FAFC`) and deepens the gold to `#B8941F` for AA contrast on the lighter surface. Themes change colour, not voice — same fonts, same hierarchy, same component language. The root `<html>` tag sets `data-theme="premium-night"` (`app.html`, FOUC-safe).

Components use **semantic DaisyUI classes** (`bg-primary`, `bg-base-100`, `text-base-content`, `text-success` …) — never raw hex. Dim/faint text is `text-base-content/55` / `/30`; soft accent fills are `bg-success/20` etc.

**Theme tokens** (in `frontend/tailwind.config.js`):

| Token | `premium-night` (dark) | `premium-day` (light) | Use |
|---|---|---|---|
| `primary` | `#D4AF37` champagne gold | `#B8941F` deeper gold | CTAs, brand, accents |
| `success` | `#059669` mint | `#059669` mint | Exact score, "good news" |
| `warning` | `#D97706` amber | `#B45309` amber | Outcome / lock |
| `error` | `#B91C1C` red | `#B91C1C` red | Miss |
| `base-100` | `#0B1329` midnight navy | `#F8FAFC` ice (NOT pure white) | Canvas |
| `base-200` | `#1C2541` premium navy | `#FFFFFF` white | Surfaces, cards |
| `base-300` | `#2A3552` slate | `#E2E8F0` slate-200 | Dividers, borders |
| `base-content` | `#E2E8F0` off-white | `#0B1329` navy | Body ink |

Radii: `rounded-box` (14px / `0.875rem`), `rounded-btn` (10px / `0.625rem`), `rounded-badge` (8px / `0.5rem`).

**Typography** — one family pair, both themes:
- **Manrope** 700/800 (display, `font-display`) — wordmark, headlines, scores, big stats
- **Inter** 400/500/600/700 (body, `font-sans`) — UI text, labels, captions
- **JetBrains Mono** 500 (mono, `font-mono`) — timers, codes, monospace data
- **Bebas Neue** (opt-in via `font-hero`) — landing-page hero headlines only. Reach for it when you want a loud, broadcast-poster moment; Manrope still carries the rest of the system.

**Global classes** (in `frontend/src/app.css`): `stadium-card`, `match-card`, `stat-card`, `leaderboard-row`, `auth-bg`, `.noise`, plus DaisyUI's `btn`, `card`, `navbar`, `dropdown`, `menu`, `tabs`, etc. Custom utilities `pitch-pattern`, `stadium-glow`, `glow-primary` / `glow-accent` live in `tailwind.config.js`.

**Card shadows:** prefer DaisyUI's `shadow`/`shadow-xl` plus the custom `glow-*` utilities for emphasis. Avoid hand-rolled box-shadow hacks unless the theme tokens can't express it.

**Save actions** show feedback only after the backend confirms.
**Mobile**: one logical group at a time; avoid grid-of-cards on small screens.
**Phase tabs**: switch between Phase 1 and Phase 2 predictions. The Phase I/II toggle and the Groups / Knockout / Bonus section toggle live as a stacked pair in the wizard hero.
**Bracket gating**: in Phase 1 the Knockout sub-section is locked until every group prediction is filled in (uses predicted standings to seed R32 — would otherwise show TBD slots).
**Score inputs** are capped at 15 goals per side, enforced live in the input event so the user sees the cap immediately.

**Flag swatches** are 2/3-stripe gradient placeholders driven by `lib/utils/teamCodes.ts` — earmarked for a real flag library in a follow-up plan.

**Backend-dependent widgets** (rank sparklines, social signals, hot pick, bracket exposure, underdog hits, steepest climb) fall back to deterministic stub data via `frontend/src/lib/utils/widgetFallbacks.ts` when the relevant endpoint is empty, unavailable, or newly deployed.
