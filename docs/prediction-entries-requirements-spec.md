# Multiple Prediction Entries Requirements And Specification

## 1. Goal

Support an admin-configurable prediction entry mode.

When multiple entries are disabled, the competition behaves like today: one prediction entry per user, one visible leaderboard row per participant, and no user-facing entry management.

When multiple entries are enabled, one user can create and submit multiple independent competition entries.

Think of each `PredictionEntry` like a horse-racing each-way bet slip:

- It has its own reference.
- It has its own prediction set.
- It competes as its own leaderboard row.
- It can be drafted, validated, submitted, locked, withdrawn, or disabled independently of the user's other entries.

The current codebase treats a user as the leaderboard unit. This enhancement changes the internal leaderboard unit to an entry. In single-entry mode, the UI can still present the experience as one participant row per user because each user has exactly one active entry.

Greenfield assumption: there is no production data to preserve. The implementation can make entry-based prediction ownership the baseline model, update APIs in place, and avoid migration backfills or legacy compatibility wrappers.

## 2. Recommended Architecture

### 2.1 Admin-Configured Entry Mode

Entry behavior must be driven by competition-level admin settings wherever possible. This lets the same codebase run a simple one-entry pool or a multi-entry competition without forks, data migrations, or hard-coded behavior.

Use `PredictionEntry` internally in both modes:

| Mode | Admin setting | User-facing behavior | System behavior |
| --- | --- | --- | --- |
| Single-entry mode | `multiple_entries_enabled = false` | Looks like the current app: one set of predictions per user and one leaderboard row per user. | The system still stores one `PredictionEntry` per user, but prevents creating a second active entry. |
| Multi-entry mode | `multiple_entries_enabled = true` | Users can create, name, duplicate, submit, withdraw, and track multiple entries. | Leaderboards, scoring, locking, payments, and visibility operate per entry. |

Recommended settings:

```yaml
prediction_entries:
  multiple_entries_enabled: false
  max_per_user: 1
  auto_create_first_entry: true
  allow_duplicate_from_existing: false
  allow_user_rename: true
  allow_user_withdrawal: true
  require_ready_before_submit: true
  payment_mode: per_user
  block_unpaid_entry_submission: false
  show_entry_reference_publicly: false
```

Setting notes:

| Setting | Purpose |
| --- | --- |
| `multiple_entries_enabled` | Main feature flag. `false` preserves current one-entry behavior. |
| `max_per_user` | Maximum active entries per user. Forced to `1` when multiple entries are disabled. |
| `auto_create_first_entry` | Creates the user's first entry automatically on registration or first prediction visit. |
| `allow_duplicate_from_existing` | Lets users copy one of their existing entries into a new draft entry. |
| `allow_user_rename` | Lets users rename entries before lock. |
| `allow_user_withdrawal` | Lets users withdraw entries before lock. |
| `require_ready_before_submit` | Requires validation and an explicit ready state before submission. |
| `payment_mode` | `per_user` or `per_entry`, depending on how the competition is run. |
| `block_unpaid_entry_submission` | Blocks unpaid entry submission when payment is entry-level. |
| `show_entry_reference_publicly` | Controls whether leaderboard rows expose the entry reference or only display name/owner label. |

The YAML config should provide defaults for a new competition. The effective settings should live in the database on the competition/tournament record so admins can configure them from the admin UI.

Admin safety rules:

- Admins can enable multiple entries before or during setup.
- Admins can disable multiple entries only if no user has more than one non-withdrawn, non-disabled entry, or by choosing an explicit admin cleanup action.
- Admins cannot reduce `max_per_user` below the highest current active entry count unless existing entries are explicitly grandfathered.
- Config changes apply immediately to new user actions, but must not silently delete, merge, or hide existing predictions.
- Locked entries remain immutable regardless of later config changes.

### 2.2 Core Recommendation

Use `PredictionEntry` as the permanent competition identity and leaderboard row.

Because the app already has Phase I and Phase II, do not make one global `PredictionEntry.status` responsible for all prediction locking. A globally terminal `locked` state would block later Phase II predictions.

Recommended model:

- `PredictionEntry`: the user's named competition entry.
- `PredictionEntryPhase`: the lifecycle status for that entry in a specific prediction phase.
- In single-entry mode this model is still used internally, but only one active entry can exist per user.

This means the requested lifecycle:

```text
draft -> ready -> submitted -> locked
```

applies per entry per phase.

Top-level withdrawal/disable rules still apply to the whole entry. If an entry is withdrawn or disabled, all phase states become read-only and the entry is excluded from active competition views unless an admin asks to include it.

### 2.3 Why Phase-Scoped Status Matters

Current app behavior:

- Phase I predictions are made before the tournament.
- Phase II predictions can be made after group stage if the admin activates Phase II.

If `PredictionEntry.status = locked` at the Phase I deadline, a user could not later add Phase II predictions to that entry. Phase-scoped states avoid that:

| Entry | Phase I state | Phase II state |
| --- | --- | --- |
| Vinay #1 | locked | draft |
| Vinay #2 | locked | submitted |

The leaderboard still shows `Vinay #1` and `Vinay #2` as separate rows.

## 3. Terminology

| Term | Meaning |
| --- | --- |
| User | The account holder who logs in. |
| PredictionEntry | One independent competition entry owned by a user. |
| Entry reference | Immutable unique code generated by the backend, such as `WC26-000123`. |
| Entry display name | User-editable label such as `Vinay Main`, `Vinay Wildcard`, or `Entry 2`. |
| Entry phase | The lifecycle record for one entry in one prediction phase. |
| Submitted entry | An entry phase that is official and eligible for scoring when locks occur. |
| Locked entry phase | A submitted phase that can no longer be changed. |
| Withdrawn entry | A user/admin-withdrawn entry excluded from active competition. |
| Disabled entry | An admin-disabled entry excluded from active competition. |

## 4. Functional Requirements

### 4.1 Entry Creation

Entry creation is governed by the active competition entry settings.

Single-entry mode requirements:

1. A logged-in user can have only one non-withdrawn, non-disabled entry for the active competition.
2. The first entry is created automatically if `auto_create_first_entry` is enabled.
3. Entry create, duplicate, switcher, and management UI are hidden.
4. Backend create-entry endpoints reject a second active entry.
5. Leaderboards may display one row per user without showing entry labels.

Multi-entry mode requirements:

1. A logged-in user can create more than one entry for the active competition, up to `max_per_user`.
2. The backend generates a unique immutable entry reference.
3. The user can set or edit a display name while the entry is not locked, withdrawn, or disabled, if `allow_user_rename` is enabled.
4. The product should choose one of two first-entry flows:
   - create a default first entry automatically when a user first opens the prediction wizard, or
   - require the user to click "Create entry" before they can enter predictions.
5. Recommended first-release behavior: auto-create the first draft entry for convenience.

### 4.2 Entry Selection

1. In single-entry mode, prediction pages can resolve the user's only entry automatically and hide entry selection.
2. In multi-entry mode, prediction pages must clearly show which entry is being edited.
3. Users can switch between their entries when multiple entries are enabled.
4. Switching entries loads that entry's match, bracket, and bonus predictions.
5. Unsaved draft persistence must be scoped by user ID and entry ID.
6. Users should be able to duplicate an existing entry into a new draft before locks when `allow_duplicate_from_existing` is enabled. This is not mandatory for the first release, but it is a high-value workflow for multiple entries.

### 4.3 Prediction Ownership

Predictions must belong to an entry, not directly to a user.

Affected prediction types:

- Match score predictions.
- Team advancement/bracket predictions.
- Bonus question predictions.

The user is still available through `PredictionEntry.user_id`.

### 4.4 Readiness And Submission

Each entry phase has a lifecycle:

```text
draft -> ready -> submitted -> locked
```

Recommended readiness rules:

| Phase | Ready when |
| --- | --- |
| Phase I | Required group-stage fixture predictions are complete, Phase I bracket is complete, and required bonus questions are answered if bonus questions are configured as required. |
| Phase II | Required knockout fixture predictions are complete for available fixtures and the Phase II bracket is complete enough for the current rules. |

Bonus questions are currently treated as user-facing picks but not obviously mandatory. Decide whether they block readiness. Recommended first-release behavior: bonus questions do not block readiness unless config says so.

### 4.5 Submission

1. A user can submit only their own ready entry phase.
2. A submitted entry phase is eligible for scoring and leaderboard display.
3. A submitted entry phase can be reopened before lock only by moving it back to `draft`.
4. Any edit to predictions in a `ready` or `submitted` phase should either:
   - be blocked until the user explicitly reopens the phase to `draft`, or
   - automatically move the phase back to `draft`.

Recommendation: require explicit "Edit submitted entry" action. It is clearer and auditable.

### 4.6 Locking

1. A submitted phase moves to `locked` when its phase lock occurs.
2. `locked` is terminal for prediction edits.
3. Draft or ready phases that reach their phase deadline without submission should become `disabled` with reason `not_submitted_before_lock`, or remain read-only `draft/ready` but excluded from competition.

Recommendation: use `disabled` for unsubmitted phases at lock time. It makes non-competing entries explicit.

4. Individual fixture lock rules still apply. A fixture prediction cannot be edited after its fixture lock, even if the entry phase is still `draft`.
5. Phase-wide lock rules still apply:
   - Phase I locks at `Competition.phase1_deadline`.
   - Phase II bracket locks at `Competition.phase2_bracket_deadline`.
   - Fixture-level match predictions lock 5 minutes before kickoff.

### 4.7 Withdrawal

1. Users can withdraw their own draft, ready, or submitted entry phase before lock.
2. Users cannot withdraw a locked phase.
3. Admins can withdraw an entry on behalf of a user before lock.
4. Withdrawn entries are read-only.
5. Withdrawn entries are excluded from normal leaderboard views.
6. Withdrawal requires a timestamp and optional reason.

Recommended rule: withdrawal is whole-entry, not phase-only. If a user withdraws an entry, it no longer competes in any phase.

### 4.8 Disable

1. Only admins can disable an entry.
2. Disabled entries are read-only.
3. Disabled entries are excluded from normal leaderboard views and prize eligibility.
4. Disable requires a reason.
5. Admins can disable draft, ready, and submitted entries.
6. For locked entries, avoid changing `locked` to `disabled` if "locked is terminal" is important. Instead, use `admin_disabled_at` / `is_disabled` overlay fields on `PredictionEntry`.

Recommendation: model disabled as an entry-level overlay, not only as a phase state. That preserves the terminal meaning of `locked` while still allowing admins to exclude an entry.

### 4.9 Payment And Prize Eligibility

Payment and prize eligibility should support both admin-configured modes.

Recommended behavior:

1. Add `PredictionEntry.paid`.
2. Add `PredictionEntry.prize_eligible`.
3. If `payment_mode = per_entry`, admin manages paid status per entry.
4. If `payment_mode = per_user`, admin can manage paid status at user level, but prize eligibility should still be resolved onto each entry.
5. Do not add `User.paid` in a greenfield implementation unless it is only a derived convenience field.
6. Leaderboard/prize logic should use entry-level eligibility after payment rules are resolved.

### 4.10 Leaderboard

1. Leaderboard rows represent prediction entries, not users.
2. Each row includes:
   - `entry_id`
   - `entry_reference`
   - `entry_name`
   - `user_id`
   - `user_name`
   - points and breakdown
   - position and movement
   - status/eligibility metadata if useful
3. In single-entry mode, the leaderboard can hide entry identity because each user has one active entry.
4. In multi-entry mode, a user with three submitted entries can occupy three leaderboard rows.
5. Draft, ready, withdrawn, disabled, and unsubmitted entries should be excluded from default leaderboard calculations.
6. Admin views may include filters to show all statuses.
7. Tie-breaking should remain total points, then exact scores, unless changed separately.

### 4.11 Public Prediction Visibility

Blind-pool behavior must remain intact.

1. Public profile prediction views should show entries separately.
2. Other users can see an entry's fixture predictions only when those fixtures are locked or finished.
3. Community prediction endpoints should aggregate by entry, not by user.
4. Agreement counts should count entries, not users, because each entry is competing independently.

### 4.12 Admin Management

Admins need to:

- Configure whether multiple entries are enabled.
- Configure maximum entries per user.
- Configure whether duplicate-from-existing is enabled.
- Configure whether entry rename and withdrawal are user-facing.
- Configure whether payment is per user or per entry.
- Configure whether unpaid entries can be submitted.
- See all entries across users.
- Search/filter by user, entry reference, status, paid status, and disabled status.
- Disable or re-enable entries, subject to rules.
- Mark entry paid/unpaid.
- View entry predictions.
- Move an entry phase to locked manually only if needed for recovery.
- Audit state transitions.

Admin config changes should be audited because they can materially affect competition fairness.

## 5. State Machine

### 5.1 Status Values

Use these phase statuses:

| Status | Meaning |
| --- | --- |
| `draft` | Editable working state. May be incomplete. Not official. |
| `ready` | Validated as complete enough to submit. Not yet official. |
| `submitted` | Official and competition-eligible before lock. |
| `locked` | Terminal locked state. Predictions cannot be edited. |
| `withdrawn` | Withdrawn from competition. Read-only and excluded. |
| `disabled` | Admin/system disabled. Read-only and excluded. |

### 5.2 Transition Rules

| From | To | Actor | Allowed when | Notes |
| --- | --- | --- | --- | --- |
| none | draft | User/Admin/System | Entry created | Create `PredictionEntry` and initial `PredictionEntryPhase`. |
| draft | ready | User | Validation passes and phase is not locked | No predictions change. |
| ready | draft | User | Phase is not locked | Explicit "Edit" action. |
| ready | submitted | User | Phase is not locked | Sets `submitted_at`. |
| submitted | draft | User | Phase is not locked and no fixture-level locked predictions would be changed | Recommended explicit reopen action. |
| submitted | locked | System/Admin | Phase lock has occurred | Sets `locked_at`; terminal for edits. |
| draft | withdrawn | User/Admin | Phase is not locked | Whole entry withdrawal recommended. |
| ready | withdrawn | User/Admin | Phase is not locked | Whole entry withdrawal recommended. |
| submitted | withdrawn | User/Admin | Phase is not locked | Whole entry withdrawal recommended. |
| draft | disabled | Admin/System | Admin reason or unsubmitted at lock | Requires reason. |
| ready | disabled | Admin/System | Admin reason or unsubmitted at lock | Requires reason. |
| submitted | disabled | Admin | Before lock | Requires reason. |
| locked | disabled | Admin | Avoid if locked must be terminal | Prefer entry-level `is_disabled` overlay. |
| withdrawn | draft | Admin | Exceptional recovery before lock | Audit required. |
| disabled | draft | Admin | Exceptional recovery before lock | Audit required. |

### 5.3 State Validation Rules

The backend must enforce state transitions. Do not rely on frontend-only checks.

Required backend checks:

- Entry belongs to current user unless admin.
- Entry belongs to active competition.
- Phase is active or allowed for editing.
- Fixture is not locked.
- Phase deadline has not passed.
- Entry is not withdrawn.
- Entry is not disabled.
- Entry phase is not locked.
- Transition is allowed from current status.

## 6. Data Model Specification

### 6.1 Competition Entry Settings

Recommended fields on the competition/tournament configuration model:

| Field | Type | Notes |
| --- | --- | --- |
| `multiple_entries_enabled` | bool | Main feature switch. Defaults to `false`. |
| `max_entries_per_user` | int | Defaults to `1`. Must be `1` when multiple entries are disabled. |
| `auto_create_first_entry` | bool | Defaults to `true`. |
| `allow_duplicate_from_existing` | bool | Defaults to `false` in single-entry mode. |
| `allow_user_rename` | bool | Defaults to `true`. |
| `allow_user_withdrawal` | bool | Defaults to `true`. |
| `require_ready_before_submit` | bool | Defaults to `true`. |
| `payment_mode` | enum | `per_user` or `per_entry`. |
| `block_unpaid_entry_submission` | bool | Useful when `payment_mode = per_entry`. |
| `show_entry_reference_publicly` | bool | Controls public leaderboard display. |

Validation rules:

- If `multiple_entries_enabled = false`, `max_entries_per_user` must be `1`.
- If `payment_mode = per_user`, entry-level paid status is ignored for submission.
- If `payment_mode = per_entry`, submission can require that entry's paid status.
- Disabling multiple entries after users have multiple active entries should be blocked unless an explicit admin resolution workflow is implemented.

### 6.2 New Model: PredictionEntry

Recommended table: `prediction_entries`

Fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | Generated server-side. |
| `competition_id` | UUID FK | References `competitions.id`. |
| `user_id` | UUID FK | Owner. |
| `reference` | string | Immutable, unique per competition. |
| `display_name` | string | User-editable label. |
| `entry_number` | int | Per-user sequence for display/sorting. |
| `paid` | bool | Entry-level paid flag. |
| `prize_eligible` | bool | Defaults to true when paid if rules require payment. |
| `is_disabled` | bool | Admin overlay. |
| `disabled_reason` | string nullable | Required when disabled. |
| `disabled_at` | datetime nullable | UTC aware. |
| `disabled_by_user_id` | UUID nullable | Admin who disabled. |
| `withdrawn_at` | datetime nullable | Whole-entry withdrawal. |
| `withdrawn_reason` | string nullable | User/admin reason. |
| `created_at` | datetime | UTC aware. |
| `updated_at` | datetime | UTC aware. |

Constraints:

- Unique `(competition_id, reference)`.
- Unique `(competition_id, user_id, entry_number)`.
- Index `(competition_id, user_id)`.
- Index `(competition_id, is_disabled)`.

Reference generation:

- Generate on backend.
- Must be immutable.
- Suggested format: `WC26-000001`, `WC26-000002`, etc.
- Avoid relying on user initials for uniqueness.

### 6.3 New Model: PredictionEntryPhase

Recommended table: `prediction_entry_phases`

Fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | Generated server-side. |
| `entry_id` | UUID FK | References `prediction_entries.id`. |
| `phase` | enum | `phase_1` or `phase_2`. |
| `status` | enum | `draft`, `ready`, `submitted`, `locked`, `withdrawn`, `disabled`. |
| `ready_at` | datetime nullable | Set on draft -> ready. |
| `submitted_at` | datetime nullable | Set on ready -> submitted. |
| `locked_at` | datetime nullable | Set on submitted -> locked. |
| `withdrawn_at` | datetime nullable | If phase-level withdrawal is used. |
| `disabled_at` | datetime nullable | If phase-level disabled is used. |
| `status_reason` | string nullable | Reason for withdrawn/disabled/system transitions. |
| `created_at` | datetime | UTC aware. |
| `updated_at` | datetime | UTC aware. |

Constraints:

- Unique `(entry_id, phase)`.
- Index `(phase, status)`.

### 6.4 Prediction Models

Prediction tables should be owned by `entry_id` from the start:

- `MatchPrediction`
- `TeamPrediction`
- `BonusPrediction`

Recommended constraints:

| Table | New uniqueness |
| --- | --- |
| `match_predictions` | `(entry_id, fixture_id)` |
| `team_predictions` | `(entry_id, phase, team, stage)` |
| `bonus_predictions` | `(entry_id, question_id)` |

Greenfield note:

- Do not store `user_id` on prediction rows unless there is a strong performance reason.
- The owning user should be reached through `PredictionEntry.user_id`.
- All prediction reads/writes should authorize through the entry, then operate by `entry_id`.

### 6.5 Leaderboard Snapshots

Snapshots should be per entry from day one.

Recommended table shape: keep `leaderboard_snapshots`, but store `entry_id` instead of `user_id`. The related user can be resolved through the entry.

New uniqueness:

- `(entry_id, captured_date)`

### 6.6 Audit Trail

Recommended new table: `prediction_entry_events`

Fields:

- `id`
- `entry_id`
- `phase`
- `from_status`
- `to_status`
- `actor_user_id`
- `actor_role` (`user`, `admin`, `system`)
- `reason`
- `created_at`

This makes state changes explainable and safer for admin operations.

## 7. API Specification

### 7.1 User Entry Endpoints

Recommended new router: `backend/app/api/entries.py`

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/entries` | List current user's entries for active competition. |
| `POST` | `/api/entries` | Create a new draft entry. |
| `GET` | `/api/entries/{entry_id}` | Read one owned entry. |
| `PATCH` | `/api/entries/{entry_id}` | Rename display name. |
| `POST` | `/api/entries/{entry_id}/duplicate` | Duplicate predictions into a new draft entry. |
| `POST` | `/api/entries/{entry_id}/phases/{phase}/ready` | Validate and mark phase ready. |
| `POST` | `/api/entries/{entry_id}/phases/{phase}/submit` | Submit a ready phase. |
| `POST` | `/api/entries/{entry_id}/phases/{phase}/reopen` | Move ready/submitted back to draft before lock. |
| `POST` | `/api/entries/{entry_id}/withdraw` | Withdraw whole entry before lock. |

Single-entry mode behavior:

- `GET /api/entries` returns the user's one entry.
- `POST /api/entries` rejects creation if an active entry already exists.
- Existing prediction screens can resolve the user's only entry automatically.

Multi-entry mode behavior:

- `GET /api/entries` returns all entries owned by the user.
- `POST /api/entries` creates a draft entry while below `max_entries_per_user`.
- Prediction screens require an explicit selected `entry_id`.

### 7.2 Prediction Endpoints

Preferred new shape:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/entries/{entry_id}/predictions/matches` | Get match predictions for entry. |
| `PUT` | `/api/entries/{entry_id}/predictions/matches/{fixture_id}` | Upsert one match prediction. |
| `POST` | `/api/entries/{entry_id}/predictions/matches/batch` | Batch upsert match predictions. |
| `GET` | `/api/entries/{entry_id}/predictions/bracket?phase=phase_1` | Get bracket for entry/phase. |
| `PUT` | `/api/entries/{entry_id}/predictions/bracket` | Save bracket for entry/current or supplied phase. |
| `GET` | `/api/entries/{entry_id}/predictions/bonus` | Get bonus picks for entry. |
| `POST` | `/api/entries/{entry_id}/predictions/bonus` | Save bonus picks for entry. |

Greenfield rule: do not keep user-scoped `/api/predictions/...` endpoints. All prediction reads/writes should be explicitly entry-scoped.

### 7.3 Leaderboard Endpoints

Update `GET /api/leaderboard/` response entries:

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

Add optional filters:

- `status=submitted`
- `include_disabled=false`
- `include_withdrawn=false`
- `user_id=...` for admin views

### 7.4 Admin Entry Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/admin/competition/entry-settings` | Read effective entry configuration. |
| `PATCH` | `/api/admin/competition/entry-settings` | Update entry configuration with validation. |
| `GET` | `/api/admin/entries` | List/search all entries. |
| `POST` | `/api/admin/entries/{entry_id}/disable` | Disable entry with reason. |
| `POST` | `/api/admin/entries/{entry_id}/enable` | Re-enable before lock if allowed. |
| `PATCH` | `/api/admin/entries/{entry_id}/paid` | Toggle or set paid status. |
| `PATCH` | `/api/admin/entries/{entry_id}/prize-eligible` | Set prize eligibility. |
| `GET` | `/api/admin/entries/{entry_id}/events` | View transition audit log. |

The admin settings endpoint must validate existing entries before accepting changes that narrow the rules.

## 8. Frontend Specification

### 8.1 Entry Store

Add `frontend/src/lib/stores/entries.ts`.

Responsibilities:

- Load effective competition entry settings.
- Load current user's entries.
- Track active selected entry ID.
- Create entry.
- Duplicate entry.
- Rename entry.
- Transition entry phase status.
- Withdraw entry.
- Expose derived stores:
  - `activeEntry`
  - `activeEntryPhaseStatus`
  - `submittedEntries`
  - `editableEntries`

Active entry persistence:

- Store last active entry ID in localStorage by user and competition.
- In single-entry mode, the selected entry can be derived from the only entry and does not need visible UI.

### 8.2 Prediction Store Changes

Update `predictions.ts` so every fetch/save is scoped to active entry.

Required changes:

- `fetchMatchPredictions(entryId)`
- `saveAllPredictions(entryId)`
- `fetchBracketPredictions(entryId, phase)`
- `saveBracketPredictions(entryId, phase, predictions)`
- `getMyBonusPredictions(entryId)`
- `saveBonusPredictions(entryId, predictions)`

Unsaved persistence keys must include entry ID:

```text
predictor_unsaved_{userId}_{entryId}_matches
predictor_unsaved_{userId}_{entryId}_bracket_phase1
predictor_unsaved_{userId}_{entryId}_bracket_phase2
predictor_unsaved_{userId}_{entryId}_bonus
```

### 8.3 Prediction Wizard UX

The prediction wizard must adapt to the active entry settings.

Single-entry mode:

- Hide the entry switcher.
- Hide create-entry and duplicate-entry actions.
- Auto-load or auto-create the user's only entry.
- Preserve the existing prediction flow as much as possible.

Multi-entry mode:

- Add an entry switcher at the top of `/predictions`.
- Show create-entry and duplicate-entry actions only when enabled and allowed by limits.

Required UI:

- Current entry display name and reference.
- Status badge for current phase.
- Create new entry button.
- Duplicate current entry button.
- Entry selector dropdown/list.
- Rename action.
- Ready/Submit/Reopen/Withdraw actions depending on status.

Suggested status UX:

| Status | UI behavior |
| --- | --- |
| `draft` | Editable, save draft, mark ready. |
| `ready` | Read-only summary by default, submit or edit. |
| `submitted` | Read-only summary by default, reopen before lock if allowed. |
| `locked` | Read-only. |
| `withdrawn` | Read-only, excluded. |
| `disabled` | Read-only with admin reason. |

### 8.4 Dashboard UX

Dashboard should adapt to entry mode.

Single-entry mode:

- Show the user's one entry as today's participant summary.
- Hide "Your entries" panels unless useful for status/payment messaging.

Multi-entry mode should decide whether it shows:

- aggregate user summary across all entries, or
- selected active entry summary.

Recommendation for first release:

- Add an entry selector.
- Dashboard KPIs reflect the selected entry.
- Add a compact "Your entries" panel showing rank/points/status for each submitted entry.

### 8.5 Leaderboard UX

Leaderboard rows should respect entry settings.

Single-entry mode:

- Show one row per user.
- Hide entry reference and entry display name unless `show_entry_reference_publicly` is enabled.

Multi-entry mode rows should show entry identity clearly:

- Primary row label: entry display name.
- Secondary text: owner name and reference.
- If current user's entry, show `YOU`.
- If the user has multiple entries, each row gets its own `YOU` marker.

Example:

```text
1  Vinay Main       @Vinay · WC26-000021     148 pts
7  Vinay Wildcard   @Vinay · WC26-000022     121 pts
```

### 8.6 Profile UX

Profiles should adapt to entry mode.

Single-entry mode:

- Preserve the current profile feel.
- Show entry-level payment/status only if needed.

Multi-entry mode should group predictions and stats by entry.

Suggested tabs/sections:

- Entries summary.
- Entry detail with visible match predictions.
- Bracket picks by entry.

### 8.7 Admin UX

Admin user management should add an Entries section:

- Competition entry settings panel.
- Entries per user.
- Paid/eligible toggles per entry.
- Entry status badges.
- Disable/enable controls.
- Search by reference.

## 9. Greenfield Build Strategy

There is no production data migration requirement. Treat this as a schema and domain redesign inside the current codebase.

### 9.1 Schema Strategy

1. Add `prediction_entries`, `prediction_entry_phases`, and optionally `prediction_entry_events`.
2. Make `match_predictions`, `team_predictions`, and `bonus_predictions` require `entry_id`.
3. Remove or ignore user-based uniqueness assumptions in prediction tables.
4. Make leaderboard snapshots require `entry_id`.
5. Keep Alembic as the schema source of truth, but the migration does not need backfill logic.
6. If local/dev data exists, it can be dropped or recreated.

### 9.2 API Strategy

1. Prefer entry-scoped endpoints immediately.
2. Do not add default-entry compatibility wrappers.
3. Update frontend and backend together enough that no user-facing route depends on user-scoped predictions.

### 9.3 Product Bootstrap

New users need an entry before predicting. Recommended behavior:

1. On registration, do not create an entry automatically unless the competition is active and entry rules are stable.
2. On first visit to `/predictions`, auto-create a first draft entry if `auto_create_first_entry` is enabled and the user has no entries.
3. In single-entry mode, hide entry management and make the first entry feel like the user's normal prediction set.
4. In multi-entry mode, display a clear entry selector even when there is only one entry, so the multiple-entry mental model is visible from the start.

## 10. Backend Implementation Plan

### Slice 1: Models And Schema

Deliverables:

- Competition entry settings fields/model.
- `PredictionEntry` model.
- `PredictionEntryPhase` model.
- Optional `PredictionEntryEvent` model.
- `entry_id` columns on prediction tables.
- Alembic migration with fresh schema changes only, no backfill.
- Tests for model constraints and entry ownership.

### Slice 2: Entry Service

Create `backend/app/services/entries.py`.

Responsibilities:

- load and validate effective entry settings
- create entry
- generate reference
- list user's entries
- get and authorize entry
- validate readiness
- transition states
- withdraw entry
- admin disable/enable
- enforce single-entry mode and multi-entry limits
- write audit events

### Slice 3: Entry API

Create `backend/app/api/entries.py`.

Add route schemas under `backend/app/schemas/entry.py`.

Include router in `backend/app/api/__init__.py`.

Expose effective entry settings to the frontend through either the entry list response or a competition settings endpoint.

### Slice 4: Prediction API Scoping

Update prediction routes to operate by entry:

- New nested routes preferred.
- Update match, bracket, bonus, agreement, and exposure logic.

### Slice 5: Scoring And Leaderboard

Update:

- `calculate_user_points` -> new `calculate_entry_points`.
- Leaderboard calculates entries.
- Snapshot service snapshots entries.
- Profile service can aggregate by user and/or entry.

### Slice 6: Frontend Entry UX

Add:

- `entries.ts` store.
- Competition entry settings API/store.
- Entry API file.
- Entry selector in predictions when multiple entries are enabled.
- Entry-aware prediction store calls.
- Entry-aware localStorage draft persistence.
- Leaderboard row changes.
- Admin entry management.

## 11. Testing Requirements

### 11.1 Backend Tests

Add tests for:

- Entry settings validation.
- Single-entry mode auto-creates or resolves one entry.
- Single-entry mode prevents creating a second active entry.
- Multi-entry mode allows entries up to `max_entries_per_user`.
- Config changes that would invalidate existing entries are rejected or explicitly grandfathered.
- User can create multiple entries.
- Entry references are unique.
- Max entry limit is enforced.
- User cannot access another user's entry.
- Draft -> ready requires validation.
- Ready -> submitted succeeds.
- Submitted -> locked occurs at lock.
- Locked entries reject edits.
- Withdrawn entries are excluded from leaderboard.
- Disabled entries are excluded from leaderboard.
- Match predictions are unique by entry and fixture.
- Two entries owned by same user can predict different scores for the same fixture.
- Leaderboard returns one row per submitted/locked entry.
- Agreement counts count entries, not users.

### 11.2 Frontend Tests

Add tests for:

- Single-entry mode hides entry management UI.
- Multi-entry mode shows entry selector and creation controls.
- Entry selector loads and switches active entry.
- Prediction store fetches/saves using selected entry ID.
- Draft persistence keys are entry-scoped.
- Leaderboard displays multiple rows for same user.
- State badges and buttons match allowed transitions.

### 11.3 Manual QA

Minimum manual scenarios:

1. Admin starts in single-entry mode.
2. New user opens the prediction wizard and gets or creates a first draft entry.
3. User cannot create a second entry while multiple entries are disabled.
4. Admin enables multiple entries and sets `max_per_user`.
5. User creates second entry and predicts different scores.
6. User submits first entry but leaves second as draft.
7. Leaderboard shows only submitted/locked entry.
8. Admin disables submitted entry.
9. Disabled entry disappears from normal leaderboard.
10. User switches entries and sees correct predictions per entry.
11. Public profile respects blind-pool rules per entry.

## 12. Open Product Decisions

Resolve these before implementation:

1. Default competition mode: single-entry or multi-entry.
2. Default maximum entries per user when multi-entry mode is enabled.
3. Whether each entry requires separate payment.
4. Whether bonus questions are required for `ready`.
5. Whether users can delete draft entries or only withdraw them.
6. Whether users can reopen submitted entries before lock.
7. Whether admins can disable locked entries as a status, or only mark locked entries prize-ineligible with an overlay.
8. Whether dashboard defaults to selected entry or aggregate view in multi-entry mode.
9. Whether public profiles show all entries or only submitted/locked entries.
10. Whether duplicate-entry flow is first release or follow-up.

## 13. Claude/Codex-Friendly Task Breakdown

Use small implementation tasks with clear ownership. Avoid asking an agent to do the whole feature in one pass.

### Task A: Backend Models And Schema

Prompt:

```text
Implement the PredictionEntry backend data model foundation.

Use docs/prediction-entries-requirements-spec.md as the source of truth.
Assume this is greenfield with no production data migration or backfill requirement.
Scope:
- Add competition entry settings with a `multiple_entries_enabled` feature flag.
- Add PredictionEntry and PredictionEntryPhase SQLModel models.
- Add required entry_id ownership to match_predictions, team_predictions, bonus_predictions.
- Add Alembic migration for the fresh schema shape only; no data backfill.
- Do not preserve user_id on prediction rows unless strictly needed.
- Add focused tests for model constraints and entry ownership.

Do not change frontend code in this task.
Do not refactor scoring or leaderboard yet.
```

### Task B: Entry Service And API

Prompt:

```text
Implement entry management APIs.

Use docs/prediction-entries-requirements-spec.md.
Scope:
- Add backend/app/services/entries.py for create/list/get/rename/transition/withdraw logic.
- Add backend/app/schemas/entry.py.
- Add backend/app/api/entries.py and include it under /api/entries.
- Enforce ownership, active competition, single-entry mode, max entries, state transition rules, and timezone-aware UTC timestamps.
- Add admin endpoints or schemas for reading/updating entry settings with validation.
- Add backend tests for create/list/rename/ready/submit/reopen/withdraw and forbidden cross-user access.

Do not change prediction save APIs yet except where absolutely required for compilation.
```

### Task C: Entry-Scoped Predictions

Prompt:

```text
Make predictions entry-scoped.

Use docs/prediction-entries-requirements-spec.md.
Scope:
- Add nested /api/entries/{entry_id}/predictions/... routes for match, bracket, and bonus predictions.
- Update services so predictions are read/written by entry_id.
- Enforce entry phase status and lock rules before writes.
- Add tests proving two entries from the same user can store different predictions for the same fixture.

Do not update the Svelte UI in this task.
```

### Task D: Entry-Based Scoring And Leaderboard

Prompt:

```text
Change scoring and leaderboard from user-based to entry-based.

Use docs/prediction-entries-requirements-spec.md.
Scope:
- Add calculate_entry_points(entry_id).
- Update leaderboard to rank PredictionEntry rows.
- Include entry_id, entry_reference, entry_name, user_id, and user_name in LeaderboardEntry.
- Exclude draft, ready, withdrawn, disabled, and unsubmitted entries from normal leaderboard.
- Update snapshots to use entry_id.
- Add backend tests for one user with multiple independently ranked entries.

Do not change frontend UI except type updates if required by tests/build.
```

### Task E: Frontend Entry Switching

Prompt:

```text
Add frontend support for multiple prediction entries.

Use docs/prediction-entries-requirements-spec.md.
Scope:
- Add frontend/src/lib/api/entries.ts.
- Add frontend/src/lib/stores/entries.ts.
- Read effective entry settings from the backend.
- In single-entry mode, hide entry management and preserve the current prediction flow.
- In multi-entry mode, add an entry selector/create/rename UI to /predictions.
- Make prediction fetch/save calls use the active entry ID.
- Scope unsaved localStorage drafts by entry ID.
- Show current entry status and allowed actions.
- Keep existing Panini design style.

Do not change backend code in this task.
```

### Task F: Admin And Public Views

Prompt:

```text
Expose multiple entries in admin, leaderboard, dashboard, and profile views.

Use docs/prediction-entries-requirements-spec.md.
Scope:
- Update leaderboard UI to show entry rows with owner and reference.
- In single-entry mode, hide entry labels/references unless configured otherwise.
- Update dashboard to select/show an entry and summarize all of the user's entries when multiple entries are enabled.
- Update profile pages to group predictions by entry when multiple entries are enabled.
- Add admin entry settings and entry management for paid/eligible/disabled status.
- Preserve blind-pool rules.

Keep changes consistent with the Panini design system.
```

## 14. Acceptance Criteria

The feature is complete when:

1. Admins can enable or disable multiple-entry mode.
2. When multiple entries are disabled, each user can have only one active entry and the app behaves like the current one-entry system.
3. When multiple entries are enabled, a user can create entries up to the configured limit.
4. Each entry has a unique reference and display name.
5. Each entry can store different predictions for the same fixture.
6. Each entry has independent phase status.
7. Only submitted/locked eligible entries appear in normal leaderboard.
8. A user's multiple entries appear as separate leaderboard rows when multiple-entry mode is enabled.
9. Admin can manage paid/disabled status per entry.
10. Admin can configure entry limits and related entry behavior.
11. Blind-pool visibility rules still hold.
12. A new user can get or create a first draft entry without manual admin setup.
13. Locked entries cannot be edited from the API.
14. Tests cover settings enforcement, state transitions, entry-scoped predictions, and entry-based leaderboard rows.
