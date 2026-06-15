# Google Sheets sync — published predictions + live standings

**Status:** code complete (v2.177.0), pending Google credential + deploy.
**Branch:** `claude/csv-google-sheets-sync-wugad3`

## Goal

Mirror the all-entries predictions matrix (the same data behind the
"All entries CSV" download) into a Google Sheet, and keep a second tab
of live standings refreshed automatically after every game. The sheet is
shared **view-only** with the pool so anyone can read it online; nobody
but the service account can write to it.

Target sheet (chosen by the pool owner):
`https://docs.google.com/spreadsheets/d/1-UZTOYQh0jIUuMw7VarsXdj8a3gPC3whVwii61ZS75Y/edit`
→ `GOOGLE_SHEET_ID=1-UZTOYQh0jIUuMw7VarsXdj8a3gPC3whVwii61ZS75Y`

## Architecture (backend push)

```
score_scheduler tick (every 60s in a match window)
  └─ sync_scores_once  → score changed?
       └─ _sync_sheets(session)               [best-effort, non-raising]
            └─ sheets_sync.sync_to_sheets(...)
                 ├─ build_standings_rows()     ← calculate_leaderboard(phase_1)
                 └─ build_all_entries_rows()   ← shared with the CSV export
                      └─ gspread → open_by_key → write "Standings"/"Predictions"
```

- **Why push, not pull (`=IMPORTDATA`/Apps Script):** the all-entries
  endpoint requires a Bearer token (no cookie auth), so a sheet-side pull
  would have to store an admin token. Pushing from the backend keeps the
  secret server-side and rides the existing 60s score heartbeat.
- **Standings** tab: rewritten on every tick where a score moved, plus
  once at scheduler startup (so it's populated outside match windows).
- **Predictions** tab: written once per process (picks are frozen after
  the deadline). `force_predictions=True` re-pushes on demand.
- **Read-only for viewers** is automatic: share view-only; the service
  account is the only Editor.

## Files

- `backend/app/services/sheets_sync.py` — the service (lazy gspread import,
  never raises into callers, config-gated via `is_configured()`).
- `backend/app/services/predictions_export.py` — refactored: the picks
  matrix now lives in `build_all_entries_rows()`; the CSV download is a
  thin serializer over it (single source of truth, shared with the sheet).
- `backend/app/services/score_scheduler.py` — `_sync_sheets()` helper +
  per-tick and startup hooks.
- `backend/app/config.py` — `google_sheet_id`, `google_service_account_json`,
  `sheets_sync_enabled`.
- `backend/pyproject.toml` — adds `gspread`, `google-auth`.
- `backend/tests/test_sheets_sync.py` — gate, row shapes, push-once,
  force, never-raises (fake spreadsheet; no real Google calls).

## Setup checklist (do this on desktop before deploy)

1. **Google Cloud project → service account.**
   - console.cloud.google.com → create/select a project.
   - Enable the **Google Sheets API**.
   - Create a **service account**; create a **JSON key** for it; download it.
   - Copy the service account's `client_email` (looks like
     `something@project.iam.gserviceaccount.com`).
2. **Share the sheet with the service account.**
   - Open the target sheet → Share → paste the `client_email` → **Editor**.
3. **Provide the credentials to the backend** (`.env` at `/opt/predictor`):
   ```
   GOOGLE_SHEET_ID=1-UZTOYQh0jIUuMw7VarsXdj8a3gPC3whVwii61ZS75Y
   GOOGLE_SERVICE_ACCOUNT_JSON=/opt/predictor/secrets/sheets-sa.json
   # …or paste the raw key JSON inline on one line instead of a path.
   SHEETS_SYNC_ENABLED=true
   ```
   If using a file path, bind-mount the secret into the backend container
   (the existing `./backend/data:/app/data` mount, or add a `secrets`
   mount) and point the var at the in-container path.
4. **Share the sheet view-only with the pool** (Anyone with link → Viewer),
   so members read online but can't edit.
5. **Deploy** (`docker compose --profile prod up -d --build`). On startup
   the scheduler does an initial push; standings then refresh within ~60s
   of each scored game.

## Notes / limits

- Sheets write quota is ~60 writes/min/user; one push per 60s tick (≤2
  `update` calls) is far under it.
- Single-worker assumption matches the leaderboard cache. If uvicorn ever
  runs `--workers>1`, each worker would push independently — move the
  `_predictions_pushed` guard to a shared store first.
- All failure modes (bad creds, network, quota) log and no-op; the score
  path is never affected.
