# All-Entries Predictions CSV Export — Design

**Date:** 2026-06-11 (deadline night)
**Status:** Approved (user confirmed wide-matrix layout, pool-post-release
gate, leaderboard-toolbar placement)
**Mockup:** `mockups/AllEntriesExport/AllEntries.xlsx`

## Purpose

A single downloadable CSV showing every scoring entry's complete
predictions side-by-side. This is a **transparency control**: once the
pool opens post-deadline, anyone can download one sheet covering all
entries and use it to resolve disputes or accusations of manipulation.
Predictions are locked at the deadline, so the export is stable from
the moment it becomes available.

## Layout (wide matrix, mirrors the mockup)

Four label columns — `Date (UTC)`, `Group`, `Home`, `Away` — then one
column per eligible entry, ordered by entry number. Roughly 140 data
rows regardless of pool size.

```
Preamble        competition name, generated-at (UTC), deadline (UTC),
                entry count, note that knockout rows are alphabetical
Header block    Ref / Name / Entry / Submitted (UTC) — one row each,
                labels in the "Away" column, values per entry column
GROUP STAGE     72 rows, one per group fixture (kickoff order):
                date, group, home, away, then "2-1" per entry
ROUND OF 32     32 rows "R32 pick 1..32" — each entry's predicted
                advancing teams, listed alphabetically
ROUND OF 16     16 rows · QUARTER-FINALS 8 · SEMI-FINALS 4 ·
                FINAL 2 · CHAMPION 1   (same shape)
BONUS           4 rows — full question label, then each entry's answer
```

Key properties:

- **Knockout rows are alphabetical per entry** because `TeamPrediction`
  stores an unordered *set* of teams per stage (32/16/8/4/2/1), not
  slots. A preamble note says row position carries no meaning, so
  column-to-column alignment is not misread as a head-to-head pairing.
- **Row count per knockout section = max(stage quota, longest pick list
  across entries)** — never silently drops a row (data-integrity rule).
- **Missing picks render as blank cells**, never invented values.
- **UTF-8 BOM** prefix so Excel-on-Windows double-click renders
  Türkiye / Côte d'Ivoire correctly.
- **Formula-injection guard** on user-supplied strings (person name,
  entry name, bonus answers): cells starting `=`, `+`, `-`, `@` get a
  leading apostrophe.
- Stage values read/compare against the **singular canonical forms**
  (`quarter_final` …, v2.161.0 invariant). `third_place` never appears
  (no such bracket picks exist).

## Backend

**Service** `backend/app/services/predictions_export.py`:
`build_all_entries_export(session) -> str` returns the full CSV text.
Bulk loads (no N+1): eligible entries via `eligible_entry_ids_select()`
(SUBMITTED, not disabled, not withdrawn — the scoring pool) with user +
phases eager-loaded; group fixtures ordered by kickoff; all PHASE_1
match predictions; all PHASE_1 team predictions; bonus predictions for
current YAML question ids only. `Submitted (UTC)` comes from the
entry's PHASE_1 phase row, wrapped in `aware_utc()` at the service
boundary.

**Endpoint** `GET /api/predictions/export/all-entries.csv`
(in `backend/app/api/predictions.py`):

- Auth: signed-in user required.
- Gate: `user.is_admin or competition.post_deadline_live`, else 403 —
  identical semantics to the V4 page gates. The blind pool stays sealed
  until the admin flips "Go live"; admins can verify early.
- Response: `text/csv; charset=utf-8` with
  `Content-Disposition: attachment; filename="all-entries-predictions-YYYY-MM-DD.csv"`.

## Frontend

- New helper `downloadAllEntriesCsv()` in `frontend/src/lib/api/export.ts`
  (new file, outside the types barrel) reusing the Bearer-token blob
  download pattern from `admin.ts:downloadAdminEntriesCsv` — CSV needs
  the Authorization header, so no `window.location.href`.
- "All entries (CSV)" button in the `/leaderboard` header row next to
  the view pills, rendered only inside the existing `lbOpen` gate
  (`V4_LEADERBOARD_ENABLED && (admin || $postDeadlineLive)`), with
  busy/error states (toast-free: brief inline error text).

## Testing

- `backend/tests/test_predictions_export.py`: section row counts (72
  group rows when 72 fixtures, 32+16+8+4+2+1 knockout rows, 4 bonus
  rows); eligibility filter (draft/withdrawn/disabled excluded);
  alphabetical knockout ordering; blank-for-missing; injection guard;
  BOM present; endpoint gating (401 anon, 403 non-admin pre-release,
  200 admin pre-release, 200 user post-release).
- `npm run check` stays at 0 errors. No new frontend pure logic worth a
  vitest (the helper is a thin fetch wrapper).

## Out of scope / later

- Long-format (one row per entry-per-pick) companion CSV — cheap to add
  behind the same service if pivot-table demand appears.
- Actual results column — this sheet is the *predictions* record;
  results live on /results.
- Version bump + changelog deferred to release coordination (feature →
  minor bump). Work stays on `claude/epic-wilbur-3a2e98`.
