# KO Live Score: Slot-Placeholder Team Name Resolution

**Date:** 2026-07-01  
**Status:** Approved for implementation  
**Version target:** patch (fix)

---

## Problem

Knockout fixtures in the database hold slot-placeholder team names
(`slot:round_of_32:537426:home`) until Football-Data.org backfills the
official team names after the preceding round completes. The KO lineup
resolver handles these at **read time** in the API layer — it resolves them
for display but never writes the real names back to `fixtures.home_team /
away_team`.

This causes two related live-scoring failures during KO matches:

### 1. ESPN score matching fails for slot-placeholder fixtures

`EspnScoreProvider` sets `ExternalScore.external_id = ""`. The
`_find_fixture` function tries `external_id` first (skipped — empty string),
then falls back to an exact `home_team / away_team` match. Since
`"England" ≠ "slot:round_of_32:537426:home"`, no fixture is found and the
ESPN event is silently dropped.

The score only arrives via the FD per-fixture resolution pass (~60 seconds
later), which matches by `external_id` (FD match ID). Live users see "no
score" for the first 60 seconds after kickoff, and the matchday pill shows
"WED · 18:00" rather than a live score or minute counter.

### 2. Match minute is null during KO play

`MatchdayPill.svelte` shows `{fixture.minute}'` when `fixture.minute != null`,
otherwise "LIVE". ESPN reliably provides `displayClock` (→ `parse_minute()`),
but since ESPN can't match slot-placeholder fixtures (issue 1), it never
writes the minute. FD's per-fixture fetch does include `minute` in its
response, but FD does not consistently populate it for every in-play tick.
The result: the pill shows "LIVE" rather than "52'" throughout the match.

Both issues share the same root cause: **the fixture row's team names are
still placeholders when ESPN's live bulk response arrives**.

---

## Fix

### Approach: Write team names back on first successful FD resolution

When the FD resolution pass successfully fetches a fixture by `external_id`
and the fixture still holds slot-placeholder team names, write the real team
names back to the `fixtures` row in the same transaction as the score write.

**Why this is correct:**
- The resolver's invariant in CLAUDE.md states: "DB rows stay untouched —
  when Football-Data eventually backfills FIFA's official lineup, the
  resolver becomes a no-op (placeholder no longer matches)." Our write-back
  IS the backfill — it performs exactly what the resolver was waiting for.
  Once the real name is in the row, the resolver's `startswith('slot:')`
  check correctly returns no match (the row is already resolved).
- The write happens atomically with the score row — no partial state.
- `_find_fixture` continues to work unchanged: after the first FD resolution
  tick, ESPN matches by team name on every subsequent tick.

**Discriminant:** FD sets `ExternalScore.external_id = str(fd_match_id)`
(non-empty). ESPN sets it to `""`. So `bool(ext.external_id)` reliably
identifies FD-originated scores, meaning the write-back only fires in the
resolution pass, never from ESPN's live bulk response.

---

## Implementation

### `backend/app/services/score_sync.py` — `_apply_external_score`

After `_find_fixture` succeeds and before the demotion guard, add a
slot-name write-back block:

```python
# If this score came from Football-Data (has external_id) and the fixture
# still holds slot-placeholder team names, write the real names back so
# ESPN's team-name fallback can match from the next tick onward.
if ext.external_id:
    if fixture.home_team and fixture.home_team.startswith("slot:") and ext.home_team:
        fixture.home_team = ext.home_team
    if fixture.away_team and fixture.away_team.startswith("slot:") and ext.away_team:
        fixture.away_team = ext.away_team
```

Place this block **before** the `score.verified` early-return guard. Even if
the score itself is skipped (admin-verified), the team-name write-back should
still fire — the team names are independent of score verification.

Precise placement in the function:

```python
async def _apply_external_score(...):
    fixture = await _find_fixture(session, competition_id, ext)
    if fixture is None:
        return None

    # ── NEW: write real team names back from FD so ESPN can match next tick ──
    if ext.external_id:
        if fixture.home_team and fixture.home_team.startswith("slot:") and ext.home_team:
            fixture.home_team = ext.home_team
        if fixture.away_team and fixture.away_team.startswith("slot:") and ext.away_team:
            fixture.away_team = ext.away_team
    # ── end new ──

    score_q = await session.execute(...)
    score = ...
    if score is not None and score.verified:
        result.skipped_verified += 1
        return fixture.id
    # ... rest unchanged
```

No other files need changes.

---

## Effect on minute display

Once ESPN can match the fixture (from tick 2 onward), `ext.minute` is
populated from `parse_minute(displayClock)` and written to `fixture.minute`
by the existing `fixture.minute = ext.minute` line in `_apply_external_score`.
The frontend's `MatchdayPill.svelte` already handles
`fixture.minute != null ? \`${fixture.minute}'\` : 'LIVE'` — no frontend
changes required.

**Residual gap (accepted):** On the very first score-sync tick after kickoff,
the FD resolution pass fires and may or may not return a `minute` value from
FD's API (FD is inconsistent). Users may see "LIVE" without a minute counter
for the first ~60 seconds. From the second tick onward, ESPN matches and the
minute counter appears. This is acceptable — showing "LIVE" is correct and
the minute counter arrives within one poll cycle.

---

## Sequence of events (post-fix)

```
T+0  Kickoff
T+0  Tick 1 — ESPN bulk response arrives:
         _find_fixture("England", home_team="slot:...") → None
         ESPN event dropped (unchanged from today)
     Tick 1 — FD resolution pass (fixture is SCHEDULED, kickoff in past):
         _find_fixture(external_id="537426") → fixture ✓
         home_team / away_team written back: "England" / "Congo DR"
         Score + status + maybe minute written
T+60 Tick 2 — ESPN bulk response arrives:
         _find_fixture("England", home_team="England") → fixture ✓
         Score, status, minute written from ESPN's live feed
T+120 ... every tick, ESPN provides minute counter reliably
```

Compare to today where FD resolution is the only path for the entire match
duration and minute is unreliable throughout.

---

## No-op safety

If Football-Data eventually backfills FIFA's official team names into the
`fixtures` rows before this fix runs (e.g., the team name was already written
by a prior deploy), the `startswith("slot:")` guard means the write-back does
nothing. The logic is idempotent.

---

## Testing

### New test: `backend/tests/test_score_sync.py`

`test_slot_placeholder_team_name_written_back_on_fd_resolution`

Setup:
- Fixture with `home_team = "slot:round_of_32:537426:home"`, `external_id = "537426"`, status SCHEDULED, kickoff in past
- FD resolution returns `ExternalScore(external_id="537426", home_team="England", away_team="Congo DR", status=LIVE, ...)`
- Call `_apply_external_score`

Assert:
- `fixture.home_team == "England"`
- `fixture.away_team == "Congo DR"`

`test_slot_placeholder_not_written_on_espn_event`

Setup:
- Same fixture
- ESPN returns `ExternalScore(external_id="", home_team="England", ...)`
- Call `_apply_external_score`

Assert:
- `fixture.home_team` still starts with `"slot:"` (no match → None returned before write-back)
- Actually: `_find_fixture` returns `None` for ESPN events (team-name match fails), so
  `_apply_external_score` returns `None` before reaching the write-back block. Assert return value is `None`.

`test_verified_score_still_updates_team_names`

Setup:
- Fixture with slot-placeholder names; existing verified Score row
- FD resolution returns real team names
- Call `_apply_external_score`

Assert:
- `fixture.home_team` and `fixture.away_team` updated (write-back fires before the verified guard)
- `result.skipped_verified == 1` (score not overwritten — admin lock respected)

---

## Files changed

| File | Change |
|---|---|
| `backend/app/services/score_sync.py` | ~8 lines added in `_apply_external_score` |
| `backend/tests/test_score_sync.py` | 3 new test cases |

---

## Out of scope

- Writing team names from ESPN (ESPN has no external_id to match by; FD path is sufficient)
- Making FD return a consistent `minute` (FD API limitation; ESPN handles this from tick 2)
- Any frontend changes (MatchdayPill already handles null minute correctly)
- Writing team names from the live bulk ESPN pass (would require a separate fixture lookup
  by canonical name, adding a DB query per ESPN event per tick — not warranted given the
  one-tick delay is acceptable)
