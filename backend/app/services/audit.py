"""Audit-event writer + HTTP-context capture helpers.

Two distinct concerns live here:

1. **`record_audit_event(...)`** — the one-line helper every other service
   calls to append an audit row. It adds the row to the *current* session
   without committing, so the audit row participates in the same
   transaction as the state mutation. If the caller rolls back, the audit
   row rolls back too.

2. **`AuditContext`** — a frozen value object carrying HTTP-side metadata
   (ip, user-agent). Constructed by an API-layer dependency, threaded
   through service calls as a plain argument. This keeps the service
   layer HTTP-agnostic and unit-testable without mocking `Request`.

Event type naming convention (dotted, lowercase, present tense):
- `auth.login_succeeded`, `auth.login_failed`, `auth.logout`,
  `auth.registered`, `auth.password_reset`, `auth.oauth_callback`
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
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.entry import ActorRole


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
