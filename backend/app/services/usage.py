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

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import TOURNAMENT_START
from app.models._datetime import aware_utc, utc_now
from app.models.user import Employer, User
from app.schemas.admin import (
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
)
from app.services import posthog_read
from app.services.audit import get_login_counts_since
from app.services.broadcast import (
    BroadcastSegment,
    _has_submitted_phase_predicate,
    count_all_audiences,
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
    ranges = [
        (0, 0, "0 days"),
        (1, 1, "1 day"),
        (2, 3, "2-3"),
        (4, 7, "4-7"),
        (8, 14, "8-14"),
        (15, 10_000, "15+"),
    ]
    nonzero_total = sum(freq_map.values())
    zero_count = max(total_population - nonzero_total, 0)

    buckets: list[UsageFrequencyBucket] = []
    for lo, hi, label in ranges:
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
    all_feature_events = [
        e for group in FEATURE_GROUPS.values() for e in group["events"]
    ]
    adoption_counts = await posthog_read.get_unique_users_by_event(
        all_feature_events, since, until, segment_uids
    )
    all_events_seen = await posthog_read.get_all_events_last_seen()

    feature_adoption: list[UsageFeatureAdoption] = []
    mapped_events: set[str] = set()
    for key, group in FEATURE_GROUPS.items():
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
        list(group["events"]), since, until, segment_uids, limit
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
