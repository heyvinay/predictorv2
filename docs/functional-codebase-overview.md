# Predictor v2 Functional Codebase Overview

This document explains the application from a functional perspective: what the system does, which code owns each feature, how data flows through the backend and frontend, and where to look when adding new functionality.

The short version: Predictor v2 is a self-hosted football prediction pool for World Cup 2026. Users register, predict match scores and knockout advancement, answer bonus questions, then watch scores, rankings, profiles, and results update as the tournament progresses. Admins manage users, deadlines, phases, bonus answers, and score sync.

## 1. Product Shape

### Main User Roles

| Role | What they can do | Important code |
| --- | --- | --- |
| Visitor | Read public rules, register, start Google login | `frontend/src/routes/rules/+page.svelte`, `login`, `register`, `backend/app/api/auth.py` |
| Player | Enter predictions, view dashboard, leaderboard, results, profiles | `frontend/src/routes/+page.svelte`, `predictions`, `leaderboard`, `results`, `profile` |
| Admin | Manage phase deadlines, activate Phase II, sync scores, manage users and bonus answers | `frontend/src/routes/admin/+page.svelte`, `backend/app/api/admin.py` |

### Competition Phases

| Phase | Purpose | Functional behavior |
| --- | --- | --- |
| Phase I | Pre-tournament prediction phase | Users predict group match scores, build a full bracket from predicted group standings, and answer bonus questions. These picks are full value. |
| Phase II | Post-group-stage prediction phase | Admin activates this after group stage. Users predict knockout bracket and knockout match scores using actual group results. These picks are reduced by the configured multiplier, currently 70 percent. |

The current phase is not inferred from dates alone. `backend/app/services/locking.py` returns Phase II only when the active `Competition.is_phase2_active` flag has been set by an admin.

## 2. Core User Journeys

### 2.1 Registration And Login

Players can register with email/password or authenticate through Google OAuth.

Backend:

- `POST /api/auth/register` creates a `User` with a bcrypt password hash.
- `POST /api/auth/login` validates credentials and returns a JWT.
- `GET /api/auth/google` starts Google SSO.
- `GET /api/auth/google/callback` verifies Google identity, links or creates a user, then redirects to the frontend callback route with a token.
- `GET /api/auth/me` returns the current user.
- `POST /api/auth/me/password` changes passwords for email-authenticated users only.

Frontend:

- `frontend/src/lib/stores/auth.ts` stores the JWT in `localStorage`, injects it into `ApiClient`, fetches the current user, and clears persisted drafts on logout/token failure.
- `frontend/src/routes/login/+page.svelte` and `frontend/src/routes/register/+page.svelte` render the dark-theme auth screens.
- `frontend/src/routes/auth/callback/+page.svelte` handles the OAuth redirect token.

### 2.2 Dashboard

The dashboard is the logged-in landing page. It summarizes the player's current rank, points, exact scores, correct outcomes, bonus haul, live matches, next lock, closest rivals, hot pick, bracket exposure, top five, and upcoming fixtures.

Key code:

- Page: `frontend/src/routes/+page.svelte`
- Fixtures store: `frontend/src/lib/stores/fixtures.ts`
- Leaderboard store: `frontend/src/lib/stores/leaderboard.ts`
- Predictions store: `frontend/src/lib/stores/predictions.ts`
- Backend endpoints:
  - `GET /api/fixtures/`
  - `GET /api/leaderboard/`
  - `GET /api/leaderboard/snapshots/me`
  - `GET /api/leaderboard/climbers`
  - `GET /api/predictions/agreements`
  - `GET /api/predictions/bracket-exposure`

Some dashboard widgets use real backend data with deterministic stub fallbacks from `frontend/src/lib/utils/widgetFallbacks.ts` for empty, unavailable, or newly deployed states.

### 2.3 Phase I Predictions

The prediction wizard lets a player enter all group match scores, see predicted standings update live, inspect third-place qualifying order, build the knockout bracket, and answer bonus questions.

Key behavior:

- Group scores are edited locally first.
- Unsaved match predictions are kept in `unsavedChanges`.
- Drafts persist to localStorage through `frontend/src/lib/stores/unsavedPersistence.ts`.
- Save actions call the backend only when the user explicitly saves.
- Score inputs are capped in the UI at 15 goals per team.
- The Phase I bracket is gated until all group-stage match predictions are complete, because the bracket needs predicted standings to seed the Round of 32.
- Bonus picks lock with Phase I.

Key code:

- Page: `frontend/src/routes/predictions/+page.svelte`
- Store: `frontend/src/lib/stores/predictions.ts`
- Group standings utility: `frontend/src/lib/utils/standings.ts`
- Bracket resolver: `frontend/src/lib/utils/bracketResolver.ts`
- Bracket config: `frontend/src/lib/config/bracketConfig.ts`
- Third-place mapping: `frontend/src/lib/config/thirdPlaceMapping.json`
- API:
  - `GET /api/predictions/matches`
  - `PUT /api/predictions/matches/{fixture_id}`
  - `POST /api/predictions/matches/batch`
  - `GET /api/predictions/bracket?phase=phase_1`
  - `PUT /api/predictions/bracket`
  - `GET /api/predictions/bonus/questions`
  - `GET /api/predictions/bonus`
  - `POST /api/predictions/bonus`

### 2.4 Phase II Predictions

Phase II opens only after an admin activates it. The frontend then fetches actual knockout fixtures and actual group standings.

Key behavior:

- The page switches to a Phase II tab when `is_phase2_active` is true.
- The Phase II bracket hides the Round of 32 column and starts from later rounds.
- Phase II bracket picks and Phase II match predictions are stored separately from Phase I through the `PredictionPhase` value.
- Phase II bracket lock is controlled by `Competition.phase2_bracket_deadline`.

Key code:

- Frontend phase state: `frontend/src/lib/stores/phase.ts`
- Actual fixtures/standings: `frontend/src/lib/stores/fixtures.ts`
- Backend:
  - `GET /api/competition/phase-status`
  - `GET /api/fixtures/knockout/actual`
  - `GET /api/fixtures/standings/actual`
  - `POST /api/admin/competition/phase2/activate`
  - `POST /api/admin/competition/phase2/deactivate`

### 2.5 Results

The results page shows finished fixtures and compares the current user's prediction to the actual score.

Key behavior:

- Users can filter by group or knockout stage.
- Users can filter by prediction result: exact, outcome, missed, or all.
- Result classification is done client-side by `frontend/src/lib/utils/predictionResult.ts`.

Key code:

- Page: `frontend/src/routes/results/+page.svelte`
- Utility: `frontend/src/lib/utils/predictionResult.ts`
- Backend data comes from `GET /api/fixtures/` and `GET /api/predictions/matches`.

There is also a community predictions backend endpoint, `GET /api/predictions/matches/{fixture_id}/community`, which enforces blind-pool visibility before returning all players' picks for a fixture.

### 2.6 Leaderboard

The leaderboard is calculated from current data rather than stored as a permanent ranking table.

Key behavior:

- Supports overall, Phase I, and Phase II views.
- Each row includes total points, exact scores, correct outcomes, movement, and a detailed point breakdown.
- Data is cached in memory for 30 seconds in the backend.
- A live polling path combines live scores and leaderboard in one response.
- Daily leaderboard snapshots support rank trajectory and steepest climber widgets.

Key code:

- Page: `frontend/src/routes/leaderboard/+page.svelte`
- Store: `frontend/src/lib/stores/leaderboard.ts`
- Backend:
  - `backend/app/api/leaderboard.py`
  - `backend/app/services/leaderboard.py`
  - `backend/app/services/scoring.py`
  - `backend/app/services/snapshots.py`

Endpoints:

- `GET /api/leaderboard/`
- `GET /api/leaderboard/?phase=phase_1`
- `GET /api/leaderboard/?phase=phase_2`
- `GET /api/leaderboard/scoring-rules`
- `GET /api/leaderboard/breakdown/{user_id}`
- `GET /api/leaderboard/snapshots/me`
- `GET /api/leaderboard/snapshots/{user_id}`
- `GET /api/leaderboard/climbers`
- `POST /api/leaderboard/invalidate`

### 2.7 Profiles

Profiles show player statistics and visible predictions.

Key behavior:

- Own profile includes account data and password management.
- Public profiles show stats, bracket summary, and recent visible predictions.
- Blind-pool rules are enforced: another user's match predictions only appear once the fixture is locked or finished.

Key code:

- Own profile: `frontend/src/routes/profile/+page.svelte`
- Public profile: `frontend/src/routes/profile/[userId]/+page.svelte`
- Backend:
  - `GET /api/auth/me/stats`
  - `GET /api/users/{user_id}/profile`
  - `GET /api/users/{user_id}/predictions`
  - `backend/app/services/profile.py`

### 2.8 Admin Console

The admin console controls operational parts of the competition.

Key behavior:

- View system stats.
- Trigger manual score sync.
- Set Phase I deadline.
- Activate or deactivate Phase II.
- Set Phase II bracket deadline.
- Manage users: admin status, active status, paid status.
- Set correct answers for bonus questions.

Key code:

- Page: `frontend/src/routes/admin/+page.svelte`
- API client: `frontend/src/lib/api/admin.ts`
- Bonus API client: `frontend/src/lib/api/bonus.ts`
- Backend: `backend/app/api/admin.py`

Important admin endpoints:

- `GET /api/admin/stats`
- `GET /api/admin/users`
- `PATCH /api/admin/users/{user_id}/admin`
- `PATCH /api/admin/users/{user_id}/active`
- `PATCH /api/admin/users/{user_id}/paid`
- `GET /api/admin/competitions`
- `POST /api/admin/competition/phase1/deadline`
- `POST /api/admin/competition/phase2/activate`
- `POST /api/admin/competition/phase2/deactivate`
- `POST /api/admin/scores/sync`
- `GET /api/admin/bonus/answers`
- `POST /api/admin/bonus/answers`

## 3. Backend Architecture

### 3.1 Entry Point And App Lifecycle

`backend/app/main.py` creates the FastAPI app.

On startup:

1. `init_db()` runs `alembic upgrade head`.
2. `scheduler_lifespan()` starts the score scheduler.
3. API routers are mounted under `/api`.

Important point: Alembic is the only schema creation path. There is no `SQLModel.metadata.create_all` fallback.

### 3.2 Configuration

`backend/app/config.py` loads environment settings and the tournament YAML config.

Important settings:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `FOOTBALL_DATA_TOKEN`
- `TOURNAMENT_CONFIG_PATH`
- `CORS_ORIGINS_STR`

Tournament config lives in `config/worldcup2026.yml`. It defines:

- tournament size and groups
- locking settings
- scoring mode and point values
- phase multipliers
- bonus question definitions

### 3.3 Authentication Dependencies

`backend/app/dependencies.py` owns:

- password hashing and verification
- JWT creation
- current-user lookup
- optional-user lookup
- admin-user enforcement
- database session dependency aliases

Route signatures use aliases such as `CurrentUser`, `OptionalUser`, `AdminUser`, and `DbSession`.

### 3.4 Data Models

| Model | Table | Functional purpose |
| --- | --- | --- |
| `User` | `users` | Player/admin account, auth provider, active flag, paid flag, optional competition link |
| `Competition` | `competitions` | Active competition metadata, entry fee, phase deadlines, external API ID |
| `Fixture` | `fixtures` | A scheduled/live/finished match with teams, kickoff, stage, group, external ID |
| `Score` | `scores` | Actual score for a fixture, including extra time and penalties |
| `MatchPrediction` | `match_predictions` | A user's predicted score for one fixture and phase |
| `TeamPrediction` | `team_predictions` | A user's predicted team-stage advancement and phase |
| `BonusPrediction` | `bonus_predictions` | A user's answer to a YAML-defined bonus question |
| `BonusAnswer` | `bonus_answers` | Admin-entered correct answer for a bonus question |
| `LeaderboardSnapshot` | `leaderboard_snapshots` | Daily rank/points snapshot used for trend charts |

Datetime invariant:

- Use `utc_now()` and `utc_datetime_column()` from `backend/app/models/_datetime.py`.
- All datetime columns are timezone-aware.
- Compare DB-loaded datetimes defensively with `aware_utc()` where needed.

### 3.5 Service Layer

| Service | Functional responsibility |
| --- | --- |
| `scoring.py` | Loads scoring config, calculates match points, advancement points, bonus points integration, full point breakdowns |
| `leaderboard.py` | Calculates ranked leaderboard, phase filtering, 30-second cache, movement from previous cached positions |
| `locking.py` | Fixture locking, phase state, Phase I lock, Phase II bracket lock, batch lock helper |
| `standings.py` | Actual group standings from finished fixtures, FIFA-like tiebreakers, best third-place teams |
| `bonus.py` | Loads bonus questions from YAML, normalizes answers, scores bonus points |
| `profile.py` | Aggregates stats for current/public profiles |
| `bracket_exposure.py` | Calculates current maximum bracket points still on the line for a user's picks |
| `score_sync.py` | Pulls external scores and applies them to fixtures/scores |
| `score_scheduler.py` | Background loop for daily snapshots and live score sync during match windows |
| `fixture_sync.py` | Imports Football-Data fixture data from cache or API into `Fixture` rows |
| `external_scores.py` | Provider abstraction for live score data |
| `external/football_data.py` | HTTP client and status mapping for Football-Data.org |

## 4. Scoring And Locking

### 4.1 Match Scoring

Match scoring supports two strategies:

- `fixed`: flat points for correct outcome plus exact score bonus.
- `hybrid`: base outcome points plus a rarity bonus based on how many players got the outcome right.

Current config in `config/worldcup2026.yml`:

- correct outcome: 5
- exact score bonus: 10
- hybrid cap: 10
- Phase I multiplier: 1.0
- Phase II multiplier: 0.7

The main entry point is `calculate_user_points()` in `backend/app/services/scoring.py`.

### 4.2 Advancement Scoring

Team advancement predictions earn points when the team reaches at least the predicted stage. Stage values and points come from the YAML config.

Backend advancement stage keys currently include:

- `group`
- `round_of_32`
- `round_of_16`
- `quarter_final`
- `semi_final`
- `final`
- `winner`

### 4.3 Bonus Question Scoring

Bonus questions are config-driven, not stored as question rows in the database.

Flow:

1. Questions are loaded from `config/worldcup2026.yml`.
2. Users save answers to `bonus_predictions`.
3. Admins set correct answers in `bonus_answers`.
4. `calculate_bonus_points()` compares answers case-insensitively and accent-insensitively.
5. Leaderboard total includes bonus question points.

### 4.4 Locking

There are several lock concepts:

- Match predictions lock 5 minutes before fixture kickoff.
- Phase I bonus picks lock at `Competition.phase1_deadline`.
- Phase I bracket UI locks from `isPhase1Locked`.
- Phase II bracket locks at `Competition.phase2_bracket_deadline`.
- Blind-pool visibility unlocks when a fixture is locked or finished.

## 5. Frontend Architecture

### 5.1 SvelteKit Routes

| Route | Functional purpose |
| --- | --- |
| `/` | Dashboard for authenticated users |
| `/login` | Email login plus Google login |
| `/register` | Email registration plus Google login |
| `/auth/callback` | OAuth token callback |
| `/rules` | Public rules and competition info |
| `/predictions` | Phase I and Phase II prediction wizard |
| `/results` | Finished-match result review |
| `/leaderboard` | Overall/phase leaderboard |
| `/profile` | Current user's account and stats |
| `/profile/[userId]` | Public player profile and visible predictions |
| `/admin` | Admin console |

All routes render inside the dark `data-theme="predictor"` DaisyUI layout: a sticky top navbar with a brand mark, the four main nav items, an optional Admin link, and a user dropdown; plus a fixed mobile bottom nav under 700px.

### 5.2 API Client Layer

`frontend/src/lib/api/client.ts` wraps `fetch` and adds the JWT `Authorization` header when the auth store has a token.

Feature-specific API files map frontend calls to backend endpoints:

- `auth.ts`
- `fixtures.ts`
- `predictions.ts`
- `bonus.ts`
- `leaderboard.ts`
- `scores.ts`
- `competition.ts`
- `admin.ts`
- `users.ts`

### 5.3 Stores

| Store | Functional responsibility |
| --- | --- |
| `auth.ts` | JWT, current user, login/register/logout, OAuth token handling |
| `phase.ts` | Phase status, phase deadlines, countdowns, Phase II active state |
| `fixtures.ts` | All fixtures, group fixtures, knockout fixtures, live/upcoming/finished derived views |
| `predictions.ts` | Saved predictions, unsaved match drafts, Phase I bracket, Phase II bracket |
| `leaderboard.ts` | Leaderboard entries, current user rank, phase filtering, live polling |
| `unsavedPersistence.ts` | LocalStorage mirror for unsaved match and bracket drafts |

### 5.4 Design System

The UI uses the DaisyUI **predictor** theme: a dark sports-broadcast palette with green primary, navy secondary, gold accent, near-black background, and subtle pitch-pattern / noise overlays.

Key files:

- `frontend/tailwind.config.js`: theme tokens (`primary`, `secondary`, `accent`, `base-100..300`), custom utilities (pitch-pattern, stadium-glow, glow-*), and font setup.
- `frontend/src/app.html`: sets `data-theme="predictor"` and loads Bebas Neue + DM Sans.
- `frontend/src/app.css`: global classes (`stadium-card`, `match-card`, `stat-card`, `leaderboard-row`, `auth-bg`, `.noise`) and base typography.
- `frontend/src/routes/+layout.svelte`: dark navbar, mobile bottom nav, user dropdown.
- `frontend/src/lib/components/MatchCard.svelte`, `GroupTable.svelte`, `ThirdPlaceTable.svelte`, `ResultCard.svelte`, `SaveButton.svelte`, `ErrorAlert.svelte`, `Icon.svelte`, `ScatterPlot.svelte`, `PredictionTable.svelte`, `GoogleLoginButton.svelte`, `EntrySelector.svelte`, `Sparkline.svelte`: shared UI primitives.
- `frontend/src/lib/components/bracket/KnockoutBracket.svelte` + `BracketMatch.svelte`: interactive knockout bracket; state machine lives in `lib/utils/bracketResolver.ts`.
- `frontend/src/lib/components/predictions/Phase1Groups.svelte`, `Phase1Bracket.svelte`, `Phase2Content.svelte`, `DeadlineBanner.svelte`, `ProgressBar.svelte`: prediction wizard sub-views.

## 6. Important Data Flows

### 6.1 Saving Match Predictions

1. User edits score inputs in `/predictions`.
2. `updateLocalPrediction()` writes to `unsavedChanges`.
3. `unsavedPersistence.ts` mirrors drafts to localStorage.
4. User clicks save.
5. `saveAllPredictions()` sends a batch to `POST /api/predictions/matches/batch`.
6. Backend skips invalid or locked fixtures, upserts unlocked predictions, and stamps the current phase.
7. Frontend merges returned predictions into `matchPredictions` and clears drafts.

### 6.2 Saving Bracket Predictions

1. `KnockoutBracket` initializes bracket state from group standings.
2. User clicks winners.
3. The bracket emits a `BracketPrediction`.
4. The route converts that into `TeamAdvancementPrediction[]`.
5. `saveBracketPredictions()` sends `PUT /api/predictions/bracket`.
6. Backend deletes existing team predictions for the current user and current phase, then inserts the submitted picks.

Important: the backend saves bracket picks to whichever phase `get_current_phase()` returns. If you add phase-specific bracket behavior, make sure phase status is correct before saving.

### 6.3 Score Sync And Live Data

1. `score_scheduler.py` runs every 60 seconds.
2. Each tick attempts daily leaderboard snapshots.
3. It checks whether any match is live or imminent.
4. If yes, it fetches live scores through `FootballDataScoreProvider`.
5. `score_sync.py` matches external scores to fixtures by `external_id` first, then by home/away team names.
6. Fixture status/minute and score rows are updated.
7. Leaderboard cache invalidates if any scores changed.

Admins can trigger the same sync through `POST /api/admin/scores/sync`.

### 6.4 Leaderboard Calculation

1. `GET /api/leaderboard/` calls `calculate_leaderboard()`.
2. All active users are loaded.
3. For each user, `calculate_user_points()` computes match, advancement, and bonus points.
4. Entries are sorted by total points, then exact scores.
5. Positions are assigned with tie handling.
6. Result is cached for 30 seconds per phase filter.

### 6.5 Public Prediction Visibility

Blind-pool rules are enforced on the backend:

- `GET /api/users/{user_id}/predictions` skips match predictions for fixtures that are not locked and not finished.
- `GET /api/predictions/matches/{fixture_id}/community` returns 403 until the fixture is locked or finished.
- `GET /api/predictions/agreements` returns aggregate counts only, relative to the current user's own pick, so it does not expose individual pre-lock picks.

## 7. Database And Migrations

Alembic owns schema creation.

Current migration files include:

- `f06b6a2077d3_initial_schema.py`
- `2c1b8f3e9a01_add_paid_column_to_users.py`
- `3d4f8a91c205_add_leaderboard_snapshots.py`
- `4e5f7a2b8c11_add_bonus_tables.py`

When adding a model field or table:

1. Edit the SQLModel model under `backend/app/models`.
2. Import the model in `backend/app/models/__init__.py` if needed.
3. Generate an Alembic migration.
4. Review the migration by hand.
5. Restart backend or run migrations.

## 8. External Data

Football-Data.org is the active external integration.

Functional usage:

- Fixture seeding/sync: `backend/app/services/fixture_sync.py`
- Live scores: `backend/app/services/external_scores.py`
- HTTP client: `backend/app/services/external/football_data.py`
- Cached sample data: `backend/data/wc2026_fixtures.json`
- Probe scripts/data: `backend/scripts/probe_football_data.py`, `backend/data/probe`

The score provider abstraction is intentionally small, so another provider can be added later by implementing `ScoreProviderBase`.

## 9. Tests And Coverage Orientation

Backend tests cover:

- scoring config and scoring strategies
- locking rules
- standings and tiebreakers
- third-place mapping
- fixture sync
- fixture score serialization
- Football-Data status mapping
- external score conversion
- live score sync window detection
- community prediction schemas and blind-pool logic
- public user prediction/profile schemas and filtering

Frontend tests cover:

- bracket resolver
- third-place mapping JSON structure
- standings and tie warnings
- widget fallbacks (deterministic stub data for backend-pending widgets)
- sparkline path generation

Common commands:

- Backend: `docker-compose exec backend pytest tests/ -v`
- Frontend checks: `cd frontend && npm run check`
- Frontend tests: `docker-compose exec frontend-dev npx vitest run`

## 10. Current Extension Points

### Add A New Backend Feature

Typical path:

1. Add or update models in `backend/app/models`.
2. Add schemas in `backend/app/schemas`.
3. Add business logic in `backend/app/services`.
4. Add API routes in `backend/app/api`.
5. Include the router if it is a new module.
6. Add tests.
7. Generate and review migrations if schema changed.
8. Add frontend API functions and store state.
9. Wire UI into the relevant route/component.

### Add A New Scoring Rule

Look at `backend/app/services/scoring.py`.

1. Add a scoring strategy class if the rule changes match scoring.
2. Register it in `SCORING_STRATEGIES`.
3. Add config keys to `config/worldcup2026.yml`.
4. Update docs and tests.
5. Confirm `PointBreakdown` still exposes everything the frontend needs.

### Add A New Dashboard Widget

Good pattern:

1. Add a backend service if the data is derived.
2. Add an API endpoint with a small response model.
3. Add a frontend API function.
4. Load it independently in the dashboard.
5. Use a deterministic stub fallback only if backend support is intentionally pending.
6. Add a test for any pure utility logic.

### Add A New Prediction Type

Important questions:

- Does it lock with a fixture, Phase I, or Phase II?
- Does it need blind-pool visibility rules?
- Does it belong to `MatchPrediction`, `TeamPrediction`, `BonusPrediction`, or a new table?
- Does scoring need to be phase-separated?
- Does the leaderboard breakdown need a new field?
- Does the frontend need localStorage draft persistence?

## 11. Functional Gotchas To Watch

- Datetimes are a hard invariant. Every stored or compared datetime must be timezone-aware UTC.
- The API returns `FixtureRead.time_until_lock` in seconds. Frontend logic should treat it as seconds, not milliseconds.
- The prediction wizard caps scores at 15 in the browser, while the backend prediction schemas currently accept values up to 20. If the 15-goal cap must be a security/data rule, enforce it on the backend too.
- Stage naming: RESOLVED in v2.161.0. `TeamPrediction.stage` values are stored SINGULAR (`quarter_final`, `semi_final`), matching scoring keys and `Fixture.stage`; plural spellings survive only as `BracketPrediction` API field names. The write path normalizes legacy plural payloads via `models.prediction.normalize_stage()`, and migration `b3c4d5e6f7a8` converted existing rows.
- `PUT /api/predictions/bracket` saves to the current backend phase, not the phase query parameter used by reads.
- Bracket lock enforcement is mainly frontend-driven in the current `PUT /api/predictions/bracket` path. If locked bracket integrity matters for a feature, add/verify backend lock checks before relying on UI state.
- Leaderboard values are derived and cached. Any score or bonus-answer write should invalidate the leaderboard cache.
- Bonus question IDs are durable keys. Renaming an ID in YAML can orphan existing user picks.
- Public prediction views must preserve blind-pool rules.
- Fixture sync never deletes database-only fixtures. It upserts by external ID and reports `db_only_count`.
- Flag swatches are stylized placeholders (2/3-stripe gradients driven by `lib/utils/teamCodes.ts`), not real national flags.
- Some dashboard/leaderboard widgets still intentionally fall back to deterministic stubs (`lib/utils/widgetFallbacks.ts`) while real backend history accumulates or endpoints are unavailable.

## 12. Quick File Map

### Backend

| Area | Files |
| --- | --- |
| App startup | `backend/app/main.py`, `backend/app/database.py` |
| Settings/config | `backend/app/config.py`, `config/worldcup2026.yml` |
| Auth | `backend/app/api/auth.py`, `backend/app/dependencies.py`, `backend/app/models/user.py` |
| Competition phase | `backend/app/api/competition.py`, `backend/app/services/locking.py`, `backend/app/models/competition.py` |
| Fixtures | `backend/app/api/fixtures.py`, `backend/app/models/fixture.py`, `backend/app/services/fixture_sync.py` |
| Predictions | `backend/app/api/predictions.py`, `backend/app/models/prediction.py`, `backend/app/services/bracket_exposure.py` |
| Bonus | `backend/app/models/bonus.py`, `backend/app/services/bonus.py`, `backend/app/api/admin.py`, `backend/app/api/predictions.py` |
| Scores | `backend/app/api/scores.py`, `backend/app/models/score.py`, `backend/app/services/score_sync.py` |
| Leaderboard | `backend/app/api/leaderboard.py`, `backend/app/services/leaderboard.py`, `backend/app/services/scoring.py` |
| Profiles | `backend/app/api/users.py`, `backend/app/services/profile.py` |
| External data | `backend/app/services/external/football_data.py`, `backend/app/services/external_scores.py` |

### Frontend

| Area | Files |
| --- | --- |
| App shell | `frontend/src/routes/+layout.svelte`, `frontend/src/app.css` |
| API client | `frontend/src/lib/api/client.ts`, `frontend/src/lib/api/*.ts` |
| Stores | `frontend/src/lib/stores/*.ts` |
| Types | `frontend/src/lib/types/index.ts` |
| Dashboard | `frontend/src/routes/+page.svelte`, `frontend/src/lib/utils/widgetFallbacks.ts` |
| Prediction wizard | `frontend/src/routes/predictions/+page.svelte`, `frontend/src/lib/utils/standings.ts`, `frontend/src/lib/utils/bracketResolver.ts` |
| Bracket UI | `frontend/src/lib/components/bracket/KnockoutBracket.svelte`, `BracketMatch.svelte` |
| Leaderboard | `frontend/src/routes/leaderboard/+page.svelte` |
| Results | `frontend/src/routes/results/+page.svelte`, `frontend/src/lib/utils/predictionResult.ts` |
| Profiles | `frontend/src/routes/profile/+page.svelte`, `frontend/src/routes/profile/[userId]/+page.svelte` |
| Admin | `frontend/src/routes/admin/+page.svelte`, `frontend/src/lib/api/admin.ts` |
| Global styles | `frontend/src/app.css`, `frontend/tailwind.config.js` |

## 13. Suggested Reading Order For New Enhancements

1. Read `config/worldcup2026.yml` to understand tournament rules and scoring knobs.
2. Read the route page that owns the feature in `frontend/src/routes`.
3. Read the related store in `frontend/src/lib/stores`.
4. Read the matching frontend API file in `frontend/src/lib/api`.
5. Read the backend router under `backend/app/api`.
6. Read the service layer under `backend/app/services`.
7. Check models and schemas for persistence/API shape.
8. Check tests that cover the same domain before making changes.

This order keeps you close to the user-facing workflow while still landing on the backend invariants that protect prediction integrity.
