# Predictor v2 - Implementation Plan

## Overview

A from-scratch rewrite of the football prediction competition web app for World Cup 2026. ~30 users, 5-month timeline.

**Tech Stack:**
- Frontend: SvelteKit + TypeScript + Tailwind CSS + DaisyUI
- Backend: FastAPI + SQLModel + PostgreSQL
- Auth: Google OAuth (fastapi-sso) + email/password (JWT)
- Infrastructure: Docker Compose (portable to Hetzner VPS)
- Live Scores: API-Football (api-football.com)

**Key Design Decisions:**
- Flexible tournament format via YAML config (supports 24-team Euro and 48-team World Cup)
- World Cup 2026 format: 48 teams → 12 groups of 4 → Round of 32 → R16 → QF → SF → Final

---

## Project Structure

```
predictorv2/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings, YAML loader
│   │   ├── database.py          # SQLModel engine
│   │   ├── dependencies.py      # Auth deps, DB session
│   │   ├── models/              # SQLModel tables
│   │   ├── schemas/             # Pydantic request/response
│   │   ├── api/                 # Route modules
│   │   └── services/            # Business logic (scoring, locking)
│   ├── tests/
│   ├── alembic/                 # DB migrations
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── lib/
│   │   │   ├── components/      # Svelte components
│   │   │   ├── stores/          # Svelte stores
│   │   │   ├── api/             # API client
│   │   │   └── types/           # TypeScript interfaces
│   │   └── routes/              # SvelteKit pages
│   └── Dockerfile
├── config/
│   └── worldcup2026.yml         # Tournament configuration
├── nginx/
├── docker-compose.yml
└── Makefile
```

---

## Database Schema

| Table | Key Fields | Notes |
|-------|------------|-------|
| `users` | id (UUID), email, name, password_hash, google_id, auth_provider, is_admin | OAuth + email auth |
| `competitions` | id, name, entry_fee, phase1_deadline, phase2_deadline | Tournament instance |
| `fixtures` | id, home_team, away_team, kickoff, stage, group, status | Match data |
| `match_predictions` | id, user_id, fixture_id, home_score, away_score, phase, locked_at | Score predictions |
| `team_predictions` | id, user_id, team, stage, group_position, phase | Bracket predictions |
| `scores` | id, fixture_id, home_score, away_score, source | Actual results |

---

## Scoring System

**Match Predictions (Hybrid):**
- 5 pts for correct outcome (1-X-2)
- +10 pts for exact score
- Hybrid bonus capped at 10 pts

**Advancement Predictions:**
| Stage | Phase 1 | Phase 2 |
|-------|---------|---------|
| Round of 32 | 10 | - |
| Round of 16 | 15 | 10 |
| Quarter-Finals | 20 | 15 |
| Semi-Finals | 40 | 25 |
| Final | 60 | 40 |
| Winner | 100 | 70 |

---

## Development Phases

### Phase 1: Foundation ✅ COMPLETED
- [x] FastAPI + SQLModel project setup
- [x] PostgreSQL + Alembic migrations config
- [x] User model with email/password auth (JWT)
- [x] Google OAuth integration
- [x] SvelteKit setup with Tailwind + DaisyUI
- [x] Login/register pages
- [x] Auth store and protected routes
- [x] Docker Compose dev environment
- [x] Tournament YAML configuration

**Deliverable:** Working authentication flow

### Phase 2: Group Stage ✅ COMPLETED
- [x] Run database migrations
- [x] Seed data for testing (competition, fixtures)
- [x] GroupTable component with live standings
- [x] Mobile-responsive group view
- [x] End-to-end testing of prediction flow
- [x] Admin endpoints for fixtures/scores

**Deliverable:** Users can enter all group stage predictions

### Phase 3: Knockout Bracket ✅ COMPLETED
- [x] Bracket validation (teams must advance through rounds)
- [x] KnockoutBracket visualization (horizontal desktop layout)
- [x] BracketMatch component with team selection
- [x] Mobile accordion view with progress tracking
- [x] Automatic initialization from group stage predictions
- [x] Winner propagation and downstream pick clearing
- [x] Save functionality with backend API integration

**Deliverable:** Visual bracket with team selection

### Phase 4: Scoring & Leaderboard ✅ COMPLETED
- [x] Scoring service (fixed + hybrid modes) — `backend/app/services/scoring.py`, both strategies via Protocol pattern, 23 tests in `test_scoring.py`
- [x] Leaderboard calculation with caching — `backend/app/services/leaderboard.py` 30s in-memory TTL, `invalidate_cache()` hooked from admin sync
- [x] Live score sync from external API — manual via admin endpoint AND automated via background scheduler (`score_scheduler.py`, smart match-window polling, started in `main.py` lifespan)
- [x] 60-second polling endpoint — `GET /scores/poll` (`scores.py:35`) returns live matches + leaderboard; frontend `startPolling(60000)` in `leaderboard.ts:81`
- [x] Position change animations — CSS keyframes (`animate-slide-up`) with stagger; movement arrows ▲/▼ from `leaderboard.py:172` position diff
- [x] Score breakdown view — `LeaderboardEntry.breakdown`, expandable on leaderboard rows + per-user profile pages
- [x] Scheduled background score sync — `score_scheduler.py`; ticks every 60s, skips silently outside match windows; verified by 7 windowing tests

**Deliverable:** Complete scoring and live updates ✓

### Phase 5: Polish & Deploy
- [x] Admin dashboard — backend API + frontend wiring complete (user table with admin/active toggles + search, manual score sync section, phase deadline controls)
- [x] Production Docker setup — `docker-compose.yml` `prod` profile + `nginx/nginx.conf` (rate-limiting, gzip, security headers, 1y static cache)
- [ ] Cloudflare Tunnel or VPS deployment — no `cloudflared` config or deployment automation yet
- [ ] "Dry run" test with friends
- [ ] Mobile device testing — substantive support exists (375px-first design, separate mobile/desktop views); user owns final pass on knockout bracket
- [ ] Final bug fixes

**Deliverable:** Production-ready for World Cup 2026

---

## Recently shipped (outside the original plan)

These features weren't in the original phase breakdown but landed during build:

- **Results page + community scatter plot** (`746bc2c`, polished `8b92deb`) — post-match feedback UI showing all players' predictions per fixture as an SVG scatter, color-coded by accuracy.
- **Public player profiles** (`69a695c` + Phase 1/2 separation in `ea9f703`) — per-user breakdowns with phase-separated bracket views.
- **Mobile knockout bracket redesign** (`bb93c78`) — swipeable two-round pager replacing the always-expanded accordion; works for 4-round (Euro) and 5-round (World Cup) formats.
- **Frontend design pass** (`67f7a08`) — extracted shared components, standardized CSS, removed dead code.
- **Configurable scoring system** (`08043a9`) — strategy pattern via YAML config (`fixed` vs `hybrid` modes).
- **Real WC2026 fixtures seeded from Football-Data.org** (`94f6596`–`7710974`) — shared `FootballDataClient` powers both fixture seeding and live scoring; 104 real fixtures in DB, JSON cache committed for offline re-seed.
- **Background score scheduler** (`396ee26`) — asyncio task started in FastAPI lifespan, polls every 60s during match windows only, smart-skip outside windows to preserve API quota.
- **Placeholder team-name rendering** (`353a6e9`) — knockout fixtures with unresolved teams render as "TBD" in bracket, scatter, results, predictions UI.
- **Admin dashboard frontend wiring** (`bf59aee`) — user management table (admin/active toggles, search, prediction counts) + manual score sync section.
- **flags.ts aliases for all 48 WC2026 nations** (`8e72982`) — Football-Data naming variants resolved (Bosnia-Herzegovina, Cape Verde Islands, Congo DR, Curaçao).
- **Timezone-aware datetimes across the stack** (`c6089cc`) — every `datetime` is now tz-aware UTC end-to-end. DB columns are `TIMESTAMPTZ`. API serialises with explicit `Z` suffix. Browser renders kickoff/deadline times in the user's local timezone via `Intl`. Migration `2c5e9a4f7d10` converts 19 columns across 6 tables.

## Remaining-work punch list (sorted by criticality for June 11 launch)

1. **Cloudflare Tunnel / VPS deployment** — Docker prod setup is ready; needs the actual hosting decision and tunnel/DNS plumbing. **Biggest remaining blocker.**
2. **Dry run with friends** — pre-tournament stress test with real users.
3. **Final mobile pass on the knockout bracket** — owner: user (real-device test of the swipeable pager).
4. **Loose ends from `issues.md`** — duplicate `CORS_ORIGINS` between `docker-compose.yml` and `.env`; `greenlet` missing.
5. **Push local main to origin** — local is ahead of origin; push when comfortable backing up the work.
6. **Rotate the 3 leaked credentials** — `GOOGLE_CLIENT_SECRET`, `API_FOOTBALL_KEY`, `FOOTBALL_DATA_TOKEN` (exposed earlier this session in error). User-action only.

---

## Key Constraints

- Predictions lock 5 minutes before kickoff
- Blind pool: users cannot see others' predictions until match locks
- 100% data integrity required - no lost predictions
- Mobile-first: verify all UI on 375px viewport

---

## Commands

```bash
# Development
make dev              # Start all services
make dev-backend      # Backend only
make dev-frontend     # Frontend only

# Database
make migrate          # Run migrations
make db-shell         # PostgreSQL shell

# Testing
make test             # All tests
make test-backend     # Backend tests only
```
