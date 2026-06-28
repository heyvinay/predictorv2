# Audit reference snapshots

Frozen-in-time references for [`backend/scripts/audit_top3_v2.py`](../scripts/audit_top3_v2.py)
step 4 (comparison of the live DB against an independent published copy
of the predictions). The audit reports tampering as **any difference**
between the live DB and the snapshot.

## Immutability contract

These files are written once and never modified after capture. Their
authority comes from being committed at a specific git commit — any
subsequent edit shows up as a diff in version control and breaks the
file's referenced SHA-256 below.

**Do not regenerate an existing snapshot.** To capture a newer reference
point, create a NEW dated file alongside the old ones and update
`_SNAPSHOT_PATH` in `audit_top3_v2.py` to point at it. The old snapshot
stays so historical audits can re-run against the original reference.

The `:ro` flag on the docker-compose volume mount enforces this at
runtime: nothing inside the container can write to `/app/snapshots/`.

## Files

### `predictions-snapshot-2026-06-28.csv`

| Property | Value |
|---|---|
| Captured (UTC) | 2026-06-28 ~11:14 |
| Source | Live `Predictions` worksheet of `GOOGLE_SHEET_ID 1-UZTOYQh0jIUuMw7VarsXdj8a3gPC3whVwii61ZS75Y` |
| Mechanism | One-shot `dump_sheet_to_csv.py` via gspread on the prod backend container |
| Rows × cols | 167 × 371 |
| SHA-256 (file as committed) | `58623d46ba0c30c3e233394064a7f9129839901248e33045fcbeddf90c93b518` |
| SHA-256 (LF-normalised content) | `9575e5fd05fd085fcaa8f4c7702db3ffabf91270dd2f8d17e29812bcbde17944` |
| Context | First snapshot. Captures the post-group-stage state, two days after the v2.181.0 group-stage winner announcement (2026-06-26). Predictions have been locked since the deadline (2026-06-11) so no legitimate change can have occurred after this capture. |

## Why this approach (not Drive revision history)

We initially planned to fetch the earliest Google Sheet revision after
the deadline via the Drive API. A 2026-06-28 probe of the live sheet's
revision history returned only 3 revisions, all from the day of the
probe — Drive aggressively prunes revisions for frequently-edited
native Sheets, and the post-deadline snapshot (the very first
sheets_sync push at 2026-06-15 09:39 UTC) had already been removed.

Self-archiving in this directory side-steps the pruning issue: git
history is the immutability mechanism, the file is mounted read-only
into the backend container, and the SHA-256s above are part of the
manifest so accidental corruption shows up immediately.
