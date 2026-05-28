# Prediction Entry Feature — Claude Code Implementation Brief
**predictorv2 fork | Updated execution brief with confirmed product decisions**

---

## HOW TO USE THIS DOCUMENT

This brief is structured as sequenced implementation tasks (A → F).
Claude Code should work through one task at a time, stop after each task, and wait for approval before proceeding.
Do not attempt the whole feature in one pass.

Before starting any task:
1. Read the full codebase
2. Read `CLAUDE.md`
3. Review this document fully
4. Confirm the scope of the current task before writing code

---

## CONFIRMED PRODUCT DECISIONS

These are no longer open questions. Treat them as hard requirements.

| # | Decision | Confirmed answer |
|---|----------|------------------|
| 1 | Default competition mode | Multi-entry mode from the beginning |
| 2 | Max entries per user | 5 |
| 3 | Payment model | Per entry |
| 4 | Bonus questions block `ready`? | Only if admin marks them as required |
| 5 | Delete vs withdraw | Withdraw only; keep record for audit |
| 6 | Reopen submitted entry? | Yes, by explicit audited action, but only before competition lock / competition start |
| 7 | Disable locked entries | Keep `locked` terminal; use `is_disabled` overlay to exclude |
| 8 | Dashboard default | Show KPIs for the selected active entry |
| 9 | Visibility of other entries | Before lock: users see only their own entries. After competition starts/locks: all participants can see all eligible competing entries |
| 10 | Duplicate entry flow | Include in first release |
| 11 | Duplicate submission rule | A user must not be allowed to submit or finalise two eligible entries with identical predictions |

---

## GLOBAL CONSTRAINTS

- **Greenfield**: there is no production data to preserve. Migrations can be destructive. No backfill logic is required.
- **UTC only**: use `utc_now()` from `app.models._datetime`. Never use `datetime.utcnow()`.
- **State machine enforced in backend**: frontend must not be the source of truth.
- **Blind pool / visibility enforced in API layer**: do not rely on frontend hiding.
- **Scoring values and labels** come only from the active scoring scheme; never hardcode.
- **TypeScript**: no `any` types. Add explicit interfaces under `/lib/types`.
- **Tests required** for all new backend logic, especially state transitions, duplicate checks, scoring, and visibility.
- **Mobile-first**: verify all UI at 375px viewport.
- **Admin actions** must require admin role checks and be auditable.

---

## FEATURE SUMMARY

Implement a new multi-entry competition model where:
- One user can own up to 5 prediction entries
- Each entry competes independently on the leaderboard
- Payment is tracked per entry
- Visibility of entries follows the blind-pool rule
- Entry status is phase-scoped, so the same entry can be locked for Phase I and still open for Phase II
- Users can duplicate entries, but cannot submit two eligible entries that are prediction-identical

The system must still support a future single-entry configuration, but this release should be built and tested with multi-entry mode as the default operating mode.

---

## CORE DOMAIN MODEL

### Competition settings

Add or confirm these competition-level settings:

| Field | Type | Default / required behaviour |
|------|------|-------------------------------|
| `multiple_entries_enabled` | bool | true for this release |
| `max_entries_per_user` | int | 5 |
| `auto_create_first_entry` | bool | true |
| `allow_duplicate_from_existing` | bool | true |
| `allow_user_rename` | bool | true |
| `allow_user_withdrawal` | bool | true |
| `require_ready_before_submit` | bool | true |
| `payment_mode` | enum | `per_entry` |
| `block_unpaid_entry_submission` | bool | configurable by admin |
| `show_entry_reference_publicly` | bool | configurable by admin |

### PredictionEntry

Each `PredictionEntry` is an independent competition unit.

Recommended fields:
- `id`
- `competition_id`
- `user_id`
- `reference` — immutable backend-generated code such as `WC26-000001`
- `display_name`
- `entry_number`
- `paid`
- `prize_eligible`
- `is_disabled`
- `disabled_reason`
- `disabled_at`
- `disabled_by_user_id`
- `withdrawn_at`
- `withdrawn_reason`
- `created_at`
- `updated_at`

Constraints:
- Unique `(competition_id, reference)`
- Unique `(competition_id, user_id, entry_number)`

### PredictionEntryPhase

Use phase-scoped lifecycle records.

Each entry has one phase record per prediction phase.

Fields:
- `id`
- `entry_id`
- `phase`
- `status` → `draft`, `ready`, `submitted`, `locked`, `withdrawn`, `disabled`
- `ready_at`
- `submitted_at`
- `locked_at`
- `status_reason`
- `created_at`
- `updated_at`

Constraint:
- Unique `(entry_id, phase)`

### Prediction ownership

All prediction rows must belong to `entry_id`, not directly to `user_id`.

Apply to:
- `match_predictions`
- `team_predictions`
- `bonus_predictions`

Use entry-scoped uniqueness rules.

---

## KEY BUSINESS RULES

### 1. Multi-entry mode
- Multi-entry is enabled from day one.
- A user can have up to 5 entries.
- Entry creation beyond the limit must be rejected in backend.

### 2. Payment
- Payment is tracked per entry.
- If `block_unpaid_entry_submission` is enabled, an unpaid entry cannot be submitted.
- Prize eligibility should also resolve at entry level.

### 3. Ready / submit lifecycle
- A phase becomes `ready` only when all required predictions for that phase are complete.
- Bonus questions only block readiness if admin marked them as required.
- Submission is explicit.
- Reopen is allowed only before competition lock and must be audited.

### 4. Withdrawal
- Users can withdraw their own non-locked entries if allowed by config.
- Withdraw is whole-entry, not phase-only.
- No hard delete. Keep record for audit.

### 5. Disabled overlay
- Admin can disable an entry using `is_disabled`.
- Do not overwrite `locked` status for already locked phases.
- Disabled entries are excluded from normal competition and prize views.

### 6. Duplicate entry detection
- Duplicate-from-existing is allowed in first release.
- However, before an entry can move to `ready` or `submitted` (final checkpoint to be chosen in implementation plan), backend must check whether the prediction set is identical to another of that user's eligible entries.
- A user must not be allowed to submit two eligible entries that are exact duplicates.
- The API must return a clear validation error naming the conflicting entry reference.

Recommended implementation:
- Perform duplicate validation at least on `submit`
- Optionally also run it on `ready` for earlier feedback
- Comparison must include all relevant predictions for the phase: match, bracket/team, and required bonus predictions where applicable

### 7. Visibility rule
- Before competition lock/start: a participant can only see their own entries.
- After competition lock/start: all participants can see all eligible competing entries, including their own and others'.
- Eligible competing entries means entries that are not withdrawn and not disabled, and that have reached the appropriate submitted/locked competition state.
- Visibility enforcement must happen in backend/API layer.

### 8. Dashboard rule
- Dashboard KPIs reflect the currently selected entry.
- Do not aggregate by default across all entries.

---

## STATE MACHINE

Use these statuses for `PredictionEntryPhase`:
- `draft`
- `ready`
- `submitted`
- `locked`
- `withdrawn`
- `disabled`

Recommended transitions:

| From | To | Allowed? | Notes |
|------|----|----------|-------|
| none | draft | yes | on create |
| draft | ready | yes | validation must pass |
| ready | draft | yes | explicit edit action |
| ready | submitted | yes | explicit submit |
| submitted | draft | yes | reopen, only before competition lock |
| submitted | locked | yes | on phase lock |
| draft/ready/submitted | withdrawn | yes | whole-entry withdrawal before lock |
| draft/ready/submitted | disabled | yes | admin/system action |
| locked | disabled | no status transition | use `is_disabled` overlay instead |

Backend must enforce:
- ownership
- active competition
- phase not locked
- fixture not locked
- entry not withdrawn
- entry not disabled
- transition allowed from current state
- payment rule where configured
- duplicate-submission rule

---

## API DIRECTION

Use entry-scoped APIs as the primary model.
Do not keep user-scoped prediction APIs as the long-term shape.

### Entry endpoints
- `GET /api/entries`
- `POST /api/entries`
- `GET /api/entries/{entry_id}`
- `PATCH /api/entries/{entry_id}`
- `POST /api/entries/{entry_id}/duplicate`
- `POST /api/entries/{entry_id}/phases/{phase}/ready`
- `POST /api/entries/{entry_id}/phases/{phase}/submit`
- `POST /api/entries/{entry_id}/phases/{phase}/reopen`
- `POST /api/entries/{entry_id}/withdraw`

### Prediction endpoints
- `GET /api/entries/{entry_id}/predictions/matches`
- `PUT /api/entries/{entry_id}/predictions/matches/{fixture_id}`
- `POST /api/entries/{entry_id}/predictions/matches/batch`
- `GET /api/entries/{entry_id}/predictions/bracket`
- `PUT /api/entries/{entry_id}/predictions/bracket`
- `GET /api/entries/{entry_id}/predictions/bonus`
- `POST /api/entries/{entry_id}/predictions/bonus`

### Leaderboard response
Leaderboard rows represent entries, not users.
Response should include:
- `entry_id`
- `entry_reference`
- `entry_name`
- `user_id`
- `user_name`
- `position`
- `total_points`
- `breakdown`
- `correct_outcomes`
- `exact_scores`
- `movement`

### Admin endpoints
- `GET /api/admin/competition/entry-settings`
- `PATCH /api/admin/competition/entry-settings`
- `GET /api/admin/entries`
- `POST /api/admin/entries/{entry_id}/disable`
- `POST /api/admin/entries/{entry_id}/enable`
- `PATCH /api/admin/entries/{entry_id}/paid`
- `PATCH /api/admin/entries/{entry_id}/prize-eligible`
- `GET /api/admin/entries/{entry_id}/events`

---

## FRONTEND DIRECTION

### Prediction flow
- Add entry selector to predictions flow
- Show current entry name, reference, and phase status
- Allow create, duplicate, rename, ready, submit, reopen, withdraw based on state/config
- Persist unsaved drafts by `userId + entryId`

### Single selected entry context
- Dashboard and prediction screens should operate on the selected active entry
- Persist active entry in localStorage per user + competition

### Leaderboard
- Multi-entry mode: one row per entry
- Show entry display name, owner, and optional reference depending on config
- Mark current user's entries clearly

### Profile / visibility
- Before competition starts/locks: users only see their own entries
- After lock/start: all participants can see all eligible competing entries
- Public profile and community prediction views must follow this same rule

### Admin UI
Add:
- competition entry settings panel
- entries list with filters
- disable/enable actions
- paid/prize eligible toggles
- entry event audit log

---

## TASK BREAKDOWN FOR CLAUDE CODE

Work sequentially and stop after each task for approval.

### Task A — Models and schema
Implement:
- competition entry settings
- `PredictionEntry`
- `PredictionEntryPhase`
- `PredictionEntryEvent`
- `entry_id` ownership for prediction tables
- entry-based leaderboard snapshots
- Alembic migration (no backfill)
- tests for schema constraints and ownership

Stop and present:
- new models
- migration plan
- key constraints

### Task B — Entry service and API
Implement:
- `backend/app/services/entries.py`
- `backend/app/schemas/entry.py`
- `backend/app/api/entries.py`
- create/list/get/rename/duplicate/ready/submit/reopen/withdraw
- admin entry settings and admin entry actions
- audit events
- duplicate-submission validation

Stop and present:
- service interface
- route list
- validation rules

### Task C — Entry-scoped predictions
Implement:
- entry-nested match/bracket/bonus prediction APIs
- authorization through entry ownership
- phase + fixture lock checks on writes
- tests proving same user can make different picks on different entries

Stop and present:
- updated prediction route map
- lock enforcement points

### Task D — Entry-based scoring and leaderboard
Implement:
- `calculate_entry_points(entry_id)`
- entry-based leaderboard ranking
- entry-based snapshots
- exclude withdrawn/disabled/non-eligible entries from normal leaderboard
- tests for multiple entries by same user ranking independently

Stop and present:
- scoring service changes
- leaderboard response contract

### Task E — Frontend entry support
Implement:
- `frontend/src/lib/api/entries.ts`
- `frontend/src/lib/stores/entries.ts`
- entry selector/create/duplicate/rename UI
- entry-scoped prediction fetch/save
- localStorage scoping by entry
- selected-entry dashboard behavior

Stop and present:
- store design
- updated screens list

### Task F — Admin, profile, and visibility views
Implement:
- admin entry management UI
- leaderboard updates for entries
- dashboard entry panels
- profile/public visibility rules
- blind-pool enforcement reflected correctly in UI states

Stop and present:
- visibility matrix
- admin screens changed

---

## REQUIRED TEST COVERAGE

### Backend
Add tests for:
- multi-entry limit enforcement
- per-entry payment enforcement
- bonus questions required only when configured
- reopen only before competition lock
- withdraw only, no hard delete
- duplicate submission blocked for identical eligible entries
- entry references unique
- cross-user access forbidden
- locked phases reject edits
- disabled overlay excludes entry without mutating locked status
- leaderboard returns one row per eligible entry
- visibility rules before and after competition lock

### Frontend
Add tests for:
- entry selector behaviour
- selected entry persistence
- create/duplicate/rename controls
- hidden vs visible entries based on competition lock
- leaderboard showing multiple rows for same user
- no `any` types

---

## ACCEPTANCE CRITERIA

The feature is complete when all of the following are true:

1. A user can create up to 5 entries.
2. Each entry has its own reference, name, predictions, payment state, and lifecycle.
3. The same user can submit multiple different entries.
4. The same user cannot submit two eligible entries that are prediction-identical.
5. Users can duplicate an entry into a new draft.
6. Users can withdraw entries but not delete them.
7. Users can reopen submitted entries only before competition lock.
8. Locked entries remain locked; admin exclusion uses `is_disabled` overlay.
9. Leaderboard ranks entries, not users.
10. Dashboard defaults to the selected active entry.
11. Before competition lock, users see only their own entries.
12. After competition lock/start, users can see all eligible competing entries.
13. Bonus questions affect readiness only when marked required by admin.
14. Payment is enforced per entry where configured.
15. All new backend logic is covered by tests.
16. No TypeScript `any` types are introduced.
