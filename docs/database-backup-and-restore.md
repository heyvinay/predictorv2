# Database backup & restore

A one-page runbook. Use this when you've taken a backup before a risky action
and want to revert, or when you need to grab a snapshot before doing one.

Production lives on the Hetzner VPS at `167.235.145.76`. The database runs
inside the `predictor-db` Docker container; user/database name are both
`predictor` (defined in `docker-compose.yml` under `db.environment`).

## Take a new backup

```bash
ssh root@167.235.145.76 'TS=$(date -u +%Y%m%dT%H%M%SZ); DEST=/root/predictor-${TS}.sql; docker exec predictor-db pg_dump -U predictor predictor > "$DEST" && ls -lh "$DEST"'
```

Drops a timestamped `.sql` file in `/root/` on the VPS. Plain-SQL format (not
custom binary), so it can be piped back through `psql` without `pg_restore`.

Typical size: ~400-600 KB for the current competition. Takes ~1 second.

## Pull a backup to your laptop (off-machine copy)

```powershell
scp root@167.235.145.76:/root/predictor-pre-disable-20260602T194810Z.sql .
```

Replace the filename with whichever backup you want to fetch. Keeping a copy
off the VPS protects against disk-level VPS failure.

## Restore from a backup

> **Warning** — full restore replaces ALL database state with the backup
> contents. Anything written since the backup is lost. For "undo a single
> admin action" prefer the targeted alternative below.

### Full restore (the nuclear option)

```bash
ssh root@167.235.145.76 <<'EOF'
# 1. Stop the backend so it releases DB connections (frontend can stay up).
docker stop predictor-backend

# 2. Drop + recreate the database. Done via the system `postgres` DB
#    because you can't DROP the database you're connected to.
docker exec predictor-db psql -U predictor -d postgres -c 'DROP DATABASE predictor;'
docker exec predictor-db psql -U predictor -d postgres -c 'CREATE DATABASE predictor OWNER predictor;'

# 3. Pipe the dump back in. EDIT THE FILENAME to whichever backup you're
#    restoring. The `-i` on `docker exec` is what enables stdin piping.
cat /root/predictor-pre-disable-20260602T194810Z.sql | docker exec -i predictor-db psql -U predictor predictor

# 4. Bring the backend back up. It'll auto-run `alembic upgrade head` on
#    startup; if the dump was taken at a different schema version, this
#    is where you'd find out. Usually a no-op.
docker start predictor-backend
EOF
```

Expected downtime: 5-15 seconds (frontend stays up; nginx returns 502 from
the backend route briefly).

### Targeted alternative — undo a single admin action

Almost always preferable to the nuclear option, because it preserves
everything else that happened after the backup.

**Via the admin UI:** open `/admin`, find the entry, click **Enable**. That
clears the `is_disabled` flag and writes a clean `entry.enabled` audit event.
This is the right answer 99% of the time after an accidental disable.

**Via SQL (only if the admin UI is broken):**

```bash
ssh root@167.235.145.76 "docker exec predictor-db psql -U predictor predictor -c \"UPDATE prediction_entries SET is_disabled=false, disabled_reason=null, disabled_at=null, disabled_by_user_id=null WHERE id='<entry-uuid>'\""
```

This skips the audit event trail — only do it if the UI path isn't an option.

## Verify a restore (or backup) is healthy

```bash
ssh root@167.235.145.76 "docker exec predictor-db psql -U predictor predictor -c 'SELECT COUNT(*) AS entries FROM prediction_entries; SELECT MAX(created_at) AS last_event FROM audit_events;'"
```

- `entries` count should match what you expect for the competition.
- `last_event` should be at or before the backup timestamp (after a restore)
  or close to *now* (during normal operation).

## Notes

- **Backups are not on a schedule.** The procedure above is manual and gets
  invoked before risky actions (admin disables, migration deploys, etc.).
  Hetzner snapshots the VPS volume periodically as a coarse safety net, but
  those are filesystem-level, not transactional Postgres backups.

- **Restore presumes the schema matches.** The dump is plain SQL with
  `CREATE TABLE` statements. If you restore an old backup into a newer
  schema version, the restored tables will be the older shape — and Alembic
  will try to upgrade them on backend boot. Usually fine, but be alert to
  startup errors after a cross-version restore.

- **The `\restrict` / `\unrestrict` markers** at the start/end of the dump
  are a Postgres 17+ security feature that blocks arbitrary backslash-commands
  during restore. Functionally invisible; just a signal the dump format is
  current.
