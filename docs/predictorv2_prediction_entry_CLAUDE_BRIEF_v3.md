# Prediction Entry Feature — Claude Code Implementation Brief
**predictorv2 fork | v3 — confirmed product decisions baked in**

---

## HOW TO USE THIS DOCUMENT

Work through tasks A → F in sequence.
Stop after each task and wait for approval before proceeding.
Do not implement the full feature in one pass.

Before starting any task:
1. Read the full codebase
2. Read `CLAUDE.md`
3. Review this document fully
4. Confirm task scope with the user before writing code

---

## CONFIRMED PRODUCT DECISIONS

Hard requirements. Do not treat these as configurable unless stated.

| # | Decision | Answer |
|---|----------|--------|
| 1 | Default max entries per user | 5 — admin can change to any number ≥ 1 |
| 2 | Minimum entries per user | 1 — a user must always have at least one entry |
| 3 | Single-entry mode | Achieved by setting max_entries_per_user = 1; no separate flag |
| 4 | Entry status scope default | Whole-competition (not phase-scoped) |
| 5 | Phase-scoped entry status | Optional — admin enables it in competition settings |
| 6 | Phase II opening | Admin manually triggers globally; does not auto-open |
| 7 | Payment model | Per entry |
| 8 | Bonus questions block ready? | Only if admin marks them as required |
| 9 | Delete vs withdraw | Withdraw only — keep record for audit |
| 10 | Reopen submitted entry? | Yes — explicit audited action, only before competition lock |
| 11 | Disable locked entries | Use `is_disabled` overlay; keep `locked` terminal |
| 12 | Dashboard default | KPIs for the selected active entry |
| 13 | Visibility before lock | Users see only their own entries |
| 14 | Visibility after lock/start | All participants see all eligible competing entries |
| 15 | Duplicate entry flow | Included in first release |
| 16 | Duplicate submission rule | Backend blocks submitting two eligible entries with identical predictions |

---

## GLOBAL CONSTRAINTS

- **Greenfield**: no production data; migrations can be destructive; no backfill needed
- **UTC only**: use `utc_now()` from `app.models._datetime` — never `datetime.utcnow()`
- **State transitions**: enforced in backend only — frontend must not be the source of truth
- **Blind pool / visibility**: enforced in API layer only — do not rely on frontend filtering
- **Scoring values and labels**: always come from the active scoring scheme — never hardcode
- **TypeScript**: no `any` types — define all interfaces under `/lib/types`
- **Tests**: all new backend logic must have pytest tests — especially transitions, duplicates, visibility, and scoring
- **Mobile-first**: verify all UI at 375px viewport
- **Admin actions**: require role checks in API layer and must be logged with timestamp and actor user ID

---

## COMPETITION ENTRY SETTINGS

All of the following must be configurable from the admin panel.
Store effective values on the competition/tournament record in the database.
Use YAML config only for bootstrap defaults.

| Setting | Type | Default | Admin rules |
|---------|------|---------|-------------|
| `max_entries_per_user` | int | 5 | Min 1; no upper limit enforced by system |
| `auto_create_first_entry` | bool | true | Auto-creates first draft on first prediction visit |
| `allow_duplicate_from_existing` | bool | true | Copy existing entry to new draft |
| `allow_user_rename` | bool | true | User can rename before lock |
| `allow_user_withdrawal` | bool | true | User can withdraw before lock |
| `require_ready_before_submit` | bool | true | Must pass validation before submitting |
| `payment_mode` | enum | per_entry | `per_user` or `per_entry` |
| `block_unpaid_entry_submission` | bool | false | Block submission when entry unpaid |
| `show_entry_reference_publicly` | bool | false | Show reference on public leaderboard |
| `phase_scoped_status_enabled` | bool | false | Enable phase-level lifecycle (see below) |
| `bonus_questions_required_for_ready` | bool | false | Block ready until bonus questions answered |

Validation rules for admin changes:
- `max_entries_per_user` cannot be reduced below the highest current active entry count per user unless existing entries are explicitly grandfathered
- Disabling `allow_duplicate_from_existing` does not affect already-created entries
- All config changes are audited with timestamp and admin user ID

---

## ENTRY STATUS SCOPE — KEY ARCHITECTURAL DECISION

The system supports two status scope modes, controlled by `phase_scoped_status_enabled`.

### Whole-competition mode (default, `phase_scoped_status_enabled = false`)
- `PredictionEntry` has a single status that covers the whole competition
- The lifecycle is: `draft → ready → submitted → locked`
- `locked` = entry is frozen for the entire competition
- `PredictionEntryPhase` records are still used internally for per-phase prediction tracking, but status management is entry-level only

### Phase-scoped mode (`phase_scoped_status_enabled = true`)
- Each entry has a separate status per phase via `PredictionEntryPhase`
- Phase I and Phase II each have their own lifecycle: `draft → ready → submitted → locked`
- When Phase I locks, Phase II status is NOT opened automatically
- Admin must explicitly trigger the **"Open Phase II"** global action
- This action sets all eligible Phase II phase records to `draft`
- Entries that are withdrawn or disabled are excluded from the Phase II open action
- The action is audited with timestamp and admin user ID

Design note:
- Always create `PredictionEntryPhase` records internally in both modes
- In whole-competition mode, use a single representative phase status for UX
- This ensures the schema can support phase-scoped mode without migration when enabled

---

## DATA MODELS

### PredictionEntry (table: `prediction_entries`)

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | Server-generated |
| `competition_id` | UUID FK | → competitions.id |
| `user_id` | UUID FK | Owner |
| `reference` | string | Immutable, unique per competition. Format: `WC26-000001` |
| `display_name` | string | User-editable label |
| `entry_number` | int | Per-user sequence (1, 2, 3...) |
| `paid` | bool | Entry-level paid flag |
| `prize_eligible` | bool | Defaults true when paid (if payment required) |
| `is_disabled` | bool | Admin overlay — does not change phase status |
| `disabled_reason` | string nullable | Required when disabled |
| `disabled_at` | datetime nullable | UTC aware |
| `disabled_by_user_id` | UUID nullable | Admin who disabled |
| `withdrawn_at` | datetime nullable | Whole-entry withdrawal |
| `withdrawn_reason` | string nullable | User/admin reason |
| `created_at` | datetime | UTC aware |
| `updated_at` | datetime | UTC aware |

Constraints:
- Unique `(competition_id, reference)`
- Unique `(competition_id, user_id, entry_number)`
- Index `(competition_id, user_id)`
- Index `(competition_id, is_disabled)`

Reference generation:
- Backend-generated, immutable after creation
- Format: `WC26-000001` (competition code + zero-padded global sequence)
- Do not use user initials for uniqueness

### PredictionEntryPhase (table: `prediction_entry_phases`)

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | Server-generated |
| `entry_id` | UUID FK | → prediction_entries.id |
| `phase` | enum | `phase_1` or `phase_2` |
| `status` | enum | `draft`, `ready`, `submitted`, `locked`, `withdrawn`, `disabled` |
| `ready_at` | datetime nullable | Set on draft → ready |
| `submitted_at` | datetime nullable | Set on ready → submitted |
| `locked_at` | datetime nullable | Set on submitted → locked |
| `status_reason` | string nullable | Reason for system/admin transitions |
| `created_at` | datetime | UTC aware |
| `updated_at` | datetime | UTC aware |

Constraints:
- Unique `(entry_id, phase)`
- Index `(phase, status)`

### PredictionEntryEvent (table: `prediction_entry_events`) — audit trail

| Field | Type |
|-------|------|
| `id` | UUID PK |
| `entry_id` | UUID FK |
| `phase` | enum nullable |
| `from_status` | string |
| `to_status` | string |
| `actor_user_id` | UUID FK |
| `actor_role` | enum: `user`, `admin`, `system` |
| `reason` | string nullable |
| `created_at` | datetime UTC |

### Prediction table ownership

All prediction rows must be owned by `entry_id`, not `user_id`.

| Table | New uniqueness constraint |
|-------|--------------------------|
| `match_predictions` | `(entry_id, fixture_id)` |
| `team_predictions` | `(entry_id, phase, team, stage)` |
| `bonus_predictions` | `(entry_id, question_id)` |

Do not store `user_id` on prediction rows. Resolve the owning user through `PredictionEntry.user_id`.

### Leaderboard snapshots

Change uniqueness from `(user_id, captured_date)` to `(entry_id, captured_date)`.

---

## STATE MACHINE

### Status values

| Status | Meaning |
|--------|---------|
| `draft` | Editable; may be incomplete; not official |
| `ready` | Validated as complete; not yet official |
| `submitted` | Official and competition-eligible before lock |
| `locked` | Terminal for edits — predictions cannot be changed |
| `withdrawn` | Excluded from competition; read-only |
| `disabled` | Admin/system excluded; read-only |

`locked` is always terminal for prediction edits.
For locked entries excluded by admin, use `is_disabled` overlay. Do not change status to `disabled`.

### Allowed transitions

| From | To | Actor | Condition |
|------|----|-------|-----------|
| — | draft | User/Admin/System | Entry created |
| draft | ready | User | Validation passes; phase not locked |
| ready | draft | User | Phase not locked; explicit edit action |
| ready | submitted | User | Phase not locked; payment satisfied if required; not duplicate of another eligible entry |
| submitted | draft | User | Competition not locked; explicit reopen action; audited |
| submitted | locked | System/Admin | Phase lock event |
| draft/ready/submitted | withdrawn | User/Admin | Competition not locked; whole-entry |
| draft/ready/submitted | disabled | Admin/System | Admin reason or unsubmitted at lock |
| locked | — | — | Terminal; use `is_disabled` overlay for exclusion |
| withdrawn | draft | Admin | Exceptional recovery before lock; audited |
| disabled | draft | Admin | Exceptional recovery before lock; audited |

### Backend validation on every state transition

- Entry belongs to requesting user (unless admin)
- Entry belongs to active competition
- Phase deadline not passed
- Fixture not individually locked (for prediction writes)
- Entry not withdrawn (`withdrawn_at` is null)
- Entry `is_disabled` is false
- Phase status not `locked`
- Transition is in the allowed transitions table
- Payment rule satisfied where configured
- Duplicate-submission rule satisfied on submit

---

## DUPLICATE SUBMISSION RULE

Before an entry moves to `submitted`, the backend must check:
- Does this user have another eligible entry (submitted or locked) for the same competition and phase with an identical set of predictions?
- Identical means: same predicted scores for all match predictions, same bracket/team predictions, same bonus picks (for required bonus questions)
- If a duplicate is detected, return a validation error that names the conflicting entry reference
- Run this check at minimum on `submit`
- Optionally also run it on `ready` for earlier feedback (recommended)

---

## API SPECIFICATION

### User entry endpoints (`backend/app/api/entries.py`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/entries` | List current user's entries |
| POST | `/api/entries` | Create new draft entry |
| GET | `/api/entries/{entry_id}` | Read one owned entry |
| PATCH | `/api/entries/{entry_id}` | Rename display name |
| POST | `/api/entries/{entry_id}/duplicate` | Duplicate into new draft |
| POST | `/api/entries/{entry_id}/phases/{phase}/ready` | Mark phase ready |
| POST | `/api/entries/{entry_id}/phases/{phase}/submit` | Submit phase |
| POST | `/api/entries/{entry_id}/phases/{phase}/reopen` | Reopen before competition lock |
| POST | `/api/entries/{entry_id}/withdraw` | Withdraw whole entry |

### Prediction endpoints (nested under entry)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/entries/{entry_id}/predictions/matches` | Get match predictions |
| PUT | `/api/entries/{entry_id}/predictions/matches/{fixture_id}` | Upsert one match prediction |
| POST | `/api/entries/{entry_id}/predictions/matches/batch` | Batch upsert |
| GET | `/api/entries/{entry_id}/predictions/bracket` | Get bracket predictions |
| PUT | `/api/entries/{entry_id}/predictions/bracket` | Save bracket predictions |
| GET | `/api/entries/{entry_id}/predictions/bonus` | Get bonus picks |
| POST | `/api/entries/{entry_id}/predictions/bonus` | Save bonus picks |

Do not retain user-scoped `/api/predictions/...` endpoints.

### Leaderboard response shape (per row)

```json
{
  "entry_id": "uuid",
  "entry_reference": "WC26-000001",
  "entry_name": "Vinay Main",
  "user_id": "uuid",
  "user_name": "Vinay",
  "position": 1,
  "total_points": 123,
  "breakdown": {},
  "correct_outcomes": 12,
  "exact_scores": 3,
  "movement": 0
}
```

### Admin endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/admin/competition/entry-settings` | Read entry config |
| PATCH | `/api/admin/competition/entry-settings` | Update entry config with validation |
| POST | `/api/admin/competition/phase2/open` | Globally open Phase II for all eligible entries |
| GET | `/api/admin/entries` | List/search all entries |
| POST | `/api/admin/entries/{entry_id}/disable` | Disable with reason |
| POST | `/api/admin/entries/{entry_id}/enable` | Re-enable if allowed |
| PATCH | `/api/admin/entries/{entry_id}/paid` | Toggle paid status |
| PATCH | `/api/admin/entries/{entry_id}/prize-eligible` | Set prize eligibility |
| GET | `/api/admin/entries/{entry_id}/events` | Audit log |

---

## FRONTEND SPECIFICATION

### Entry store (`frontend/src/lib/stores/entries.ts`)
- Load competition entry settings on app init
- Load current user's entries
- Track and persist active entry ID (localStorage by user + competition)
- Expose: `activeEntry`, `activeEntryPhaseStatus`, `submittedEntries`, `editableEntries`

### Prediction store (`predictions.ts`)
- All fetch/save calls scoped to active `entry_id`
- localStorage draft keys: `predictor_unsaved_{userId}_{entryId}_{type}`

### Prediction wizard UI
- Entry selector at top showing current entry name + reference + status badge
- Create, duplicate, rename, ready, submit, reopen, withdraw actions conditional on status and config
- Status UX:

| Status | Behaviour |
|--------|-----------|
| draft | Editable; save draft; mark ready |
| ready | Read-only summary; submit or edit |
| submitted | Read-only; reopen only before lock |
| locked | Read-only |
| withdrawn | Read-only; excluded |
| disabled | Read-only; show admin reason |

### Leaderboard UI
- One row per entry
- Primary: entry display name
- Secondary: owner name + optional reference
- Mark current user's entries with `YOU`

### Dashboard
- Entry selector
- KPIs for selected entry only

### Visibility
- Before lock: user sees own entries only
- After lock/start: all eligible entries visible to all participants

### Admin panel additions
- Competition entry settings panel (all flags in the config table)
- Phase II open action with confirmation dialog
- Entry list with filters: user, reference, status, paid, disabled
- Per-entry: predictions view, paid toggle, prize-eligible toggle, disable/enable with reason, audit log

---

## IMPLEMENTATION TASKS

Stop after each task and wait for approval.

---

### Task A — Models and schema

```
Implement the PredictionEntry data model foundation.

Greenfield: no production data; no backfill.

Scope:
1. Add competition entry settings to Competition model (all fields in the config table above)
2. Create PredictionEntry (prediction_entries)
3. Create PredictionEntryPhase (prediction_entry_phases)
4. Create PredictionEntryEvent (prediction_entry_events)
5. Add entry_id FK to match_predictions, team_predictions, bonus_predictions
6. Remove user-scoped uniqueness from prediction tables; apply entry-scoped constraints
7. Change leaderboard_snapshots uniqueness to (entry_id, captured_date)
8. Write Alembic migration — schema only, no backfill
9. Tests for:
   - model constraints and uniqueness
   - entry ownership
   - max_entries_per_user limit enforcement
   - two entries from same user can predict different scores for same fixture

Stop and show models and migration plan before creating files.
```

---

### Task B — Entry service and API

```
Implement entry management.

Scope:
1. backend/app/services/entries.py
   create, list, get, rename, duplicate, ready, submit, reopen, withdraw
   admin disable/enable, phase II open trigger
   enforce: limits, ownership, state transitions, payment rule, duplicate-submission check
2. backend/app/schemas/entry.py
3. backend/app/api/entries.py — all user and admin endpoints above
4. Write audit events for every state transition
5. Tests for:
   - create/list/rename/ready/submit/reopen/withdraw
   - max_entries_per_user enforcement
   - duplicate submission blocked for identical eligible entries
   - reopen blocked after competition lock
   - cross-user access forbidden
   - phase II global open transitions correct entries only

Stop and show service interface and API contract before implementing.
```

---

### Task C — Entry-scoped predictions

```
Make all predictions entry-scoped.

Scope:
1. Add /api/entries/{entry_id}/predictions/... endpoints
2. Remove or replace user-scoped prediction endpoints
3. Update prediction services to read/write by entry_id
4. Enforce phase status + fixture lock + phase deadline on every write
5. Tests:
   - same user makes different picks on two entries for same fixture
   - locked phase rejects all prediction writes
   - fixture individually locked rejects write
   - cross-entry access forbidden

Stop and show updated route map before implementing.
```

---

### Task D — Entry-based scoring and leaderboard

```
Change scoring and leaderboard from user-based to entry-based.

Scope:
1. Add calculate_entry_points(entry_id) — all values from active scoring scheme
2. Update leaderboard to rank PredictionEntry rows
3. Exclude draft/ready/withdrawn/disabled entries from normal leaderboard
4. Update snapshot service to use entry_id
5. Tests:
   - same user with two entries appears as two independent leaderboard rows
   - withdrawn entries excluded
   - disabled entries excluded
   - points isolated per entry

Stop and show scoring service changes and leaderboard contract before implementing.
```

---

### Task E — Frontend entry support

```
Add frontend support for multiple prediction entries.

Scope:
1. frontend/src/lib/api/entries.ts — API client
2. frontend/src/lib/stores/entries.ts — store per spec above
3. Entry selector + create/duplicate/rename/status UI in /predictions
4. Update predictions.ts to use active entry ID for all fetch/save
5. Scope localStorage draft keys by entry ID
6. Single-entry feel when max_entries_per_user = 1 (hide multi-entry controls)
7. No any types; mobile-first 375px

Stop and show store design and updated screen list before implementing.
```

---

### Task F — Admin, leaderboard, dashboard, and profile views

```
Expose entries across admin, leaderboard, dashboard, and profile.

Scope:
1. Leaderboard UI: one row per entry; YOU marker; conditional reference display
2. Dashboard UI: entry selector; selected entry KPIs
3. Admin UI: competition entry settings panel; Phase II open button with confirmation;
   entries list with filters; per-entry actions
4. Profile/public visibility: enforce before/after lock visibility rule in API + UI state
5. All visibility decisions enforced in API layer first

Stop and show visibility matrix and admin screen list before implementing.
```

---

## REQUIRED TEST COVERAGE

### Backend (pytest)
- max_entries_per_user enforced; min 1 enforced
- per-entry payment enforced when configured
- bonus questions required only when admin-configured
- reopen blocked after competition lock
- withdraw only — no hard delete
- duplicate submission blocked for identical eligible entries; error names conflicting reference
- entry references globally unique per competition
- cross-user access forbidden on all entry and prediction endpoints
- locked phases reject all prediction writes
- is_disabled overlay excludes entry without mutating locked status
- leaderboard returns one row per eligible entry
- phase II global open transitions only eligible entries; withdraws/disables excluded
- audit events written for all state transitions
- visibility: other entries blocked before lock; all eligible visible after lock

### Frontend
- single-entry feel when max = 1
- multi-entry controls visible when max > 1
- entry selector loads and switches active entry
- prediction store scoped to active entry ID
- localStorage keys scoped by entry ID
- leaderboard shows multiple rows for same user
- status badges and action buttons match allowed transitions
- no TypeScript `any` types

---

## ACCEPTANCE CRITERIA

Done when all of the following are true:

1. Admin can configure all entry settings from the admin panel without code changes
2. max_entries_per_user defaults to 5; admin can set to any number ≥ 1
3. Setting max_entries_per_user to 1 gives a single-entry experience
4. Each entry has a unique immutable reference and user-editable display name
5. Each entry stores independent predictions for the same fixture
6. Users cannot submit two eligible entries with identical predictions
7. Users can duplicate an existing entry into a new draft
8. Withdraw only — no hard delete — audit record kept
9. Reopen is allowed only before competition lock; blocked after
10. Locked phases are immutable; admin exclusion uses is_disabled overlay
11. Phase-scoped status is off by default; admin can enable it
12. Phase II opens only when admin triggers it globally
13. Leaderboard ranks entries, not users — one row per eligible entry
14. Dashboard defaults to selected active entry KPIs
15. Before lock: users see only their own entries
16. After lock/start: all participants see all eligible competing entries
17. Bonus questions block readiness only when admin marks them required
18. All new backend logic covered by tests
19. No TypeScript any types introduced
