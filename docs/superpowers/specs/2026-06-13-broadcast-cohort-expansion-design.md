# Broadcast cohort expansion — Pool Ghost + Lapsing

**Date:** 2026-06-13
**Status:** Approved (brainstorming) — pending implementation plan
**Author:** Vinay (via brainstorming session)
**Slice:** 1 of 1 (no follow-up slice planned)

## Summary

Add two cohorts — **Pool Ghost** and **Lapsing** — to the existing
admin Broadcast Emails tool at `/admin`. Both target users who have a
submitted, eligible Phase 1 entry but have stopped engaging with the
site since the tournament kicked off on **2026-06-11 19:00 UTC** (21:00
Malta time). Predicates extend the existing `BroadcastSegment` enum +
correlated-EXISTS pattern in `backend/app/services/broadcast.py` with a
new join into `audit_events` filtered to
`event_type = 'auth.login_succeeded'`.

The Monday-morning operational ask ("which users haven't signed in?")
is satisfied by the **Pool Ghost** cohort. The **Lapsing** cohort
covers ongoing mid-tournament drop-off and starts populating from
2026-06-14 19:00 UTC onwards (when the 3-day-dormant threshold first
becomes possible).

## Scope (in)

1. New enum values `POOL_GHOST` and `LAPSING` on `BroadcastSegment`.
2. Three new predicate functions in `backend/app/services/broadcast.py`:
   - `_eligible_submitted_predicate()` — shared base, tighter than the
     existing `_has_submitted_phase_predicate()`: filters
     `is_disabled=false AND withdrawn_at IS NULL AND phase=PHASE_1 AND
     status=SUBMITTED`.
   - `_no_login_since_kickoff_predicate()` — `NOT EXISTS` against
     `audit_events` filtered to `auth.login_succeeded AND created_at >=
     TOURNAMENT_START`.
   - `_last_login_in_lapsing_window_predicate()` — composite EXISTS +
     NOT EXISTS pair: has a login between 3-7 days ago AND no login in
     the last 3 days.
3. Two new branches in `_segment_predicate()` dispatcher.
4. One new constant `TOURNAMENT_START` in `backend/app/config.py`:
   `datetime(2026, 6, 11, 19, 0, 0, tzinfo=timezone.utc)`.
5. Two new HTML email templates (alongside the three existing broadcast
   templates) — copy below.
6. Two new rows on the `/admin` Broadcast Emails card. Header copy
   updates from "three audience segments" to "five audience segments".
7. Pytest coverage for the two new cohorts and their mutual exclusivity
   with each other.

## Scope (out)

- The `/admin/insights` site-analytics page (deferred — separate spec
  if pursued).
- Cohort columns / filter chips on the `/admin/users` list page
  (deferred).
- Per-user activity expansion on `/admin/users/[id]` (deferred —
  the existing `EngagementSummary` card stays as-is).
- Engagement insights via PostHog HogQL queries for these cohorts.
  We use audit events from our own Postgres because:
  (a) the existing broadcast predicate pattern is correlated-EXISTS
  SQLAlchemy, mixing in an external async HogQL call would require a
  separate architecture, and
  (b) audit data is immune to ad-block — PostHog `$pageview` events
  are not.
- Tightening the existing `_has_submitted_phase_predicate()` to add
  the eligibility filter. Trade-off: the existing SUBMITTERS audience
  stays at its current count (140 today) instead of dropping a few.
  Per CLAUDE.md, refactors of stable Phase 1 paths require a specific
  justification — and the new predicates are explicit about their
  stricter filter, so the asymmetry is intentional and documented.
- Mutual exclusivity between SUBMITTERS and the two new cohorts. Pool
  Ghost and Lapsing are *subsets* of SUBMITTERS — an admin who sends
  both "Thank submitters" and "Wake up Pool Ghosts" will double-email
  ghosts. This is intentional: the admin picks one cohort per
  broadcast, audit log + audience-count display make mistakes
  recoverable, and the alternative (auto-excluding ghosts from
  SUBMITTERS) would silently change the existing audience count.
- No new endpoint. `GET /admin/broadcasts/audience` (the existing
  audience-counts endpoint) returns five counts after this change
  because `count_all_audiences()` iterates the `BroadcastSegment`
  enum.
- No new migration. `audit_events` already has the indexes the new
  predicates need.
- No new env var. `TOURNAMENT_START` is a code constant — changing
  it mid-tournament is a deploy with code review, not an env flip.

## Cohort definitions

| Cohort | Predicate (informal) |
|---|---|
| Pool Ghost | Has an eligible, submitted, phase-1 entry AND zero `auth.login_succeeded` events since 2026-06-11 19:00 UTC. |
| Lapsing | Has an eligible, submitted, phase-1 entry AND most recent `auth.login_succeeded` is 3-7 days ago (no login in last 3 days, at least one login 3-7 days ago). |

**Constants:**
- `TOURNAMENT_START = datetime(2026, 6, 11, 19, 0, 0, tzinfo=timezone.utc)`
- `LAPSING_FRESH_DAYS = 3`
- `LAPSING_STALE_DAYS = 7`

**Cold-start behaviour:**
- **Today (2026-06-13, ~46h into tournament):** Pool Ghost populated;
  Lapsing empty (no one can be 3-7d dormant when tournament is 2d old).
- **2026-06-14 19:00 UTC (Saturday evening, day 3):** Lapsing begins
  to populate.
- **2026-06-18 19:00 UTC (day 7):** Cohort distribution stabilises.

## Architecture

### Backend

**File touches:**

| File | Change |
|---|---|
| `backend/app/config.py` | Add `TOURNAMENT_START` UTC constant. |
| `backend/app/services/broadcast.py` | +2 enum values, +3 predicate fns, +2 dispatcher branches. |
| `backend/app/services/broadcast.py` (templates) OR `email.py` | +2 email-body builders, mirroring the existing three. (Exact file confirmed during implementation.) |
| `backend/tests/test_broadcast*.py` | +3 pytest cases (Pool Ghost predicate, Lapsing predicate, mutual exclusivity). |

**Predicate sketch** (final code lives in `broadcast.py`):

```python
def _eligible_submitted_predicate():
    return (
        select(PredictionEntry.id)
        .join(
            PredictionEntryPhase,
            PredictionEntryPhase.entry_id == PredictionEntry.id,
        )
        .where(PredictionEntry.user_id == User.id)
        .where(PredictionEntry.is_disabled.is_(False))
        .where(PredictionEntry.withdrawn_at.is_(None))
        .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
        .where(PredictionEntryPhase.phase == PredictionPhase.PHASE_1)
        .exists()
    )


def _no_login_since_kickoff_predicate():
    return ~(
        select(AuditEvent.id)
        .where(AuditEvent.user_id == User.id)
        .where(AuditEvent.event_type == "auth.login_succeeded")
        .where(AuditEvent.created_at >= TOURNAMENT_START)
        .exists()
    )


def _last_login_in_lapsing_window_predicate():
    cutoff_fresh = utc_now() - timedelta(days=LAPSING_FRESH_DAYS)
    cutoff_stale = utc_now() - timedelta(days=LAPSING_STALE_DAYS)
    has_in_window = (
        select(AuditEvent.id)
        .where(AuditEvent.user_id == User.id)
        .where(AuditEvent.event_type == "auth.login_succeeded")
        .where(AuditEvent.created_at >= cutoff_stale)
        .where(AuditEvent.created_at < cutoff_fresh)
        .exists()
    )
    no_fresh = ~(
        select(AuditEvent.id)
        .where(AuditEvent.user_id == User.id)
        .where(AuditEvent.event_type == "auth.login_succeeded")
        .where(AuditEvent.created_at >= cutoff_fresh)
        .exists()
    )
    return has_in_window & no_fresh


# In _segment_predicate():
if segment == BroadcastSegment.POOL_GHOST:
    return (
        _eligible_submitted_predicate()
        & _no_login_since_kickoff_predicate()
    )
if segment == BroadcastSegment.LAPSING:
    return (
        _eligible_submitted_predicate()
        & _last_login_in_lapsing_window_predicate()
    )
```

**Why `utc_now()` at predicate-build time** (not SQL-side `NOW()`): the
cutoff is stable within a single request, and pinning to a Python-side
helper aligns with the project's existing test patterns (`utc_now()`
is mockable in pytest; SQL `NOW()` is not).

### Frontend

**File touches:**

| File | Change |
|---|---|
| `frontend/src/lib/api/admin.ts` | Mirror the two new enum values. |
| `frontend/src/routes/admin/+page.svelte` (broadcast card) | +2 rows in the segments list; update header text "three" → "five"; add small "Audience refreshes on page load" caption under the new cohort buttons. |

**No new component, no new endpoint, no new type files.** The broadcast
card already iterates a segments array (or equivalent — confirmed at
implementation). Adding two rows is data-only.

**Row ordering:** new cohorts at bottom, Pool Ghost above Lapsing
(Monday's priority order).

**Labels (approved during brainstorming):**
- "Wake up Pool Ghosts" — Pool Ghost row
- "Pull back lapsing players" — Lapsing row

**Audience refresh note:** small caption under the Pool Ghost row only:
*"Audience refreshes on page load. Re-open `/admin` for a fresh count."*
Pool Ghost is a *shrinking* cohort (people leave it as they log in), so
stale counts are a real risk. The existing cohorts are slow-changing
and don't need this note.

### Email templates

**Pool Ghost — minimal personalization (option A from §4):**

```
Subject: Your World Cup picks are still alive

Hi {{name}},

The tournament kicked off Wednesday night and your entry is in the
pool — but we haven't seen you back since the deadline.

Two games into the group stage, the leaderboard is already shifting.
Come take a look at how your picks are doing:

  [View my entry] → https://wc26.heyvinay.com/results

A friendly reminder that group-stage matches are paying out daily,
so today's a good day to peek in. You can also check the leaderboard
to see where you stand vs. the rest of the pool.

Catch you on the touchline,
The Predictor
```

**Lapsing — rank-personalized (option B from §4):**

```
Subject: Don't lose your edge — matchday is coming up

Hi {{name}},

You haven't been around for a few days, and the tournament is heating
up.

You're currently {{rank}}th on the leaderboard.

  [See the latest results] → https://wc26.heyvinay.com/results

Stay sharp,
The Predictor
```

The Lapsing template needs one extra per-recipient lookup at send time:
the user's current rank from the cached leaderboard
(`get_cached_leaderboard()` or equivalent). One small extra query in
the send loop. If the leaderboard cache is empty (early-tournament
edge case), the template skips the rank line gracefully and reads
"You're still in the running on the leaderboard."

**No phase language anywhere** in the bodies, subjects, or CTAs (per
CLAUDE.md "no Phase 1 / Phase 2 in user-facing copy" invariant).

## Audit, safety, testing

**Audit (reused):**
- `admin.broadcast_sent` fires once per send. New segments inherit
  automatically. `/admin/audit` shows
  `admin.broadcast_sent · segment=pool_ghost · recipient_count=N ·
  sender=<admin>`.

**Safety:**

| Concern | Mitigation |
|---|---|
| Double-send | Existing confirmation modal with audience count + sample of 5. |
| Send-to-disabled / withdrawn | `_eligible_submitted_predicate()` excludes both. |
| Wrong `TOURNAMENT_START` | Named constant in `config.py`; audience counts in the UI surface a misconfiguration before send. |
| RESEND_API_KEY missing in dev | Existing dev-fallback prints to backend logs. Inherited. |
| Stale Pool Ghost audience | "Refreshes on page load" caption under the new button. |

**Pytest cases** (`backend/tests/test_broadcast*.py`):

```python
async def test_pool_ghost_excludes_users_with_login_since_kickoff(session):
    # A: submitted entry, logged in after kickoff → NOT in cohort
    # B: submitted entry, no login since kickoff → IN cohort
    # C: never submitted → NOT in cohort (eligibility)
    # D: submitted but is_disabled=True → NOT in cohort (eligibility)
    ...

async def test_lapsing_uses_3_to_7_day_window(session):
    # A: last login 1d ago → NOT lapsing (fresh)
    # B: last login 5d ago → IN cohort
    # C: last login 10d ago → NOT lapsing (graduates to Pool Ghost)
    # D: never logged in → NOT lapsing (Pool Ghost)
    ...

async def test_pool_ghost_and_lapsing_mutually_exclusive(session):
    # Same DB state, query both segments; assert intersection is empty.
    ...
```

**Test conventions to follow:**
- Use `utc_now()` for time fixtures (project's TZ rule).
- Construct test datetimes with `datetime(..., tzinfo=timezone.utc)`
  — aiosqlite strips tzinfo on read, so the predicate must coerce
  defensively (`aware_utc()` helper) where it compares.

**No frontend test required.** Two new rows in an iterating loop;
existing component tests still pass.

## Open questions resolved during brainstorming

1. **Cohort set granularity** — landed on 2 new cohorts (Pool Ghost +
   Lapsing) rather than the original 5-cohort segmentation matrix.
   Power user / Engaged / Non-participant are *observational*, not
   actionable broadcast targets; they belong on a future
   `/admin/insights` page (out of scope here).
2. **Entry filter** — eligible (option A from §5 brainstorming):
   `is_disabled=false AND withdrawn_at IS NULL AND status=SUBMITTED
   AND phase=PHASE_1`.
3. **Anchor** — Pool Ghost anchored to kickoff (one-shot semantics);
   Lapsing rolling 3-7d window (ongoing semantics).
4. **Personalization level** — Pool Ghost minimal (option A: name +
   CTA only); Lapsing rank-personalized (option B: name + rank + CTA).
5. **Mutual exclusivity** — not enforced between SUBMITTERS and the
   two new cohorts. Admin picks one cohort per broadcast.
6. **Tournament start anchor** — pinned to 2026-06-11 19:00 UTC (21:00
   Malta CEST).

## Out-of-scope follow-up ideas (NOT in this spec)

These came up during brainstorming and are *not* part of this slice.
Filing them here for future reference only:

- `/admin/insights` page: site-wide page/feature analytics dashboard
  (top pages, top events, time-series, funnels).
- Cohort column on `/admin/users` list page with filter chips.
- Per-user activity expansion on `/admin/users/[id]` (rich page-list
  + click breakdown beyond the existing 4-field summary).
- Power-user / Engaged / Non-participant observational cohorts.
- Group-stage-winners celebratory broadcast cohort (revisit ~Day 12).
- Tightening the existing `_has_submitted_phase_predicate()` to add
  eligibility filtering (CLAUDE.md "skip Phase 2 paths" rule applies).
- Toast notifications driven by cohort membership.

## Versioning

This is a minor (capability-adding) release per the bump rule in
CLAUDE.md.

- Frontend `package.json` and `package-lock.json`: bump minor.
- Backend `pyproject.toml`: bump minor.
- `frontend/src/lib/data/changelog.json`: append entry of type
  `feature` summarising "Two new cohorts on the broadcast email tool
  — re-engage players who haven't logged in since kickoff."

## Risks

- **Pool Ghost count on day 3 includes legitimate-vacation users** —
  someone who submitted on the deadline and went on holiday is flagged
  as a ghost on day 3 even though they always intended to come back.
  Mitigation: the email copy is friendly, not accusatory. If this
  proves to be a real annoyance, a follow-up could add a
  `min_tournament_age_days = 5` grace period before Pool Ghost can
  fire.
- **Lapsing under-counts on the first send** — because the 3-7d window
  only fills in from day 3 onward, the first time the admin sends
  Lapsing the audience may be artificially small. Not a bug, just
  worth knowing on day 4.
- **The "ghost zone" forms from day 8+** — Pool Ghost is anchored to
  kickoff, which means a user who logged in once at kickoff and then
  drifted away leaves the cohort permanently for this tournament.
  Once their last-login is past the 7d Lapsing window (day 8+), they
  fall into a third bucket — neither Pool Ghost nor Lapsing. Today
  this zone is empty (tournament is 2d old; everyone with a post-
  kickoff login is in the Lapsing-or-fresh window). As of day 8+
  (2026-06-18) it begins to form. Mitigation, if it becomes a real
  gap: switch Pool Ghost from "no login since kickoff" to a rolling
  "no login in last 7 days" window in a follow-up. Both definitions
  converge today (tournament age < 7d) so we're not losing precision
  by deferring the call.
- **Audit-events table growth** — adding `WHERE event_type =
  'auth.login_succeeded' AND created_at >= X` for every cohort
  predicate evaluation is two index lookups per user. With ~100 users
  in the pool and ~1 evaluation per `/admin` page load, this is
  negligible. Worth re-checking if the pool grows past ~1,000.
- **Tournament-start constant drift** — if the next tournament reuses
  the system without updating `TOURNAMENT_START`, Pool Ghost would
  immediately empty out (everyone's `auth.login_succeeded` is >=
  start). The cohort-count display surfaces this before send.
