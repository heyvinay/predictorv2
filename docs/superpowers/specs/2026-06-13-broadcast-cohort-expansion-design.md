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
Malta time).

**Engagement signal: hybrid (option A + B).** Engagement is measured
by combining two sources:

1. **Primary — `User.last_seen_at` column** (new). Updated by the
   `CurrentUser` dependency on every authenticated request, throttled
   to once per 5 minutes per user. Reliable, ad-block-immune, no
   external API.
2. **Fallback — PostHog `$pageview` events**. Best-effort lookup via
   the existing `posthog_read.py` service. If PostHog is unreachable,
   rate-limited, or mis-configured, the engagement signal degrades
   gracefully to A alone — the request path NEVER raises an error
   visible to the user.

A user is "engaged since kickoff" if EITHER signal shows activity
since `TOURNAMENT_START`. Pool Ghost = submitted-eligible AND NOT
engaged. Lapsing = submitted-eligible AND most-recent engagement
signal (max of both sources) is between 3 and 7 days ago.

The previous draft of this spec used `auth.login_succeeded` audit
events as the signal — that approach was rejected during brainstorming
because session-cookie holders don't fire login events on revisit, so
the vast majority of active users would be misclassified as ghosts.

## Scope (in)

1. **New column** `User.last_seen_at: datetime | None` with backing
   migration. Backfill: `COALESCE(MAX(audit_events.created_at WHERE
   actor_user_id = users.id), users.created_at)`.
2. **`CurrentUser` dependency update** — throttled write of
   `last_seen_at` once per 5 minutes of activity per user.
3. **New enum values** `POOL_GHOST` and `LAPSING` on
   `BroadcastSegment`.
4. **New predicate factory** in `broadcast.py` — predicates for the
   two new cohorts are *built per-request* with optional PostHog
   engagement data, instead of being static SQLAlchemy expressions.
   The existing three predicates (SUBMITTERS / NO_ENTRY /
   DRAFT_HOLDERS) stay static — they don't need engagement data.
5. **Two new branches** in `_segment_predicate()` dispatcher.
6. **New helper** in `posthog_read.py`:
   `get_last_pageview_for_users_since(timestamp) -> dict[UUID,
   datetime]`. Returns each active user's MAX(`$pageview`.timestamp)
   since the cutoff. Empty dict on any failure (silent degradation).
7. **One new constant** `TOURNAMENT_START` in
   `backend/app/config.py`: `datetime(2026, 6, 11, 19, 0, 0,
   tzinfo=timezone.utc)`.
8. **Two new HTML email templates** alongside the three existing
   broadcast templates — copy below.
9. **Two new rows** on the `/admin` Broadcast Emails card. Header
   copy updates from "three audience segments" to "five audience
   segments".
10. **Pytest coverage** for the two new cohorts including:
    - Pool Ghost membership rules across both signal sources.
    - Lapsing membership rules with max-of-signals timing.
    - Silent PostHog-failure degraded mode (empty fallback dict →
      column-only behaviour, no exception propagated).
    - Mutual exclusivity between Pool Ghost and Lapsing.

## Scope (out)

- The `/admin/insights` site-analytics page (a separate spec).
- Cohort columns / filter chips on the `/admin/users` list page
  (deferred).
- Per-user activity expansion on `/admin/users/[id]` (deferred —
  the existing `EngagementSummary` card stays as-is for now; this
  card may benefit from reading `last_seen_at` as a follow-up).
- Tightening the existing `_has_submitted_phase_predicate()` to add
  eligibility filtering. The existing SUBMITTERS audience stays at
  its current count (140 today) instead of dropping a few. The new
  predicates are explicit about their stricter filter, so the
  asymmetry is intentional and documented.
- Mutual exclusivity between SUBMITTERS and the two new cohorts.
  Pool Ghost and Lapsing are *subsets* of SUBMITTERS — an admin who
  sends both "Thank submitters" and "Wake up Pool Ghosts" will
  double-email ghosts. This is intentional: the admin picks one
  cohort per broadcast, audit log + audience-count display make
  mistakes recoverable, and the alternative (auto-excluding ghosts
  from SUBMITTERS) would silently change the existing audience count.
- No new endpoint. `GET /admin/broadcasts/audience` (the existing
  audience-counts endpoint) returns five counts after this change
  because `count_all_audiences()` iterates the `BroadcastSegment`
  enum.
- No new env var. `TOURNAMENT_START` is a code constant — changing
  it mid-tournament is a deploy with code review, not an env flip.

## Engagement signal — the core architecture

### Why hybrid (A + B) and not either alone

| Signal | Catches | Misses |
|---|---|---|
| **A — `User.last_seen_at` column** | Every authenticated request that resolves the session cookie (page loads, API calls, anything that touches `CurrentUser`) | Pure client-side navigation that doesn't hit the backend (heavy SvelteKit caching could lag the column) |
| **B — PostHog `$pageview` HogQL** | Every browser navigation (including SPA-style transitions that don't hit the backend) | ~25% of users with ad-blockers; DNT users (zero PostHog events) |
| **A + B (OR)** | Either signal indicates engagement | Only: ad-blocker users who *also* navigate exclusively client-side — vanishingly small set |

A alone has the small "SPA navigation" gap. B alone has the
ad-blocker gap. Together they cover essentially all active users. The
spec uses A as the primary (column-driven, always reliable) and B as
the fallback that closes the SPA-navigation gap, with PostHog
failures degrading silently to A-only behaviour.

### Silent PostHog failure — invariant

**Hard rule:** if any PostHog query fails — timeout, network error,
non-2xx response, malformed JSON, missing env vars — the broadcast
endpoint MUST:

1. **Never raise** into the request path. The existing
   `posthog_read.py` pattern (return None / empty on failure, log at
   WARNING) is the contract.
2. **Never surface an error to the user**. No toast, no error pill,
   no broken UI state. The audience-count badge shows a number;
   that number is computed from `last_seen_at` alone.
3. **Continue to function** as if PostHog didn't exist. Pool Ghost
   and Lapsing fall back to A-only semantics, which is strictly
   correct (just narrower coverage). No UX hint that anything is
   degraded.

The pytest suite has a dedicated `test_posthog_failure_degrades_silently`
case asserting this contract: PostHog client returns `{}`, predicate
factory completes without raising, cohort membership is computed
from the column alone.

## Cohort definitions

| Cohort | Predicate (informal) |
|---|---|
| **Pool Ghost** | submitted-eligible AND last engagement signal (max of A + B sources) is < TOURNAMENT_START (or absent on both sides). |
| **Lapsing** | submitted-eligible AND last engagement signal (max of A + B sources) is between 3 and 7 days ago (no signal in last 3 days, at least one signal in 3-7d window). |

**Constants:**
- `TOURNAMENT_START = datetime(2026, 6, 11, 19, 0, 0, tzinfo=timezone.utc)`
- `LAST_SEEN_THROTTLE_S = 300` (5-minute write throttle)
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
| `backend/app/models/user.py` | Add nullable `last_seen_at` column. |
| `backend/alembic/versions/<new>_user_last_seen_at.py` | Migration: add column + backfill from audit_events + created_at. |
| `backend/app/dependencies.py` | `CurrentUser` dep updates `last_seen_at` on each request, throttled to 5 min. |
| `backend/app/services/broadcast.py` | +2 enum values, +1 engagement-input helper, +2 predicate factories, +2 dispatcher branches. |
| `backend/app/services/posthog_read.py` | +`get_last_pageview_for_users_since()` helper. |
| `backend/app/services/broadcast.py` (templates) OR `email.py` | +2 email-body builders. |
| `backend/tests/test_broadcast*.py` | +4 pytest cases (Pool Ghost, Lapsing, silent PostHog failure, mutual exclusivity). |
| `backend/tests/test_dependencies.py` | +1 pytest case (throttled last_seen_at write). |
| `backend/tests/test_posthog_read.py` | +1 pytest case (new helper). |

**Migration sketch** (new Alembic revision):

```python
def upgrade():
    op.add_column(
        "users",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill from audit_events.MAX(created_at) per user, fall back to
    # User.created_at for users with zero audit rows.
    op.execute("""
        UPDATE users
        SET last_seen_at = COALESCE(
            (SELECT MAX(ae.created_at)
               FROM audit_events ae
              WHERE ae.actor_user_id = users.id),
            users.created_at
        )
    """)


def downgrade():
    op.drop_column("users", "last_seen_at")
```

The backfill gives every existing user a defensible starting value.
After the deploy, the dependency starts updating the column on each
authenticated request.

**`CurrentUser` dependency change:**

```python
# backend/app/dependencies.py

LAST_SEEN_THROTTLE_S = 300  # 5 minutes

async def get_current_user(
    session: DbSession,
    ...  # existing args
) -> User:
    user = ...  # existing session-cookie validation

    # Throttled write — 99%+ of requests skip this in steady state.
    now = utc_now()
    if user.last_seen_at is None or (now - user.last_seen_at).total_seconds() > LAST_SEEN_THROTTLE_S:
        user.last_seen_at = now
        await session.commit()

    return user
```

**Predicate factory pattern** (broadcast.py):

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from app.config import TOURNAMENT_START, LAPSING_FRESH_DAYS, LAPSING_STALE_DAYS
from app.services import posthog_read
from app.models._datetime import utc_now


@dataclass(frozen=True)
class EngagementInput:
    """One-shot engagement-signal snapshot for the new cohort predicates.

    posthog_last_seen[user_id] is the user's MAX($pageview.timestamp) over
    the lookback window. Empty dict ⇒ PostHog unreachable; predicates
    degrade to last_seen_at-only.
    """
    posthog_last_seen: dict[UUID, datetime]


async def _build_engagement_input() -> EngagementInput:
    """Best-effort PostHog fetch. Catches every failure, logs at WARNING,
    returns empty dict so predicates fall back to column-only.
    """
    try:
        ph = await posthog_read.get_last_pageview_for_users_since(
            TOURNAMENT_START - timedelta(days=14)
        )
    except Exception as exc:  # noqa: BLE001 — explicit silent degradation
        logger.warning("PostHog engagement fetch failed; degrading to column: %s", exc)
        ph = {}
    return EngagementInput(posthog_last_seen=ph)


def _pool_ghost_predicate(eng: EngagementInput):
    """Eligible-submitted AND no engagement signal since kickoff (either source)."""
    column_active = User.last_seen_at >= TOURNAMENT_START
    posthog_active_ids = [
        uid for uid, ts in eng.posthog_last_seen.items()
        if ts >= TOURNAMENT_START
    ]
    posthog_active = User.id.in_(posthog_active_ids) if posthog_active_ids else literal(False)
    return _eligible_submitted_predicate() & ~(column_active | posthog_active)


def _lapsing_predicate(eng: EngagementInput):
    """Eligible-submitted AND last signal (max of A + B) in [3d, 7d) ago."""
    now = utc_now()
    fresh_cutoff = now - timedelta(days=LAPSING_FRESH_DAYS)
    stale_cutoff = now - timedelta(days=LAPSING_STALE_DAYS)

    # SQL-side: User.last_seen_at filters
    col_in_window = (User.last_seen_at >= stale_cutoff) & (User.last_seen_at < fresh_cutoff)
    col_fresh = User.last_seen_at >= fresh_cutoff

    # PostHog-side: enumerate user_ids whose MAX(pageview) is in window / fresh
    ph_in_window_ids = [
        uid for uid, ts in eng.posthog_last_seen.items()
        if stale_cutoff <= ts < fresh_cutoff
    ]
    ph_fresh_ids = [
        uid for uid, ts in eng.posthog_last_seen.items()
        if ts >= fresh_cutoff
    ]
    ph_in_window = User.id.in_(ph_in_window_ids) if ph_in_window_ids else literal(False)
    ph_fresh = User.id.in_(ph_fresh_ids) if ph_fresh_ids else literal(False)

    # Lapsing ⇔ (any source in window) AND (no source is fresh)
    return (
        _eligible_submitted_predicate()
        & (col_in_window | ph_in_window)
        & ~(col_fresh | ph_fresh)
    )
```

**Why `utc_now()` at predicate-build time:** the cutoff is stable
within a single request, and a Python-side helper is mockable in
pytest (SQL `NOW()` is not).

**Predicate factories vs static predicates:** the existing three
predicates (SUBMITTERS / NO_ENTRY / DRAFT_HOLDERS) don't need
engagement input — they remain static. The dispatcher branches on
whether the segment needs engagement data:

```python
async def _segment_predicate(segment: BroadcastSegment):
    # Static path — no engagement input needed
    if segment in (BroadcastSegment.SUBMITTERS, BroadcastSegment.NO_ENTRY, BroadcastSegment.DRAFT_HOLDERS):
        return _static_segment_predicate(segment)
    # Hybrid path — fetch engagement input, then build predicate
    eng = await _build_engagement_input()
    if segment == BroadcastSegment.POOL_GHOST:
        return _pool_ghost_predicate(eng)
    if segment == BroadcastSegment.LAPSING:
        return _lapsing_predicate(eng)
    raise ValueError(...)
```

`count_audience()` and `query_audience()` become `async def`
internally where they weren't before for the engagement-dependent
segments. The existing three paths stay sync.

### `posthog_read.py` extension

```python
async def get_last_pageview_for_users_since(
    cutoff: datetime,
) -> dict[UUID, datetime]:
    """Return MAX($pageview.timestamp) per distinct_id since cutoff.

    Used by the broadcast-cohort engagement signal. Best-effort: any
    failure (PostHog unreachable, rate-limited, mis-configured, malformed
    response) returns {} and logs at WARNING. Callers MUST tolerate
    empty result and degrade gracefully — this function is on the
    user-visible request path.
    """
    cfg = _config()
    if cfg is None:
        return {}
    # HogQL: SELECT distinct_id, MAX(timestamp) FROM events
    # WHERE event = '$pageview' AND timestamp >= '...'
    # GROUP BY distinct_id
    query = (
        f"SELECT distinct_id, max(timestamp) AS last_seen "
        f"FROM events "
        f"WHERE event = '$pageview' "
        f"AND timestamp >= '{cutoff.isoformat()}' "
        f"GROUP BY distinct_id"
    )
    rows = await _hogql(query)
    if rows is None:
        return {}
    out: dict[UUID, datetime] = {}
    for row in rows:
        try:
            out[UUID(str(row[0]))] = row[1]
        except (ValueError, IndexError, TypeError):
            continue
    return out
```

The pattern mirrors `get_recent_seen_for_users` exactly — same TTL
cache (5-minute batch), same silent-failure semantics.

### Frontend

**File touches:**

| File | Change |
|---|---|
| `frontend/src/lib/api/admin.ts` | Mirror the two new enum values. |
| `frontend/src/routes/admin/+page.svelte` (broadcast card) | +2 rows in segments list; header text "three" → "five"; small "Audience refreshes on page load" caption under the Pool Ghost row. |

**No new component, no new endpoint, no new type files.** The
broadcast card already iterates a segments array; adding two rows is
data-only.

**Row ordering:** new cohorts at bottom, Pool Ghost above Lapsing
(Monday's priority order).

**Labels (approved during brainstorming):**
- "Wake up Pool Ghosts" — Pool Ghost row.
- "Pull back lapsing players" — Lapsing row.

**Audience-refresh note:** small caption under the Pool Ghost row only.
Pool Ghost is a *shrinking* cohort (people leave it as they log in),
so stale counts are a real risk. The existing cohorts are slow-changing
and don't need this note.

### Email templates

**Pool Ghost — minimal personalization (option A from brainstorming §4):**

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

**Lapsing — rank-personalized (option B from brainstorming §4):**

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

The Lapsing template needs one extra per-recipient lookup at send
time: the user's current rank from the cached leaderboard
(`get_cached_leaderboard()` or equivalent). If the cache is empty
(early-tournament edge case), the template skips the rank line
gracefully and reads "You're still in the running on the leaderboard."

**No phase language anywhere** in the bodies, subjects, or CTAs (per
the CLAUDE.md "no Phase 1 / Phase 2 in user-facing copy" invariant).

## Audit, safety, testing

**Audit (reused):**
- `admin.broadcast_sent` fires once per send. New segments inherit
  automatically.
- The `last_seen_at` write does NOT emit an audit event (would
  flood the log). The column update IS the engagement record.

**Safety:**

| Concern | Mitigation |
|---|---|
| Double-send | Existing confirmation modal with audience count + sample of 5. |
| Send-to-disabled / withdrawn | `_eligible_submitted_predicate()` excludes both. |
| Wrong `TOURNAMENT_START` | Named constant in `config.py`; audience counts in the UI surface a misconfiguration before send. |
| RESEND_API_KEY missing in dev | Existing dev-fallback prints to backend logs. Inherited. |
| Stale Pool Ghost audience | "Refreshes on page load" caption under the new button. |
| PostHog unreachable / rate-limited | Silent failure — empty fallback dict; predicates degrade to column-only. No error visible to user. Logged at WARNING. |
| Heavy DB write rate from `last_seen_at` | 5-minute throttle in dependency; at this scale (~100 users) the rate is <1 write/sec averaged, negligible vs. existing background load (e.g., 30s leaderboard cache rebuild). |
| Migration risk | Adding a nullable timestamp column is one of the safest Alembic ops; no table rewrite, no lock escalation. Backfill is a single UPDATE. |

**Pytest cases** (`backend/tests/test_broadcast*.py`):

```python
async def test_pool_ghost_uses_hybrid_signal(session, posthog_stub):
    # User A: last_seen_at after kickoff → NOT ghost (column says active)
    # User B: last_seen_at NULL, PostHog shows pageview after kickoff → NOT ghost (PostHog rescue)
    # User C: last_seen_at before kickoff, no PostHog → IN ghost
    # User D: never submitted → NOT ghost (eligibility filter)
    # User E: submitted but is_disabled=True → NOT ghost (eligibility)
    ...

async def test_lapsing_window_uses_max_of_signals(session, posthog_stub):
    # User A: last_seen_at 1d ago → NOT lapsing (fresh)
    # User B: last_seen_at NULL, PostHog 5d ago → IN cohort (PostHog says lapsing)
    # User C: last_seen_at 5d ago, PostHog 1d ago → NOT lapsing (PostHog is fresh)
    # User D: last_seen_at 10d ago, no PostHog → NOT lapsing (graduates to Pool Ghost)
    # User E: never logged in → NOT lapsing (Pool Ghost candidate)
    ...

async def test_posthog_failure_degrades_silently(session, monkeypatch):
    # Patch posthog_read.get_last_pageview_for_users_since to raise.
    # Build engagement input → returns empty dict, logs WARNING, doesn't raise.
    # Pool Ghost / Lapsing predicates work on column data alone.
    # Assert: no exception propagates to caller; audience counts are correct
    # given column-only signal.
    ...

async def test_pool_ghost_and_lapsing_mutually_exclusive(session, posthog_stub):
    # Same DB + PostHog state, query both segments; assert intersection is empty.
    ...
```

**Test conventions:**
- Use `utc_now()` for time fixtures (project's TZ rule).
- Construct test datetimes with `datetime(..., tzinfo=timezone.utc)`
  — aiosqlite strips tzinfo on read, so the predicate must coerce
  defensively (`aware_utc()` helper) where it compares.
- PostHog stub: a fixture returning a controllable dict; the failure
  test patches the helper to raise.

**Dependency test** (`test_dependencies.py`):

```python
async def test_get_current_user_throttles_last_seen_writes(session):
    # First request: last_seen_at NULL → write fires; column updates.
    # Immediate second request: < 5 min → no write.
    # Mocked clock advance 6 min: write fires again.
    ...
```

**Frontend test:** none required. The broadcast card change is
data-only.

## Open questions resolved during brainstorming

1. **Cohort set granularity** — 2 new cohorts (Pool Ghost + Lapsing).
   Power user / Engaged / Non-participant are *observational*, not
   actionable broadcast targets; they belong on the future
   `/admin/insights` page.
2. **Entry filter** — eligible: `is_disabled=false AND withdrawn_at
   IS NULL AND status=SUBMITTED AND phase=PHASE_1`.
3. **Anchor** — Pool Ghost anchored to kickoff (one-shot semantics);
   Lapsing rolling 3-7d window (ongoing semantics).
4. **Personalization level** — Pool Ghost minimal (name + CTA);
   Lapsing rank-personalized.
5. **Mutual exclusivity** — not enforced between SUBMITTERS and the
   two new cohorts. Admin picks one cohort per broadcast.
6. **Tournament start anchor** — 2026-06-11 19:00 UTC (21:00 Malta CEST).
7. **Engagement signal architecture** — hybrid (A + B): primary
   `User.last_seen_at` column + fallback PostHog `$pageview` query,
   PostHog failures degrade silently.

## Out-of-scope follow-up ideas

These came up during brainstorming and are *not* part of this slice.

- `/admin/insights` page: site-wide page/feature analytics dashboard
  (separate spec).
- Cohort column on `/admin/users` list page with filter chips.
- Per-user activity expansion on `/admin/users/[id]` — could read
  `last_seen_at` directly once the column lands.
- Power-user / Engaged / Non-participant observational cohorts.
- Group-stage-winners celebratory broadcast cohort (revisit ~Day 12).
- Tightening the existing `_has_submitted_phase_predicate()` to add
  eligibility filtering.
- Toast notifications driven by cohort membership.

## Versioning

Minor (capability-adding) release per the bump rule in CLAUDE.md.

- Frontend `package.json` and `package-lock.json`: bump minor.
- Backend `pyproject.toml`: bump minor.
- `frontend/src/lib/data/changelog.json`: append entry of type
  `feature` summarising "Two new cohorts on the broadcast email tool
  — re-engage players who haven't been to the site since kickoff."

## Risks

- **Pool Ghost on day 3 includes legitimate-vacation users** —
  someone who submitted on the deadline and went on holiday is
  flagged as a ghost on day 3 even though they intended to return.
  Mitigation: email copy is friendly, not accusatory.
- **Lapsing under-counts on the first send** — the 3-7d window only
  fills in from day 3 onward; first send may be artificially small.
- **The "ghost zone" forms from day 8+** — Pool Ghost is anchored to
  kickoff, so a user who logged in once at kickoff and then drifted
  away leaves the cohort permanently for this tournament. Once
  their last-seen is past the 7d Lapsing window (day 8+), they fall
  into a third bucket — neither Pool Ghost nor Lapsing. Mitigation,
  if it becomes a real gap: switch Pool Ghost from "since kickoff"
  to a rolling "no engagement in last 7 days" window in a follow-up.
- **Audit-events table growth** — irrelevant for this spec; we no
  longer query audit_events at predicate-evaluation time (only in
  the one-shot backfill).
- **`User.last_seen_at` column drifts on heavy SvelteKit client-side
  caching** — pure client navigation that doesn't hit the backend
  doesn't tick the column. The PostHog fallback (B) closes this gap
  by catching pageviews regardless of whether the backend was hit.
- **PostHog quota / rate limits** — the engagement fetch is one
  HogQL query per `count_audience` call, cached for 5 minutes via
  the existing `posthog_read.py` TTL cache. Negligible at the
  current pool size; worth re-checking if the system grows past
  ~1,000 users.
- **Tournament-start constant drift** — if the next tournament
  reuses the system without updating `TOURNAMENT_START`, Pool Ghost
  would empty out (everyone's `last_seen_at` is >= start). The
  cohort-count display surfaces this before send.
