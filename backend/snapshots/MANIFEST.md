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

## Active reference

### `predictions-snapshot-2026-06-11.csv` *(deadline-night capture)*

| Property | Value |
|---|---|
| Captured (UTC) | 2026-06-11 21:43 — 4h 43m after the 17:00 UTC deadline |
| Source | One-off export from the all-entries Predictions data, generated at the moment all entries were locked. Originally archived to `docs/all-entries-predictions-2026-06-11.csv` and ported here on 2026-06-28. |
| Rows × cols | 166 × 187 |
| Encoding | UTF-8 with BOM (Excel-compatible) — the audit script reads via `utf-8-sig` to strip the BOM transparently. |
| SHA-256 (file as committed) | `0d5f67bbfd21378b4283fc98aee938b57f353e9ceb512e8179d6bc80ea14db37` |
| SHA-256 (LF-normalised content) | `7363bd10b476beed7e316cecb7d50bbb7eaffa3aca3d47e81fadea40fd4c11e1` |
| Audit verification (2026-06-28) | All three top-3 entries' bonus answers, champion picks, and knockout selections match the live DB exactly. |
| Context | This is the strongest available audit reference: it was generated within hours of the deadline, has been version-controlled in `docs/` since deadline night, and predates every subsequent system change (the v2.161.0 stage-rename migration, the v2.181.0 Group Stage Winner announcement, etc.). Any post-deadline tampering would show up as a CSV-vs-DB diff. |

## Why this approach (not Drive revision history)

We initially planned to fetch the earliest Google Sheet revision after
the deadline via the Drive API. A 2026-06-28 probe of the live sheet's
revision history returned only 3 revisions, all from the day of the
probe — Drive aggressively prunes revisions for frequently-edited
native Sheets, and the post-deadline snapshot we wanted had already
been removed.

Self-archiving in this directory side-steps the pruning issue
entirely. The deadline-night CSV in `docs/` happened to be exactly
what we needed; ported here, it inherits the same git-history
immutability + read-only mount the audit infrastructure provides.

## History

A mid-tournament reference (`predictions-snapshot-2026-06-28.csv`,
captured 11:13 UTC on 2026-06-28) was briefly committed under this
directory in commit `ee15fee` and superseded in the next commit when
the deadline-night CSV was discovered. The 06-28 capture remains in
git history for anyone who wants to inspect mid-tournament state but
is not the active audit reference.
