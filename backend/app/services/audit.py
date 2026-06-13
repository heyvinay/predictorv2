"""Audit-event writer + HTTP-context capture helpers + reader (v2.156.0).

Three distinct concerns live here:

1. **`record_audit_event(...)`** — the one-line helper every other service
   calls to append an audit row. It adds the row to the *current* session
   without committing, so the audit row participates in the same
   transaction as the state mutation. If the caller rolls back, the audit
   row rolls back too.

2. **`AuditContext`** — a frozen value object carrying HTTP-side metadata
   (ip, user-agent). Constructed by an API-layer dependency, threaded
   through service calls as a plain argument. This keeps the service
   layer HTTP-agnostic and unit-testable without mocking `Request`.

3. **Reader functions** (`query_audit_events`, `last_login_for_users`,
   `last_activity_for_users`) — added in v2.156.0 for the redesigned
   `/admin/audit` page, the Users list's "Last activity" column, and the
   User-detail page's KPI strip. All read-only, all LEFT-join User for
   actor name/email so the frontend can render rows without a second
   round-trip.

Event type naming convention (dotted, lowercase, present tense):
- `auth.login_succeeded`, `auth.login_failed`, `auth.logout`,
  `auth.registered`, `auth.password_reset`, `auth.oauth_callback`
- `user.profile_updated` (added in v2.156.0)
- `entry.created`, `entry.renamed`, `entry.duplicated`, `entry.withdrawn`,
  `entry.phase_ready`, `entry.phase_submitted`, `entry.phase_reopened`,
  `entry.disabled`, `entry.enabled`, `entry.paid_updated`,
  `entry.prize_eligible_updated`, `entry.recovered`
- `competition.settings_updated`, `competition.phase2_opened`
- `prediction.match_upserted`, `prediction.bracket_upserted`,
  `prediction.bonus_upserted` (added in Task C)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models._datetime import aware_utc
from app.models.audit import AuditEvent
from app.models.entry import ActorRole
from app.models.user import User
from app.schemas.admin import AuditEventRead


@dataclass(frozen=True)
class AuditContext:
    """HTTP-side metadata for one audited action.

    Constructed by `audit_context()` dependency. Pass through to every
    service call that performs an auditable action. Service code never
    touches FastAPI's `Request` directly.
    """

    ip_address: str | None
    user_agent: str | None

    @classmethod
    def empty(cls) -> "AuditContext":
        """Use when no HTTP context is available (system jobs, scripts)."""
        return cls(ip_address=None, user_agent=None)


def audit_context(request: Request) -> AuditContext:
    """FastAPI dependency that captures IP + user-agent from the request.

    `request.client` is `None` in some test environments — guard for it.
    The X-Forwarded-For header is preferred when a reverse proxy is in
    front (production deploys behind nginx/cloudflare); otherwise fall
    back to the direct client host.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For is a comma-separated chain of proxies; the
        # original client is the leftmost address.
        ip = forwarded.split(",")[0].strip()
    elif request.client is not None:
        ip = request.client.host
    else:
        ip = None

    user_agent = request.headers.get("user-agent")
    # Truncate to the column max-length so an unusually long UA doesn't
    # blow up the insert. 512 chars covers >99% of real-world UAs.
    if user_agent and len(user_agent) > 512:
        user_agent = user_agent[:512]

    return AuditContext(ip_address=ip, user_agent=user_agent)


def record_audit_event(
    session: AsyncSession,
    *,
    event_type: str,
    actor_user_id: UUID | None,
    actor_role: ActorRole,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    ctx: AuditContext | None = None,
    metadata: dict[str, Any] | None = None,
    reason: str | None = None,
) -> AuditEvent:
    """Append one audit row to the current session.

    Does NOT commit — the caller's commit picks it up. This is intentional:
    keeping the audit write in the same transaction as the state mutation
    means the log is exactly as complete as the state. A rollback rolls
    both back together.

    Returns the (unflushed) event so callers can inspect / log the id.
    """
    if ctx is None:
        ctx = AuditContext.empty()
    event = AuditEvent(
        event_type=event_type,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        subject_type=subject_type,
        subject_id=subject_id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        event_metadata=metadata,
        reason=reason,
    )
    session.add(event)
    return event


# ===========================================================================
# Readers (v2.156.0) — power the redesigned /admin/audit page and the
# Last login / Last activity columns on /admin/users.
# ===========================================================================


async def query_audit_events(
    session: AsyncSession,
    *,
    event_type: str | None = None,
    namespace: str | None = None,
    actor_user_id: UUID | None = None,
    subject_id: UUID | None = None,
    subject_type: str | None = None,
    search: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[AuditEventRead], int]:
    """Paginated audit feed, newest-first, with actor name/email joined.

    Filter semantics (all AND-ed together; absent params are no-ops):

    * ``event_type`` — exact match on the dotted string.
    * ``namespace`` — prefix match used by the page's namespace chips
      (``"auth"`` matches every ``auth.*`` event). Excludes the trailing
      dot; we add it here so ``"auth"`` doesn't accidentally match a
      hypothetical ``"authorization.*"`` namespace.
    * ``actor_user_id`` — restricts the feed to one user's actions
      (powers the User-detail Activity table).
    * ``subject_id`` — restricts to actions on one subject (powers the
      slide-over's "Full audit history →" deep-link).
    * ``subject_type`` — typically used alongside ``subject_id`` (e.g.
      ``subject_type="entry"``).
    * ``search`` — case-insensitive substring match on the JOINed
      ``User.email``, ``User.name``, or ``AuditEvent.event_type``. Empty
      / whitespace-only strings are treated as "no filter."
    * ``since`` / ``until`` — closed-open window on ``created_at``
      (``[since, until)``). Timezone-aware UTC datetimes per project
      convention.

    Returns ``(rows, total_matching)``. ``rows`` is sliced by
    ``limit``/``offset``; ``total`` is the full match count for
    pagination math.
    """
    # Base SELECT — LEFT JOIN User so unauthenticated/system events
    # (actor_user_id=None) still appear with NULL name/email columns.
    base = select(AuditEvent, User.name, User.email).outerjoin(
        User, AuditEvent.actor_user_id == User.id
    )

    # Apply filters identically to data + count statements so totals
    # always reflect what the rows would have returned without pagination.
    if event_type:
        base = base.where(AuditEvent.event_type == event_type)

    if namespace:
        base = base.where(AuditEvent.event_type.like(f"{namespace.rstrip('.')}.%"))

    if actor_user_id is not None:
        base = base.where(AuditEvent.actor_user_id == actor_user_id)

    if subject_id is not None:
        base = base.where(AuditEvent.subject_id == subject_id)

    if subject_type:
        base = base.where(AuditEvent.subject_type == subject_type)

    if search and search.strip():
        pat = f"%{search.strip()}%"
        base = base.where(
            or_(
                User.email.ilike(pat),
                User.name.ilike(pat),
                AuditEvent.event_type.ilike(pat),
            )
        )

    if since is not None:
        base = base.where(AuditEvent.created_at >= since)

    if until is not None:
        base = base.where(AuditEvent.created_at < until)

    # Total count — same filters, no ordering / pagination.
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    # Page of rows.
    page_stmt = (
        base.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
    )
    result = await session.execute(page_stmt)
    rows: list[AuditEventRead] = []
    for event, actor_name, actor_email in result.all():
        rows.append(
            AuditEventRead(
                id=event.id,
                event_type=event.event_type,
                actor_user_id=event.actor_user_id,
                actor_name=actor_name,
                actor_email=actor_email,
                actor_role=event.actor_role.value
                if hasattr(event.actor_role, "value")
                else str(event.actor_role),
                subject_type=event.subject_type,
                subject_id=event.subject_id,
                ip_address=event.ip_address,
                event_metadata=event.event_metadata,
                reason=event.reason,
                created_at=event.created_at,
            )
        )

    return rows, int(total or 0)


async def get_recent_logins(
    session: AsyncSession,
    limit: int = 20,
) -> list[tuple[UUID, str | None, datetime]]:
    """Most recent successful logins across the WHOLE pool.

    Returns ``[(user_id, name, login_at)]`` ordered newest first. Used
    by the Site Pulse panel — answers "who's been around lately?" with
    no per-user drilldown required. v2.176.0.

    Joins to User so the panel doesn't need a second hop. ``name`` is
    nullable (a user can have logged in before completing onboarding,
    though it's rare); callers should fall back to email-prefix or "—".

    ``aware_utc()`` defends against aiosqlite tzinfo strip in tests.
    """
    from app.models.user import User as UserModel  # local: avoid cycles

    stmt = (
        select(
            AuditEvent.actor_user_id,
            UserModel.name,
            AuditEvent.created_at,
        )
        .join(UserModel, UserModel.id == AuditEvent.actor_user_id)
        .where(AuditEvent.event_type == "auth.login_succeeded")
        .where(AuditEvent.actor_user_id.is_not(None))
        .order_by(AuditEvent.created_at.desc())
        .limit(int(limit))
    )
    rows = (await session.execute(stmt)).all()
    return [
        (uid, name, aware_utc(ts))
        for uid, name, ts in rows
        if uid is not None
    ]


async def last_login_for_users(
    session: AsyncSession,
    user_ids: list[UUID],
) -> dict[UUID, datetime]:
    """MAX(created_at) WHERE event_type='auth.login_succeeded' grouped by
    actor_user_id.

    Empty input → empty output (no DB round-trip). Users with no
    successful login event are absent from the returned dict; callers
    should treat the missing key as "never logged in" (e.g. cohort 1
    sign-up-only users will be missing here).

    Powers the audit-derived "Last login" KPI on /admin/users/[id] and
    is one of two signals on /admin/users. The other (broader) signal
    is :func:`last_activity_for_users`.
    """
    if not user_ids:
        return {}

    stmt = (
        select(AuditEvent.actor_user_id, func.max(AuditEvent.created_at))
        .where(AuditEvent.event_type == "auth.login_succeeded")
        .where(AuditEvent.actor_user_id.in_(user_ids))
        .group_by(AuditEvent.actor_user_id)
    )
    rows = (await session.execute(stmt)).all()
    # aware_utc() defensively coerces naive datetimes (which aiosqlite
    # returns for TIMESTAMPTZ columns) back to timezone-aware UTC.
    # Postgres preserves tzinfo so the call is a no-op there.
    return {uid: aware_utc(ts) for uid, ts in rows if uid is not None}


async def last_activity_for_users(
    session: AsyncSession,
    user_ids: list[UUID],
) -> dict[UUID, datetime]:
    """MAX(created_at) across ALL event types grouped by actor_user_id.

    Broader signal than :func:`last_login_for_users` — captures writes
    (entry submissions, profile edits, prediction changes) as well as
    authentication events. Powers the "Last activity" column on
    /admin/users (the broader, more useful "are they still engaged?"
    signal) and a KPI on User-detail.

    Empty input → empty output. Users with zero audit rows are absent
    from the dict.
    """
    if not user_ids:
        return {}

    stmt = (
        select(AuditEvent.actor_user_id, func.max(AuditEvent.created_at))
        .where(AuditEvent.actor_user_id.in_(user_ids))
        .group_by(AuditEvent.actor_user_id)
    )
    rows = (await session.execute(stmt)).all()
    # aware_utc() defensively coerces naive datetimes (which aiosqlite
    # returns for TIMESTAMPTZ columns) back to timezone-aware UTC.
    return {uid: aware_utc(ts) for uid, ts in rows if uid is not None}
