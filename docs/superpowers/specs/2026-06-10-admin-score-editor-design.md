# Admin Score Editor (`/admin/sync`) — Design

**Date:** 2026-06-10 · **Shipped as:** v2.162.0 · **Status:** **deployed** (prod 2026-06-10 12:43 UTC)

## Purpose

Make the read-only fixtures table on `/admin/sync` editable so the admin
can enter match scores and seed knockout team names by hand. Two jobs:

1. **Dev-test vehicle** for the v2.161.0 scoring fixes — simulate a
   tournament (finish group games, seed knockout rounds, watch points
   flow) without curl.
2. **Production escape hatch** when Football-Data.org fails, lags, or
   serves a wrong score mid-tournament, with ~147 live users watching
   the leaderboard.

## Decisions (user, 2026-06-10)

- Edit scope: **scores on any fixture + team seeding on knockout fixtures**.
- Knockout draws: **optional ET + penalties fields** (required for winner
  resolution — `Score.outcome` returns `X` for a level scoreline unless
  ET/pens break the tie, and the advancement logic needs `1`/`2`).
- Safety rails: **confirm dialog before save** + **audit log event** per
  manual edit. No un-finish UI (the existing
  `PATCH /fixtures/{id}/status` stays curl-only).
- Sync protection: **API sync skips `verified=True` scores**; manual
  saves set `verified=true` by default. Un-verifying hands control back
  to the API.
- UI shape: **inline row expansion** (Edit button expands the row into a
  form; fast for back-to-back entry).
- Packaging: same branch as v2.161.0, released together as **2.162.0**.

## Constraint honoured

Everything rides on fields and endpoints that already exist. No schema
change, no migration. `Score.verified`, `Score.source`, ET/penalty
columns, `PUT /api/scores/{fixture_id}`, `PUT /api/fixtures/{id}`, and
the audit service are all in place today. The only schema touch is
ADDITIVE: expose `verified` on the embedded `FixtureScore` response so
the table can render the lock badge.

## Backend changes

1. **Sync guard** — `score_sync._apply_external_score`: when the
   existing score row has `verified=True`, skip the overwrite and count
   it in a new `ScoreSyncResult.skipped_verified` field. Without this,
   the 60-second scheduler re-applies a wrong API score within a minute
   of the admin correcting it.
2. **Audit events** —
   - `PUT /api/scores/{fixture_id}` records `score.manual_update`
     (actor admin, subject fixture, old → new values, verified flag).
   - `PUT /api/fixtures/{id}` records `fixture.admin_update` with the
     changed fields (covers knockout team seeding).
3. **Schema** — `FixtureScore` gains `verified: bool = False`;
   `fixture_to_read` passes it through.

## Frontend changes

- `frontend/src/lib/api/scores.ts`: `updateScore(fixtureId, payload)`.
- `frontend/src/lib/api/fixtures.ts`: `updateFixture(fixtureId, payload)`.
- `frontend/src/lib/types`: fixture score type gains `verified`.
- `/admin/sync/+page.svelte`:
  - Edit button per row → inline expansion with home/away score inputs
    (0–15). Knockout rows add a "went to extra time / penalties" toggle
    revealing ET-score + penalty inputs, and editable home/away team
    text fields (seeding).
  - Save → confirm dialog stating the consequence ("marks the match
    FINISHED and updates the leaderboard for everyone") → PUT score
    (with `verified: true`) and/or PUT fixture for team changes →
    reload row.
  - 🔒 badge in the Score column when `score.verified` — "API sync will
    not touch this." Editing exposes an "API can overwrite" checkbox to
    un-verify.
  - Sync card surfaces `skipped_verified` from the sync response.

## Behavior notes

- Saving a score flips the fixture to FINISHED and invalidates the
  leaderboard cache (existing endpoint behavior).
- Group rows never show ET/pens or team fields.
- Scoring counts only FINISHED fixtures, so reverting a status via the
  existing PATCH un-pays points if ever needed.

## Testing

- Backend: sync skips verified scores (value untouched, counted);
  sync still overwrites unverified manual scores; audit events written
  for manual score + fixture updates.
- Frontend: `npm run check` 0 errors; the dev tournament walkthrough is
  the manual test.

## Out of scope

Bulk entry, undo/history stack, kickoff/status editing in the UI,
live-minute simulation.
