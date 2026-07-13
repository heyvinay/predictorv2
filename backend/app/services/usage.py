"""Usage & Adoption dashboard assembler (v2.212.0).

Thin orchestrator over :mod:`app.services.posthog_read`,
:mod:`app.services.audit`, and :mod:`app.services.broadcast` that
builds the response for `GET /admin/usage` — a deliberately separate,
more analytical surface from the narrow, operational Site Pulse panel
(:mod:`app.services.pulse`). See
docs/superpowers/specs/2026-07-13-usage-adoption-dashboard-design.md.

**FEATURE_GROUPS is the authoritative event→feature map.** When you
ship a new discretionary user-facing feature with a new analytics
event, add it here (see the CLAUDE.md "Keeping the Usage & Adoption
dashboard current" convention). Anything that fires in PostHog but
isn't in this map, and isn't in AMBIENT_EVENTS, surfaces automatically
under "Uncategorized events" — a forgotten mapping is always visible,
never silent.

**Partial-failure contract.** Every PostHog-sourced field degrades to
empty/0/None when PostHog is unreachable or unconfigured — mirrors
:func:`app.services.pulse.get_site_pulse`'s contract. DB-sourced
fields (the submitter funnel, login counts, ``User.last_seen_at``)
always render regardless. ``UsageReport.posthog_available`` lets the
frontend show one unified banner instead of per-widget checks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import TOURNAMENT_START
from app.models._datetime import aware_utc, utc_now
from app.models.user import Employer, User
from app.schemas.admin import (
    UsageDrillUser,
    UsageFeatureAdopter,
    UsageFeatureAdoption,
    UsageFrequencyBucket,
    UsageFunnel,
    UsageKpi,
    UsagePowerUser,
    UsageReport,
    UsageRetentionCohort,
    UsageSeriesPoint,
    UsageUncategorizedEvent,
    UserFeatureUsage,
)
from app.services import posthog_read
from app.services.audit import get_login_counts_since
from app.services.broadcast import (
    BroadcastSegment,
    _has_submitted_phase_predicate,
    count_all_audiences,
    query_audience,
)

# ---------------------------------------------------------------------------
# FEATURE_GROUPS — hand-curated, mirrors the discipline already applied
# to changelog.json vs featureHighlights.json: never auto-derive this
# from the EventName union (that would surface reserved-but-unfired
# events as phantom 0%-adoption rows). `frozen=True` marks entry-phase
# features that die post-deadline (adoption stays historical, not
# live) — see Smart Fill.
# ---------------------------------------------------------------------------
FEATURE_GROUPS: dict[str, dict[str, object]] = {
    "leaderboard": {
        "name": "Leaderboard views",
        "sub": "Standings / Race / Insights",
        "events": ["leaderboard_view_changed"],
    },
    "insights_tab": {
        "name": "Insights tab",
        "sub": "Standings → Insights view",
        "events": ["leaderboard_view_changed"],
        # Same event as "leaderboard" above, narrowed to one view —
        # `leaderboard_view_changed` fires with `{view, from}` (see
        # frontend/src/routes/leaderboard/+page.svelte:setView).
        # `prop_filter` is handled specially in get_usage_report/
        # get_feature_adopters: it CANNOT share the bulk unfiltered
        # get_unique_users_by_event() call every other feature uses,
        # since the filter is per-feature, not global.
        "prop_filter": ("view", "insights"),
    },
    "smartfill": {
        "name": "Smart Fill",
        "sub": "FIFA + Betting Odds",
        "events": ["smartfill_opened", "smartfill_applied"],
        "frozen": True,
    },
    "matchdetail": {
        "name": "Match Detail",
        "sub": "per-fixture drill-in",
        "events": ["match_detail_opened"],
    },
    "allentries": {
        "name": "All-entries sheet",
        "sub": "View All Entries button",
        "events": ["view_all_entries_clicked"],
    },
    "bracket": {
        "name": "Knockout bracket tab",
        "sub": "Results page",
        "events": ["bracket_tab_opened"],
    },
    "whatsnew": {
        "name": "What's New panel",
        "sub": "sparkle nav",
        "events": ["whats_new_opened", "whats_new_feature_clicked"],
    },
    "feedback": {
        "name": "Feedback & rating",
        "sub": "star + written note",
        "events": ["app_rating_submitted", "feedback_submitted", "feature_rated"],
    },
    "simulator": {
        "name": "Bracket Simulator",
        "sub": '"what if" knockout runs',
        "events": [
            "simulator_gate_opened",
            "simulator_toggled_on",
            "simulator_challenge_submitted",
            "simulator_unlocked",
            "simulator_run_committed",
        ],
    },
}

# Ambient / navigation / landing-funnel / system-initiated events —
# deliberately excluded from Feature Adoption AND from "Uncategorized
# events" (they're known-and-intentionally-unmapped, not forgotten).
AMBIENT_EVENTS: frozenset[str] = frozenset(
    {
        "$pageview", "$autocapture", "$identify", "$pageleave",
        "$feature_flag_called", "$web_vitals", "$rageclick",
        "$exception", "$dead_click",
        "page_viewed", "nav_clicked", "dashboard_view",
        "landing_view", "section_viewed", "cta_clicked",
        "news_card_clicked", "rules_link_clicked", "countdown_phase",
        "signin_email_focused", "signin_email_submitted",
        "signin_google_clicked", "signin_abandoned",
        "feature_nudge_shown", "feature_nudge_clicked",
    }
)

LOW_ADOPTION_THRESHOLD_PCT = 15
POWER_USER_MIN_ACTIVE_DAYS = 8
TABLE_ROW_LIMIT = 20
DRILL_ROW_LIMIT = 200

# (lo, hi, label) — shared by _bucket_frequency (counts per bucket) and
# _range_for_bucket_label (the reverse lookup the frequency-bucket
# drill-down uses to turn a clicked label back into a query range).
FREQUENCY_RANGES: list[tuple[int, int, str]] = [
    (0, 0, "0 days"),
    (1, 1, "1 day"),
    (2, 3, "2-3"),
    (4, 7, "4-7"),
    (8, 14, "8-14"),
    (15, 10_000, "15+"),
]


# ---------------------------------------------------------------------------
# Time-range / segment resolution
# ---------------------------------------------------------------------------
def _resolve_range(range_key: str, now: datetime) -> tuple[datetime, datetime, str]:
    """(since, until, default_granularity) for a range key."""
    until = now
    if range_key == "1h":
        return until - timedelta(hours=1), until, "hour"
    if range_key == "24h":
        return until - timedelta(hours=24), until, "hour"
    if range_key == "30d":
        return until - timedelta(days=30), until, "day"
    if range_key == "all":
        return TOURNAMENT_START, until, "week"
    return until - timedelta(days=7), until, "day"  # "7d" default


def _previous_window(since: datetime, until: datetime) -> tuple[datetime, datetime]:
    span = until - since
    return since - span, since


async def resolve_segment_user_ids(
    session: AsyncSession, segment: str
) -> list[UUID] | None:
    """None = no segment filter (everyone). Unknown segment → None too
    (fail open to "all" rather than silently returning zero rows)."""
    if segment == "all":
        return None
    try:
        employer = Employer(segment)
    except ValueError:
        return None
    rows = (
        await session.execute(select(User.id).where(User.employer == employer))
    ).all()
    return [r[0] for r in rows]


def _delta_pct(cur: float | int | None, prev: float | int | None) -> float | None:
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100, 1)


def _delta_points(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None:
        return None
    return round(cur - prev, 1)


def _bucket_frequency(
    freq_map: dict[int, int], total_population: int
) -> list[UsageFrequencyBucket]:
    """PostHog only returns users with >=1 active day; the "0 days"
    (dormant) bucket is the DB population minus everyone PostHog saw.
    """
    nonzero_total = sum(freq_map.values())
    zero_count = max(total_population - nonzero_total, 0)

    buckets: list[UsageFrequencyBucket] = []
    for lo, hi, label in FREQUENCY_RANGES:
        count = zero_count if (lo, hi) == (0, 0) else sum(
            v for k, v in freq_map.items() if lo <= k <= hi
        )
        buckets.append(
            UsageFrequencyBucket(
                label=label,
                count=count,
                is_dormant=(lo, hi) == (0, 0),
                is_power=lo >= POWER_USER_MIN_ACTIVE_DAYS,
            )
        )
    return buckets


def _range_for_bucket_label(label: str) -> tuple[int, int] | None:
    """Reverse of the loop in :func:`_bucket_frequency` — turns a
    clicked bucket label back into its (lo, hi) range. ``None`` for an
    unrecognised label.
    """
    for lo, hi, bucket_label in FREQUENCY_RANGES:
        if bucket_label == label:
            return (lo, hi)
    return None


def _bucket_bounds(bucket: str, granularity: str) -> tuple[datetime, datetime]:
    """Parse one trend-chart bucket label (exactly as PostHog's
    ``toStartOfX`` returned it, e.g. ``"2026-07-07"`` or
    ``"2026-07-07 14:00:00"``) into its own [start, start+1unit) window
    — powers the Active-users-trend bar click-through.
    """
    raw = bucket.strip()
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T")
    if len(raw) == 10:  # date-only, e.g. "2026-07-07"
        raw += "T00:00:00"
    start = datetime.fromisoformat(raw)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    width = {
        "hour": timedelta(hours=1),
        "day": timedelta(days=1),
        "week": timedelta(weeks=1),
    }.get(granularity, timedelta(days=1))
    return start, start + width


async def _drill_users_from_rows(
    session: AsyncSession, rows: list[tuple[UUID, datetime]]
) -> list[UsageDrillUser]:
    """Map (user_id, last_used) pairs from a PostHog query into
    UsageDrillUser rows with real names, via one DB lookup. Shared by
    every click-through drawer backed by a raw distinct_id/timestamp
    query (day bucket, hour-of-day).
    """
    if not rows:
        return []
    uids = [uid for uid, _ in rows]
    users = list(
        (await session.execute(select(User).where(User.id.in_(uids)))).scalars().all()
    )
    name_by_id = {u.id: (u.name or u.email) for u in users}
    return [
        UsageDrillUser(user_id=uid, name=name_by_id.get(uid, "(unknown)"), last_used=ts)
        for uid, ts in rows
    ]


# ---------------------------------------------------------------------------
# Main assembler
# ---------------------------------------------------------------------------
async def get_usage_report(
    session: AsyncSession,
    range_key: str = "7d",
    granularity: str | None = None,
    segment: str = "all",
) -> UsageReport:
    now = utc_now()
    since, until, default_gran = _resolve_range(range_key, now)
    gran = granularity or default_gran
    prev_since, prev_until = _previous_window(since, until)

    segment_uids = await resolve_segment_user_ids(session, segment)
    posthog_ok = posthog_read.is_configured()

    # --- Submitter population (the adoption denominator + power-users
    # table source) — "people actually playing," not all registered
    # users, so adoption % isn't diluted by no-shows.
    submitter_stmt = select(User).where(_has_submitted_phase_predicate())
    if segment_uids is not None:
        submitter_stmt = submitter_stmt.where(User.id.in_(segment_uids))
    submitters = list((await session.execute(submitter_stmt)).scalars().all())
    submitter_ids = [u.id for u in submitters]
    total_submitters = len(submitter_ids)

    # --- Funnel — reuse the existing broadcast-audience counts wholesale.
    audience_counts = await count_all_audiences(session)
    funnel = UsageFunnel(
        submitters=audience_counts.get(BroadcastSegment.SUBMITTERS, 0),
        no_entry=audience_counts.get(BroadcastSegment.NO_ENTRY, 0),
        draft_holders=audience_counts.get(BroadcastSegment.DRAFT_HOLDERS, 0),
        pool_ghost=audience_counts.get(BroadcastSegment.POOL_GHOST, 0),
        lapsing=audience_counts.get(BroadcastSegment.LAPSING, 0),
    )

    # --- KPI scorecard ---
    active_series = await posthog_read.get_active_users_series(
        since, until, gran, segment_uids
    )
    active_users = await posthog_read.get_unique_active_users(
        since, until, segment_uids
    )
    prev_active_users = await posthog_read.get_unique_active_users(
        prev_since, prev_until, segment_uids
    )
    sessions_per_user = await posthog_read.get_sessions_per_user(
        since, until, segment_uids
    )
    prev_sessions_per_user = await posthog_read.get_sessions_per_user(
        prev_since, prev_until, segment_uids
    )
    new_returning = await posthog_read.get_new_vs_returning(
        since, until, segment_uids
    )
    prev_new_returning = await posthog_read.get_new_vs_returning(
        prev_since, prev_until, segment_uids
    )
    stickiness = await posthog_read.get_stickiness(since, until, segment_uids)
    prev_stickiness = await posthog_read.get_stickiness(
        prev_since, prev_until, segment_uids
    )

    new_count = new_returning[0] if new_returning else None
    new_total = sum(new_returning) if new_returning else None
    prev_new_count = prev_new_returning[0] if prev_new_returning else None

    kpis = [
        UsageKpi(
            key="active_users",
            label="Active users",
            value=active_users,
            delta_pct=_delta_pct(active_users, prev_active_users),
            # Headline KPI reuses the trend series for its sparkline; the
            # other three would each need their own per-bucket time
            # series (an extra N HogQL queries) for a v1 nice-to-have —
            # left empty rather than faked.
            sparkline=[p.count for p in active_series],
        ),
        UsageKpi(
            key="sessions_per_user",
            label="Sessions / user",
            value=sessions_per_user,
            delta_pct=_delta_pct(sessions_per_user, prev_sessions_per_user),
        ),
        UsageKpi(
            key="new_vs_returning",
            label="New vs returning",
            value=new_count,
            suffix=f" / {new_total}" if new_total is not None else "",
            delta_pct=_delta_pct(new_count, prev_new_count),
        ),
        UsageKpi(
            key="stickiness",
            label="Stickiness (DAU/MAU)",
            value=stickiness,
            suffix="%",
            # Point delta, not %, per the DAU/MAU convention (e.g. "+3 pts").
            delta_pct=_delta_points(stickiness, prev_stickiness),
        ),
    ]

    series = [UsageSeriesPoint(bucket=p.bucket, count=p.count) for p in active_series]
    time_of_day = await posthog_read.get_activity_by_hour(since, until, segment_uids)

    # --- Retention + frequency ---
    retention_raw = await posthog_read.get_weekly_retention_cohorts()
    retention_cohorts = [
        UsageRetentionCohort(
            cohort_week=r["cohort_week"], pct_by_offset=r["pct_by_offset"]
        )
        for r in retention_raw
    ]
    freq_map = await posthog_read.get_engagement_frequency(
        since, until, segment_uids
    )
    frequency_buckets = (
        _bucket_frequency(freq_map, total_submitters) if posthog_ok else []
    )

    # --- Feature adoption + uncategorized events ---
    # Property-filtered features (e.g. "Insights tab" = leaderboard_
    # view_changed narrowed to view='insights') can't share the bulk
    # unfiltered query below — the filter is per-feature, not global —
    # so they're split out and given their own small query each.
    plain_groups = {
        k: g for k, g in FEATURE_GROUPS.items() if not g.get("prop_filter")
    }
    property_groups = {
        k: g for k, g in FEATURE_GROUPS.items() if g.get("prop_filter")
    }

    all_feature_events = [e for group in plain_groups.values() for e in group["events"]]
    adoption_counts = await posthog_read.get_unique_users_by_event(
        all_feature_events, since, until, segment_uids
    )
    all_events_seen = await posthog_read.get_all_events_last_seen()

    feature_adoption: list[UsageFeatureAdoption] = []
    mapped_events: set[str] = set()
    for key, group in plain_groups.items():
        events = group["events"]
        mapped_events.update(events)
        # Per-feature adopter count approximates the true union of
        # "used any of this feature's events" with the MAX of each
        # event's individual unique-user count — a documented lower
        # bound, not the exact union (which would need one more HogQL
        # query per feature to compute correctly). Close enough for
        # features whose events are strongly correlated (opened →
        # applied), which is every feature in this map today.
        users = max((adoption_counts.get(e, 0) for e in events), default=0)
        pct = round(users / total_submitters * 100) if total_submitters else 0
        last_used = None
        for e in events:
            seen = all_events_seen.get(e)
            if seen and seen[1] and (last_used is None or seen[1] > last_used):
                last_used = seen[1]
        feature_adoption.append(
            UsageFeatureAdoption(
                key=key,
                name=str(group["name"]),
                sub=str(group["sub"]),
                users=users,
                pct=pct,
                last_used=last_used,
                frozen=bool(group.get("frozen", False)),
                rarely_used=pct < LOW_ADOPTION_THRESHOLD_PCT,
            )
        )

    for key, group in property_groups.items():
        events = list(group["events"])
        mapped_events.update(events)
        prop_filter = group["prop_filter"]
        prop_counts = await posthog_read.get_unique_users_by_event(
            events, since, until, segment_uids, prop_filter=prop_filter
        )
        users = sum(prop_counts.values())
        pct = round(users / total_submitters * 100) if total_submitters else 0
        last_used = None
        if users:
            top_adopter = await posthog_read.get_adopters_for_events(
                events, since, until, segment_uids, limit=1, prop_filter=prop_filter
            )
            if top_adopter:
                last_used = top_adopter[0][1]
        feature_adoption.append(
            UsageFeatureAdoption(
                key=key,
                name=str(group["name"]),
                sub=str(group["sub"]),
                users=users,
                pct=pct,
                last_used=last_used,
                frozen=bool(group.get("frozen", False)),
                rarely_used=pct < LOW_ADOPTION_THRESHOLD_PCT,
            )
        )

    feature_adoption.sort(key=lambda f: f.users, reverse=True)

    uncategorized_events = [
        UsageUncategorizedEvent(name=name, count=count, last_seen=seen)
        for name, (count, seen) in all_events_seen.items()
        if name not in mapped_events and name not in AMBIENT_EVENTS
    ]
    uncategorized_events.sort(key=lambda u: u.count, reverse=True)

    # --- Power users (3 modes) ---
    most_active: list[UsagePowerUser] = []
    least_active: list[UsagePowerUser] = []
    never_engaged: list[UsagePowerUser] = []

    if posthog_ok and submitter_ids:
        login_counts = await get_login_counts_since(
            session, TOURNAMENT_START, submitter_ids
        )
        visit_freq = await posthog_read.get_active_days_and_sessions_for_users(
            submitter_ids, TOURNAMENT_START
        )
        rows: list[UsagePowerUser] = []
        for u in submitters:
            vf = visit_freq.get(u.id)
            rows.append(
                UsagePowerUser(
                    user_id=u.id,
                    name=u.name or u.email,
                    logins=login_counts.get(u.id, 0),
                    active_days=vf.active_days if vf else 0,
                    sessions=vf.sessions if vf else 0,
                    last_seen_at=aware_utc(u.last_seen_at) if u.last_seen_at else None,
                )
            )
        most_active = sorted(rows, key=lambda r: r.active_days, reverse=True)[
            :TABLE_ROW_LIMIT
        ]
        least_active = sorted(
            (r for r in rows if r.active_days >= 1), key=lambda r: r.active_days
        )[:TABLE_ROW_LIMIT]
        never_engaged = sorted(
            (r for r in rows if r.active_days == 0), key=lambda r: r.logins
        )[:TABLE_ROW_LIMIT]

    return UsageReport(
        range=range_key,
        granularity=gran,
        segment=segment,
        posthog_available=posthog_ok,
        funnel=funnel,
        kpis=kpis,
        active_users_series=series,
        time_of_day=time_of_day,
        retention_cohorts=retention_cohorts,
        frequency_buckets=frequency_buckets,
        feature_adoption=feature_adoption,
        uncategorized_events=uncategorized_events,
        power_users_most_active=most_active,
        power_users_least_active=least_active,
        power_users_never_engaged=never_engaged,
    )


async def get_feature_adopters(
    session: AsyncSession,
    key: str,
    range_key: str = "all",
    segment: str = "all",
    limit: int = 20,
) -> list[UsageFeatureAdopter]:
    """Adopter drawer for one feature — click-through from the Feature
    Adoption card. ``[]`` for an unknown key or when PostHog is down.
    """
    group = FEATURE_GROUPS.get(key)
    if group is None:
        return []

    now = utc_now()
    since, until, _ = _resolve_range(range_key, now)
    segment_uids = await resolve_segment_user_ids(session, segment)

    raw = await posthog_read.get_adopters_for_events(
        list(group["events"]),
        since,
        until,
        segment_uids,
        limit,
        prop_filter=group.get("prop_filter"),
    )
    if not raw:
        return []

    uids = [uid for uid, _ in raw]
    users = list(
        (await session.execute(select(User).where(User.id.in_(uids)))).scalars().all()
    )
    name_by_id = {u.id: (u.name or u.email) for u in users}

    return [
        UsageFeatureAdopter(
            user_id=uid, name=name_by_id.get(uid, "(unknown)"), last_used=last_used
        )
        for uid, last_used in raw
    ]


# ---------------------------------------------------------------------------
# Click-through drill-downs (v2.213.0) — "who's behind this number?"
# ---------------------------------------------------------------------------
async def get_day_bucket_users(
    session: AsyncSession,
    bucket: str,
    granularity: str = "day",
    segment: str = "all",
) -> list[UsageDrillUser]:
    """Users active in ONE bucket of the "Active users over time"
    trend — click-through on a single bar. ``bucket`` is exactly the
    label the chart rendered (``UsageSeriesPoint.bucket``); ``[]`` if
    it doesn't parse or PostHog is unavailable.
    """
    try:
        since, until = _bucket_bounds(bucket, granularity)
    except (ValueError, TypeError):
        return []
    segment_uids = await resolve_segment_user_ids(session, segment)
    rows = await posthog_read.get_users_active_in_bucket(
        since, until, segment_uids, DRILL_ROW_LIMIT
    )
    return await _drill_users_from_rows(session, rows)


async def get_hour_bucket_users(
    session: AsyncSession,
    hour: int,
    range_key: str = "7d",
    segment: str = "all",
) -> list[UsageDrillUser]:
    """Users active at this hour-of-day, anywhere in the selected
    range — click-through on a "Time of day" bar.
    """
    now = utc_now()
    since, until, _ = _resolve_range(range_key, now)
    segment_uids = await resolve_segment_user_ids(session, segment)
    rows = await posthog_read.get_users_active_at_hour(
        hour, since, until, segment_uids, DRILL_ROW_LIMIT
    )
    return await _drill_users_from_rows(session, rows)


async def get_frequency_bucket_users(
    session: AsyncSession,
    bucket_label: str,
    range_key: str = "7d",
    segment: str = "all",
) -> list[UsageDrillUser]:
    """Users whose active-days-in-range falls in this Engagement
    Frequency bucket — click-through on a frequency bar. The "0 days"
    (dormant) bucket is derived by diffing the segment's full submitter
    population against everyone PostHog saw active — the only way to
    represent "did nothing" from a system that only records events.
    """
    bounds = _range_for_bucket_label(bucket_label)
    if bounds is None:
        return []
    lo, hi = bounds

    now = utc_now()
    since, until, _ = _resolve_range(range_key, now)
    segment_uids = await resolve_segment_user_ids(session, segment)

    submitter_stmt = select(User).where(_has_submitted_phase_predicate())
    if segment_uids is not None:
        submitter_stmt = submitter_stmt.where(User.id.in_(segment_uids))
    submitters = list((await session.execute(submitter_stmt)).scalars().all())
    submitter_by_id = {u.id: u for u in submitters}

    if lo == 0 and hi == 0:
        active_rows = await posthog_read.get_users_by_active_days(
            since, until, 1, 10_000, list(submitter_by_id.keys()), DRILL_ROW_LIMIT * 5
        )
        active_ids = {uid for uid, _ in active_rows}
        dormant = [uid for uid in submitter_by_id if uid not in active_ids]
        return [
            UsageDrillUser(
                user_id=uid,
                name=submitter_by_id[uid].name or submitter_by_id[uid].email,
                detail="0 active days",
            )
            for uid in dormant[:DRILL_ROW_LIMIT]
        ]

    rows = await posthog_read.get_users_by_active_days(
        since, until, lo, hi, list(submitter_by_id.keys()), DRILL_ROW_LIMIT
    )
    out: list[UsageDrillUser] = []
    for uid, active_days in rows:
        u = submitter_by_id.get(uid)
        name = (u.name or u.email) if u else "(unknown)"
        out.append(
            UsageDrillUser(
                user_id=uid,
                name=name,
                detail=f"{active_days} active day{'s' if active_days != 1 else ''}",
            )
        )
    return out


async def get_funnel_cohort_users(
    session: AsyncSession, cohort: str
) -> list[UsageDrillUser]:
    """Members of one funnel-strip cohort (Submitters / No entry /
    Draft / Lapsing / Pool ghost) — DB-only, reuses the existing
    broadcast-audience query wholesale. ``[]`` for an unrecognised
    cohort key.
    """
    try:
        seg = BroadcastSegment(cohort)
    except ValueError:
        return []
    rows = await query_audience(session, seg)
    return [
        UsageDrillUser(user_id=r.user_id, name=r.name or r.email, detail=r.email)
        for r in rows[:DRILL_ROW_LIMIT]
    ]


async def get_user_features(
    session: AsyncSession,
    user_id: UUID,
    range_key: str = "all",
) -> list[UserFeatureUsage]:
    """Per-feature usage for ONE user — powers the Power-users drawer's
    "features this user touches" list. One HogQL query covering every
    feature's events; grouped here by feature. ``[]`` when PostHog is
    unavailable.
    """
    now = utc_now()
    since, until, _ = _resolve_range(range_key, now)

    # Plain groups can all share one bulk (unfiltered) query. Property-
    # filtered groups (e.g. "Insights tab" narrows the SAME event
    # `leaderboard_view_changed` that "Leaderboard views" counts
    # unfiltered) need their own query each — reusing the bulk result
    # for both would give "Insights tab" the wrong number: every
    # leaderboard view switch, not just the insights ones.
    plain_groups = {k: g for k, g in FEATURE_GROUPS.items() if not g.get("prop_filter")}
    property_groups = {k: g for k, g in FEATURE_GROUPS.items() if g.get("prop_filter")}

    all_events = [e for group in plain_groups.values() for e in group["events"]]
    usage_map = await posthog_read.get_user_feature_usage(
        user_id, all_events, since, until
    )

    out: list[UserFeatureUsage] = []
    for key, group in plain_groups.items():
        rows = [usage_map[e] for e in group["events"] if e in usage_map]
        count = sum(c for c, _ in rows)
        last_used = max((ts for _, ts in rows if ts is not None), default=None)
        out.append(
            UserFeatureUsage(
                key=key,
                name=str(group["name"]),
                sub=str(group["sub"]),
                count=count,
                last_used=last_used,
                frozen=bool(group.get("frozen", False)),
            )
        )

    for key, group in property_groups.items():
        prop_map = await posthog_read.get_user_feature_usage(
            user_id, list(group["events"]), since, until, prop_filter=group["prop_filter"]
        )
        rows = list(prop_map.values())
        count = sum(c for c, _ in rows)
        last_used = max((ts for _, ts in rows if ts is not None), default=None)
        out.append(
            UserFeatureUsage(
                key=key,
                name=str(group["name"]),
                sub=str(group["sub"]),
                count=count,
                last_used=last_used,
                frozen=bool(group.get("frozen", False)),
            )
        )

    out.sort(key=lambda f: f.count, reverse=True)
    return out
