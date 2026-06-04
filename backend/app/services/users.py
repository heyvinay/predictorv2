"""Users service (v2.156.0).

Powers the redesigned ``/admin/users`` page and the
``/admin/users/[id]`` drill-down. Two top-level entry points:

* :func:`list_users_with_cohort` — paginated roster query that joins
  ``User`` ↔ ``MagicLinkToken`` ↔ ``PredictionEntry`` and adds derived
  ``cohort`` / ``last_login_at`` / ``last_activity_at`` columns.
* :func:`list_inactive_emails` — restricted projection for the
  re-engagement CSV export.

**Cohort derivation lives here, NOT in the DB schema.** No new columns
were added for the redesign — every cohort label is computed from
existing fields (``User.name``, ``User.auth_provider``,
``MagicLinkToken.used_at``). This keeps the change reversible and means
the cohorts adjust automatically as users transition through onboarding.

**Why ``auth_provider``-aware cohorts?** A Google OAuth user that
abandons onboarding has ``name=NULL`` but no ``MagicLinkToken`` at all
(OAuth doesn't use magic links). Without the provider check those users
fall into neither cohort 1 nor cohort 2 → they're "phantom" users
invisible to every filter. The Google-provider OR clause closes the
gap so cohort 2 captures them.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entry import EntryStatus, PredictionEntry
from app.models.magic_link_token import MagicLinkToken
from app.models.prediction import MatchPrediction
from app.models.user import AuthProvider, User
from app.schemas.admin import (
    InactiveUserRow,
    UserAdminPage,
    UserAdminRowV2,
    UserCohort,
)
from app.services.audit import last_activity_for_users, last_login_for_users


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def list_users_with_cohort(
    session: AsyncSession,
    *,
    cohort: UserCohort = UserCohort.ACTIVE,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> UserAdminPage:
    """Roster query for /admin/users. Always returns the page slice + total.

    Cohort filter semantics (every clause AND-ed with name-or-email
    ``search`` if provided):

    * ``ACTIVE``            — ``name IS NOT NULL AND is_active = true``
    * ``ALL``               — no filter (admin sees everything)
    * ``ADMINS``            — ``is_admin = true``
    * ``UNPAID``            — joined AND ``paid = false``
    * ``PAID``              — joined AND ``paid = true``
    * ``SIGNED_UP_ONLY``    — ``name IS NULL`` AND ``auth_provider = email``
                              AND no ``MagicLinkToken.used_at`` exists
                              (the magic link was sent but never clicked)
    * ``VERIFIED_ONLY``     — ``name IS NULL`` AND
                              (``auth_provider = google`` OR a token has
                              ``used_at IS NOT NULL``) — i.e. verified
                              the link / OAuth callback but abandoned
                              the /onboarding screen

    Search matches case-insensitively on ``User.email`` or ``User.name``.
    Empty / whitespace-only search is treated as no filter.

    Returns rows sorted newest-first by ``User.created_at`` (recent
    registrations bubble to the top — matches admin's most common
    "who just joined?" question).
    """
    # Pre-compute the "this user has verified a magic link" set as a
    # subquery so it can be joined into both the count and the page
    # statements without re-querying.
    verified_subq = (
        select(MagicLinkToken.user_id)
        .where(MagicLinkToken.used_at.is_not(None))
        .distinct()
        .subquery()
    )

    base = select(User).outerjoin(
        verified_subq, User.id == verified_subq.c.user_id
    )

    if cohort == UserCohort.ACTIVE:
        base = base.where(User.name.is_not(None)).where(User.is_active.is_(True))
    elif cohort == UserCohort.ADMINS:
        base = base.where(User.is_admin.is_(True))
    elif cohort == UserCohort.UNPAID:
        base = base.where(User.name.is_not(None)).where(User.paid.is_(False))
    elif cohort == UserCohort.PAID:
        base = base.where(User.name.is_not(None)).where(User.paid.is_(True))
    elif cohort == UserCohort.SIGNED_UP_ONLY:
        # EMAIL provider, no verified magic-link token.
        base = (
            base.where(User.name.is_(None))
            .where(User.auth_provider == AuthProvider.EMAIL)
            .where(verified_subq.c.user_id.is_(None))
        )
    elif cohort == UserCohort.VERIFIED_ONLY:
        # name IS NULL plus either Google OAuth (no token by definition)
        # or has a verified token. OR-ed to catch both flavours of
        # "started but didn't finish onboarding."
        base = base.where(User.name.is_(None)).where(
            or_(
                User.auth_provider == AuthProvider.GOOGLE,
                verified_subq.c.user_id.is_not(None),
            )
        )
    # UserCohort.ALL → no extra clause

    if search and search.strip():
        pat = f"%{search.strip()}%"
        base = base.where(or_(User.email.ilike(pat), User.name.ilike(pat)))

    # Total matching the same filters (count BEFORE limit/offset).
    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(count_stmt)).scalar_one() or 0)

    # Page slice.
    page_stmt = (
        base.order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    users = list((await session.execute(page_stmt)).scalars().all())

    if not users:
        return UserAdminPage(rows=[], total=total)

    user_ids = [u.id for u in users]

    # Batch the supplementary lookups so every page is exactly 4 queries
    # regardless of page size (entries, predictions, verified-token-set,
    # last_login, last_activity).
    counts_stmt = (
        select(
            PredictionEntry.user_id,
            func.count(PredictionEntry.id).label("total"),
            func.sum(
                case((PredictionEntry.status == EntryStatus.SUBMITTED, 1), else_=0)
            ).label("submitted"),
            func.sum(
                case((PredictionEntry.status == EntryStatus.DRAFT, 1), else_=0)
            ).label("draft"),
        )
        .where(PredictionEntry.user_id.in_(user_ids))
        .group_by(PredictionEntry.user_id)
    )
    entry_counts: dict[UUID, tuple[int, int, int]] = {}
    for uid, total_c, sub_c, draft_c in (await session.execute(counts_stmt)).all():
        entry_counts[uid] = (int(total_c or 0), int(sub_c or 0), int(draft_c or 0))

    pred_stmt = (
        select(PredictionEntry.user_id, func.count(MatchPrediction.id))
        .join(MatchPrediction, MatchPrediction.entry_id == PredictionEntry.id)
        .where(PredictionEntry.user_id.in_(user_ids))
        .group_by(PredictionEntry.user_id)
    )
    prediction_counts: dict[UUID, int] = {
        uid: int(c or 0)
        for uid, c in (await session.execute(pred_stmt)).all()
    }

    verified_ids_stmt = (
        select(MagicLinkToken.user_id)
        .where(MagicLinkToken.used_at.is_not(None))
        .where(MagicLinkToken.user_id.in_(user_ids))
        .distinct()
    )
    verified_ids: set[UUID] = {
        uid for (uid,) in (await session.execute(verified_ids_stmt)).all()
    }

    last_logins = await last_login_for_users(session, user_ids)
    last_activities = await last_activity_for_users(session, user_ids)

    rows: list[UserAdminRowV2] = []
    for u in users:
        total_c, sub_c, draft_c = entry_counts.get(u.id, (0, 0, 0))
        rows.append(
            UserAdminRowV2(
                id=u.id,
                email=u.email,
                name=u.name,
                auth_provider=u.auth_provider.value,
                is_admin=u.is_admin,
                is_active=u.is_active,
                paid=u.paid,
                paid_to=u.paid_to,
                employer=u.employer.value if u.employer else None,
                company_contact=u.company_contact,
                cohort=_derive_row_cohort(u, u.id in verified_ids),
                entries_count=total_c,
                submitted_entries_count=sub_c,
                draft_entries_count=draft_c,
                prediction_count=prediction_counts.get(u.id, 0),
                last_login_at=last_logins.get(u.id),
                last_activity_at=last_activities.get(u.id),
                created_at=u.created_at,
            )
        )

    return UserAdminPage(rows=rows, total=total)


async def list_inactive_emails(
    session: AsyncSession,
    *,
    cohort: Literal["signed_up_only", "verified_only", "both"] = "both",
) -> list[InactiveUserRow]:
    """Restricted projection for the re-engagement CSV export.

    Returns only the two inactive cohorts (1 + 2), with the minimum
    set of fields needed for a mailshot. Sorted by ``User.created_at``
    desc so the most recent signups are at the top.

    The two cohorts are *intentionally* exported with their cohort tag
    in the row so the admin can write different copy: cohort 1 needs a
    "your magic link is waiting" prompt, cohort 2 needs a "finish setting
    up your profile" prompt.
    """
    # Verified-magic-link set (per-user latest used_at), so we can both
    # classify the row AND populate last_magic_link_verified_at.
    verified_latest_subq = (
        select(
            MagicLinkToken.user_id.label("user_id"),
            func.max(MagicLinkToken.used_at).label("last_used"),
        )
        .where(MagicLinkToken.used_at.is_not(None))
        .group_by(MagicLinkToken.user_id)
        .subquery()
    )
    # Latest magic-link-token created_at per user (= last time we sent
    # them a link).
    sent_latest_subq = (
        select(
            MagicLinkToken.user_id.label("user_id"),
            func.max(MagicLinkToken.created_at).label("last_sent"),
        )
        .group_by(MagicLinkToken.user_id)
        .subquery()
    )

    stmt = (
        select(
            User,
            verified_latest_subq.c.last_used,
            sent_latest_subq.c.last_sent,
        )
        .outerjoin(verified_latest_subq, User.id == verified_latest_subq.c.user_id)
        .outerjoin(sent_latest_subq, User.id == sent_latest_subq.c.user_id)
        .where(User.name.is_(None))  # both inactive cohorts have NULL name
    )

    if cohort == "signed_up_only":
        stmt = stmt.where(User.auth_provider == AuthProvider.EMAIL).where(
            verified_latest_subq.c.last_used.is_(None)
        )
    elif cohort == "verified_only":
        stmt = stmt.where(
            or_(
                User.auth_provider == AuthProvider.GOOGLE,
                verified_latest_subq.c.last_used.is_not(None),
            )
        )
    # cohort == "both" → no extra filter

    stmt = stmt.order_by(User.created_at.desc())

    rows: list[InactiveUserRow] = []
    for u, last_used, last_sent in (await session.execute(stmt)).all():
        # Derive the row's cohort tag (same rule as list_users_with_cohort).
        if u.auth_provider == AuthProvider.GOOGLE or last_used is not None:
            row_cohort = UserCohort.VERIFIED_ONLY
        else:
            row_cohort = UserCohort.SIGNED_UP_ONLY
        rows.append(
            InactiveUserRow(
                email=u.email,
                cohort=row_cohort,
                created_at=u.created_at,
                last_magic_link_sent_at=last_sent,
                last_magic_link_verified_at=last_used,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _derive_row_cohort(user: User, has_verified_token: bool) -> UserCohort:
    """Per-row cohort label.

    The roster view assigns each user exactly ONE engagement-state
    cohort (the three states that matter for re-engagement). ``is_admin``,
    ``paid``, and ``is_active`` are surfaced as separate boolean fields
    on the row — they're orthogonal to cohort.

    Returns one of:
    * ``SIGNED_UP_ONLY`` — never verified
    * ``VERIFIED_ONLY``  — verified but abandoned onboarding
    * ``ACTIVE``         — completed onboarding (whether or not paid /
                           admin)
    """
    if user.name is None:
        if user.auth_provider == AuthProvider.GOOGLE or has_verified_token:
            return UserCohort.VERIFIED_ONLY
        return UserCohort.SIGNED_UP_ONLY
    return UserCohort.ACTIVE
