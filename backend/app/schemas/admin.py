"""Pydantic response schemas for the v2.156.0 admin redesign.

Existing inline schemas in `app/api/admin.py` (AdminStats, UserAdminView,
BonusAnswerView, etc.) are unchanged. This file holds the NEW shared
shapes used by multiple services (audit reader, users cohort service,
posthog_read) and the new endpoints they power.

Co-locating these here prevents the circular-import shape that would
emerge if every service imported response models from `api/admin.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.prediction import BracketPrediction, MatchPredictionRead
from app.services.broadcast import BroadcastSegment


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
class AuditEventRead(BaseModel):
    """One row from the global audit feed, with actor name/email joined in.

    `actor_name` / `actor_email` are NULL for system events
    (failed-login-with-unknown-email, scheduler runs, etc.). The frontend
    renders these as "unauthenticated" / "system" using the actor_role
    + null actor_user_id combination.

    `event_metadata` carries the structured payload (e.g.
    `{"changed": ["name", "paid_to"]}` for `user.profile_updated`).
    `reason` is the free-form admin-supplied reason from a destructive
    action's confirmation modal (Pattern C in the redesign).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    actor_email: str | None
    actor_role: str
    subject_type: str | None
    subject_id: uuid.UUID | None
    ip_address: str | None
    event_metadata: dict[str, Any] | None
    reason: str | None
    created_at: datetime


class AuditEventPage(BaseModel):
    """Paginated wrapper for the audit feed."""

    rows: list[AuditEventRead]
    total: int


# ---------------------------------------------------------------------------
# User cohorts (feedback #2 from the redesign plan)
# ---------------------------------------------------------------------------
class UserCohort(str, Enum):
    """Derived from existing User + MagicLinkToken state — no schema change.

    Auth-provider-aware so Google OAuth users with name=NULL fall into
    `verified_only`, not into "phantom" status outside any cohort.

    - active           : completed onboarding AND admin hasn't deactivated
    - admins           : is_admin=True (subset of active)
    - unpaid           : completed onboarding AND paid=False
    - paid             : completed onboarding AND paid=True
    - signed_up_only   : EMAIL provider, name=NULL, no MagicLinkToken.used_at
    - verified_only    : name=NULL with EITHER (Google provider) OR (any
                         MagicLinkToken.used_at IS NOT NULL)
    - no_submission    : active, non-admin, zero counting submissions in
                         the active competition — exactly the set the
                         Close-the-pool action would disable (v2.169.0)
    - all              : no filter
    """

    ALL = "all"
    ACTIVE = "active"
    ADMINS = "admins"
    UNPAID = "unpaid"
    PAID = "paid"
    SIGNED_UP_ONLY = "signed_up_only"
    VERIFIED_ONLY = "verified_only"
    NO_SUBMISSION = "no_submission"


class UserAdminRowV2(BaseModel):
    """Users-list row including the derived cohort label, last_login,
    last_activity, and entry counts. Powers /admin/users.

    Derived fields explained:
      - cohort:        See UserCohort above.
      - last_login_at: MAX(audit_events.created_at) WHERE
                       event_type='auth.login_succeeded' AND
                       actor_user_id = user.id. None if user never logged in.
      - last_activity_at: MAX(audit_events.created_at) across ALL event
                       types where actor_user_id = user.id. Broader signal
                       (captures writes too).
      - entries_count, submitted_entries_count, draft_entries_count:
                       counts joined from PredictionEntry.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    auth_provider: str
    is_admin: bool
    is_active: bool
    paid: bool
    paid_to: str | None
    employer: str | None
    company_contact: str | None
    cohort: UserCohort
    entries_count: int
    submitted_entries_count: int
    draft_entries_count: int
    prediction_count: int
    last_login_at: datetime | None
    last_activity_at: datetime | None
    created_at: datetime


class UserAdminPage(BaseModel):
    """Paginated wrapper for the users list."""

    rows: list[UserAdminRowV2]
    total: int


class InactiveUserRow(BaseModel):
    """Row in the inactive-user CSV export used for re-engagement mailshots.

    Two cohorts get exported:
      - signed_up_only: address them as "you started signup but didn't
        click the magic link" — different CTA than cohort 2.
      - verified_only: "you logged in but didn't finish setting up your
        profile" — closer to the goal-line.
    """

    model_config = ConfigDict(from_attributes=True)

    email: str
    cohort: UserCohort
    created_at: datetime
    last_magic_link_sent_at: datetime | None
    # Most recent MagicLinkToken.used_at if any; for cohort 1 this is
    # always None.
    last_magic_link_verified_at: datetime | None


# ---------------------------------------------------------------------------
# User detail (drill-down page)
# ---------------------------------------------------------------------------
class UserDetailRead(BaseModel):
    """Full user detail payload — profile + summary metrics + recent
    activity. Renders /admin/users/[id]. Entries are NOT included here —
    the frontend fetches them via the existing admin_list_entries call
    filtered by user_id."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    auth_provider: str
    is_admin: bool
    is_active: bool
    paid: bool
    paid_to: str | None
    employer: str | None
    company_contact: str | None
    cohort: UserCohort
    entries_count: int
    submitted_entries_count: int
    draft_entries_count: int
    prediction_count: int
    last_login_at: datetime | None
    last_activity_at: datetime | None
    created_at: datetime
    recent_activity: list[AuditEventRead]


# ---------------------------------------------------------------------------
# PostHog engagement (Scope C)
# ---------------------------------------------------------------------------
class RecentSeen(BaseModel):
    """Batched response for the Users-list hover tooltip — one row per
    user. Built from a single HogQL query against PostHog events."""

    last_seen: datetime
    last_url: str | None


class EngagementSummary(BaseModel):
    """Full engagement mini-card for /admin/users/[id]. Designed as a
    general service — a future GET /api/me/engagement for personalized
    landing-page copy will return the same shape for the current user.

    All fields nullable: if PostHog is unreachable or the user has zero
    events, the frontend renders "—" placeholders instead of failing.
    """

    last_seen: datetime | None
    last_url: str | None
    session_count: int
    avg_session_seconds: float | None
    # 14 daily pageview counts, oldest → newest. Always exactly 14
    # elements (zero-filled for days with no activity). The frontend
    # renders this as the sparkline.
    sparkline_14d: list[int]


# ---------------------------------------------------------------------------
# Recent / upcoming fixtures (extends /admin/stats per redesign C9)
# ---------------------------------------------------------------------------
class FixtureMini(BaseModel):
    """Minimal fixture summary for the Score-sync card."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kickoff: datetime
    home_team: str
    away_team: str
    home_code: str | None
    away_code: str | None
    home_score: int | None
    away_score: int | None
    status: str


# ---------------------------------------------------------------------------
# Admin entry predictions (v2.157.0 — F1+F2+F3 slide-over real data)
# ---------------------------------------------------------------------------
class AdminBonusAnswer(BaseModel):
    """Minimal bonus answer for the admin slide-over Bonus tab.

    Carries the question's human-readable title server-side so the
    frontend doesn't need to know about the YAML config layout.
    """

    question_id: str
    question_title: str
    answer: str | None


class AdminEntryPredictions(BaseModel):
    """One round-trip payload for the slide-over Group / Knockout / Bonus tabs.

    Match predictions reuse `MatchPredictionRead` (already serializes
    home_team / away_team / kickoff / is_locked via fixture). Bracket is
    the existing aggregated shape. Bonus is a minimal projection — no
    category chip, no points value per user direction (v2.157.0 scope).
    """

    match_predictions: list[MatchPredictionRead]
    bracket: BracketPrediction | None
    bonus_answers: list[AdminBonusAnswer]


# ---------------------------------------------------------------------------
# Broadcast emails (v2.160.0)
# ---------------------------------------------------------------------------
class BroadcastAudienceCounts(BaseModel):
    """Live count for each of the three segments — feeds the badges on
    the broadcast card."""

    submitters: int
    no_entry: int
    draft_holders: int


class BroadcastTestRequest(BaseModel):
    """Request body for ``POST /admin/broadcasts/test``.

    ``to_email`` is optional — when ``None`` the endpoint defaults to
    the calling admin's own email. The override exists so admins can
    test-send to alternate addresses (e.g. their personal Gmail for
    cross-client rendering checks).
    """

    segment: BroadcastSegment
    to_email: str | None = None


class BroadcastTestResult(BaseModel):
    """Result of one single-recipient test send.

    ``sent`` is False when Resend returned an error; ``error`` carries
    a short reason for the admin toast. ``to_email`` echoes back the
    address that was used (so the admin knows whether the default or
    override was applied).
    """

    sent: bool
    to_email: str
    error: str | None = None


class BroadcastSendRequest(BaseModel):
    """Request body for ``POST /admin/broadcasts``.

    ``dry_run=True`` (default) → no emails sent, just the preview count.
    ``dry_run=False`` → real broadcast, one Resend call per audience row.
    The confirmation modal calls dry_run=True on open, then dry_run=False
    on confirm.
    """

    segment: BroadcastSegment
    dry_run: bool = True


class BroadcastSendResult(BaseModel):
    """Result of ``POST /admin/broadcasts``.

    Shape is uniform across dry-run and real sends so the frontend
    doesn't need to discriminate union responses. Field semantics:

    * ``dry_run`` — echoes the request flag.
    * ``audience_count`` — total matching audience size (same in both modes).
    * ``sent`` — number of successful Resend calls. 0 when dry_run=True.
    * ``failed`` — number of failed Resend calls. 0 when dry_run=True.
    * ``sample_emails`` — dry-run: first 5 recipient emails (preview).
      Real send: first 3 *failed* recipient emails (so the admin can
      eyeball-check what went wrong).
    """

    dry_run: bool
    segment: BroadcastSegment
    audience_count: int
    sent: int
    failed: int
    sample_emails: list[str]
