"""Authentication API routes.

Supports three sign-in flows:

* Magic link (passwordless, primary) — :func:`request_magic_link` +
  :func:`verify_magic_link`. The user submits their email, gets a
  one-time link, and on click is redirected to the frontend with a JWT.
  New emails create new users on first request.
* Google OAuth — :func:`google_login` + :func:`google_callback`.
* Email + password (legacy) — :func:`register` + :func:`login`. Kept
  for back-compat with existing accounts that already have passwords.
"""

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi_sso.sso.google import GoogleSSO
from sqlmodel import select

from app.config import get_settings
from app.dependencies import (
    CurrentUser,
    DbSession,
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.models.entry import ActorRole
from app.models.magic_link_token import MagicLinkToken, generate_magic_token, hash_token
from app.models.user import AuthProvider, User
from app.schemas.auth import (
    MagicLinkRequest,
    MagicLinkResponse,
    PasswordChange,
    Token,
    UserCreate,
    UserLogin,
    UserRead,
    UserStats,
    UserUpdate,
)
from app.services.audit import AuditContext, audit_context, record_audit_event
from app.services.captcha import verify_turnstile
from app.services.email import send_magic_link_email
from app.services.profile import calculate_user_stats

router = APIRouter()

AuditCtx = Annotated[AuditContext, Depends(audit_context)]


def get_google_sso() -> GoogleSSO:
    """Get Google SSO instance."""
    settings = get_settings()
    return GoogleSSO(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
        allow_insecure_http=settings.debug,
    )


SIGNUPS_CLOSED_DETAIL = (
    "Entries are closed — the World Cup 2026 pool locked at the deadline. "
    "New signups are no longer accepted."
)


async def _signups_closed(session: DbSession) -> bool:
    """True once the active competition's phase-1 deadline has passed.

    Door policy (v2.166.0): NEW account creation is refused after the
    deadline — an account created now could never hold a scoring entry
    and the close-out job would disable it minutes later. Existing
    users keep signing in normally (they need to see results).
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if competition is None or competition.phase1_deadline is None:
        return False
    return utc_now() >= aware_utc(competition.phase1_deadline)


@router.post("/register", response_model=Token)
async def register(
    user_data: UserCreate, session: DbSession, ctx: AuditCtx
) -> Token:
    """Register a new user with email/password."""
    if await _signups_closed(session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=SIGNUPS_CLOSED_DETAIL,
        )

    # Check if email already exists
    result = await session.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        # Audit the failed-registration attempt — important forensic signal
        # for someone probing existing emails.
        record_audit_event(
            session,
            event_type="auth.register_failed",
            actor_user_id=None,
            actor_role=ActorRole.SYSTEM,
            ctx=ctx,
            metadata={"email": user_data.email, "reason": "email_exists"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=user_data.email,
        name=user_data.name,
        password_hash=get_password_hash(user_data.password),
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(user)
    await session.flush()  # populate user.id before audit row references it
    record_audit_event(
        session,
        event_type="auth.registered",
        actor_user_id=user.id,
        actor_role=ActorRole.USER,
        subject_type="user",
        subject_id=user.id,
        ctx=ctx,
        metadata={"email": user.email, "auth_provider": user.auth_provider.value},
    )
    await session.commit()
    await session.refresh(user)

    # Generate token
    access_token = create_access_token(
        user_id=str(user.id),
        expires_delta=timedelta(minutes=get_settings().jwt_access_token_expire_minutes),
    )

    return Token(access_token=access_token)


@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin, session: DbSession, ctx: AuditCtx
) -> Token:
    """Login with email/password."""
    result = await session.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        # Unknown email or password-less account. actor_user_id stays None
        # so we don't lie about "who" did this.
        record_audit_event(
            session,
            event_type="auth.login_failed",
            actor_user_id=None,
            actor_role=ActorRole.SYSTEM,
            ctx=ctx,
            metadata={"email": credentials.email, "reason": "unknown_user"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(credentials.password, user.password_hash):
        record_audit_event(
            session,
            event_type="auth.login_failed",
            actor_user_id=user.id,
            actor_role=ActorRole.SYSTEM,
            subject_type="user",
            subject_id=user.id,
            ctx=ctx,
            metadata={"email": user.email, "reason": "bad_password"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        record_audit_event(
            session,
            event_type="auth.login_failed",
            actor_user_id=user.id,
            actor_role=ActorRole.SYSTEM,
            subject_type="user",
            subject_id=user.id,
            ctx=ctx,
            metadata={"email": user.email, "reason": "inactive_account"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    record_audit_event(
        session,
        event_type="auth.login_succeeded",
        actor_user_id=user.id,
        actor_role=ActorRole.USER,
        subject_type="user",
        subject_id=user.id,
        ctx=ctx,
        metadata={"email": user.email, "auth_provider": user.auth_provider.value},
    )
    await session.commit()

    access_token = create_access_token(
        user_id=str(user.id),
        expires_delta=timedelta(minutes=get_settings().jwt_access_token_expire_minutes),
    )

    return Token(access_token=access_token)


@router.get("/google")
async def google_login():
    """Initiate Google OAuth login."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )

    google_sso = get_google_sso()
    return await google_sso.get_login_redirect()


@router.get("/google/callback")
async def google_callback(request: Request, session: DbSession, ctx: AuditCtx):
    """Handle Google OAuth callback."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )

    google_sso = get_google_sso()

    try:
        google_user = await google_sso.verify_and_process(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to authenticate with Google: {e}",
        )

    if not google_user or not google_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to get user info from Google",
        )

    # Check if user exists by Google ID
    result = await session.execute(select(User).where(User.google_id == google_user.id))
    user = result.scalar_one_or_none()

    audit_event_type = "auth.login_succeeded"  # default; overridden on create/link
    if not user:
        # Check if email exists (link accounts)
        result = await session.execute(select(User).where(User.email == google_user.email))
        user = result.scalar_one_or_none()

        if user:
            # Link Google account to existing user
            user.google_id = google_user.id
            user.auth_provider = AuthProvider.GOOGLE
            audit_event_type = "auth.oauth_linked"
        else:
            # Door policy: no NEW accounts via OAuth after the deadline.
            if await _signups_closed(session):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=SIGNUPS_CLOSED_DETAIL,
                )
            # Create new user
            user = User(
                email=google_user.email,
                name=google_user.display_name or google_user.email.split("@")[0],
                google_id=google_user.id,
                auth_provider=AuthProvider.GOOGLE,
            )
            session.add(user)
            audit_event_type = "auth.registered"

        await session.flush()  # populate user.id for audit
        await session.commit()
        await session.refresh(user)

    if not user.is_active:
        record_audit_event(
            session,
            event_type="auth.login_failed",
            actor_user_id=user.id,
            actor_role=ActorRole.SYSTEM,
            subject_type="user",
            subject_id=user.id,
            ctx=ctx,
            metadata={"email": user.email, "reason": "inactive_account"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # Audit the successful Google login / link / register.
    record_audit_event(
        session,
        event_type=audit_event_type,
        actor_user_id=user.id,
        actor_role=ActorRole.USER,
        subject_type="user",
        subject_id=user.id,
        ctx=ctx,
        metadata={
            "email": user.email,
            "auth_provider": user.auth_provider.value,
            "google_id": user.google_id,
        },
    )
    await session.commit()

    # Generate token
    access_token = create_access_token(
        user_id=str(user.id),
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )

    # Redirect to frontend with token
    frontend_url = settings.cors_origins[0] if settings.cors_origins else "http://localhost:5173"
    return RedirectResponse(url=f"{frontend_url}/auth/callback?token={access_token}")


# ── Magic-link (passwordless) flow ──────────────────────────────────────────


# Per-email throttle: don't issue a fresh token if the most recent one is
# younger than this. Matches the frontend's 60 s "resend cooldown" so the
# UI and backend agree.
_MAGIC_LINK_THROTTLE_SECONDS = 60


@router.post("/request-magic-link", response_model=MagicLinkResponse)
async def request_magic_link(
    payload: MagicLinkRequest, session: DbSession, request: Request
) -> MagicLinkResponse:
    """Issue a one-time sign-in link to the supplied email address.

    Behaviour:
      * If the email is **unknown**, a new User is created with
        ``name=None``, ``auth_provider=EMAIL``, ``password_hash=None``.
        The user fills in their name on /onboarding after first verify.
      * If the email is **known**, the existing User is reused — the
        token row is independent so multiple-tab scenarios work.
      * If the user has requested a token in the last
        ``_MAGIC_LINK_THROTTLE_SECONDS`` and that token is still
        unused, return 429 — prevents email-bombing a victim.

    Always returns the same generic ``message`` regardless of whether
    the email was previously known, so this endpoint can't be used to
    enumerate accounts.
    """
    settings = get_settings()

    # Gate on Cloudflare Turnstile before doing anything else (this is the
    # only unauthenticated, account-creating endpoint). No-ops in dev when
    # no secret key is configured.
    client_ip = request.client.host if request.client else None
    if not await verify_turnstile(payload.captcha_token, client_ip):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Captcha verification failed. Please try again.",
        )

    email = payload.email.lower().strip()

    # Find-or-create user.
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        # Door policy: post-deadline, unknown emails don't get an
        # account. Return the same generic message (no enumeration
        # leak) — they simply never receive a link.
        if await _signups_closed(session):
            return MagicLinkResponse(
                message="If that email is registered, a sign-in link is on its way."
            )
        user = User(email=email, name=None, auth_provider=AuthProvider.EMAIL)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif not user.is_active:
        # Don't leak inactive-account state to the email submitter —
        # return the same generic message but skip sending.
        return MagicLinkResponse(
            message="If that email is registered, a sign-in link is on its way."
        )

    # Throttle: reject if there's an unused token less than 60 s old.
    now = utc_now()
    recent_q = await session.execute(
        select(MagicLinkToken)
        .where(MagicLinkToken.user_id == user.id)
        .where(MagicLinkToken.used_at.is_(None))
        .order_by(MagicLinkToken.created_at.desc())
        .limit(1)
    )
    recent = recent_q.scalar_one_or_none()
    if recent is not None:
        age = (now - aware_utc(recent.created_at)).total_seconds()
        if age < _MAGIC_LINK_THROTTLE_SECONDS:
            wait = int(_MAGIC_LINK_THROTTLE_SECONDS - age)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait}s before requesting another link.",
                headers={"Retry-After": str(wait)},
            )

    # Mint token, store hash, send email with raw.
    raw_token, token_hash = generate_magic_token()
    token_row = MagicLinkToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(minutes=settings.magic_link_expire_minutes),
    )
    session.add(token_row)
    await session.commit()

    magic_link_url = (
        f"{settings.frontend_url}/api/auth/verify-magic-link?token={raw_token}"
    )
    try:
        await send_magic_link_email(to_email=email, magic_link_url=magic_link_url)
    except RuntimeError:
        # Email delivery failed — surface a generic 500 so the user can retry.
        # The token row stays in the DB; if they request again within 60 s
        # they'll be throttled, otherwise a new token is issued.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send sign-in email. Please try again in a minute.",
        )

    return MagicLinkResponse(
        message="If that email is registered, a sign-in link is on its way."
    )


@router.get("/verify-magic-link")
async def verify_magic_link(
    token: str, session: DbSession, ctx: AuditCtx
) -> RedirectResponse:
    """Validate a magic link token and redirect to the frontend with a JWT.

    Called by the user's browser when they click the link in their
    email. The raw token is hashed and looked up; if valid and unused,
    the token is marked used, a JWT is issued, and the browser is
    302'd to ``{frontend_url}/auth/callback?token=<jwt>`` (the same
    callback page Google OAuth uses, so the frontend has one code path
    for "we got a JWT, store it and fetch the user").
    """
    settings = get_settings()
    incoming_hash = hash_token(token)

    result = await session.execute(
        select(MagicLinkToken).where(MagicLinkToken.token_hash == incoming_hash)
    )
    token_row = result.scalar_one_or_none()

    # Generic rejection for any failure mode — don't help attackers
    # distinguish "wrong token" from "expired" from "already used".
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This sign-in link is invalid, expired, or already used.",
    )

    if token_row is None:
        raise invalid
    if token_row.used_at is not None:
        raise invalid
    if aware_utc(token_row.expires_at) < utc_now():
        raise invalid

    # Mark used (single-use enforcement).
    token_row.used_at = utc_now()
    session.add(token_row)

    # Load user to confirm still active.
    user_q = await session.execute(select(User).where(User.id == token_row.user_id))
    user = user_q.scalar_one_or_none()
    if user is None or not user.is_active:
        await session.commit()
        raise invalid

    # v2.156.0 — fire auth.login_succeeded so magic-link verifies show up
    # in the audit log alongside password + Google logins. Makes
    # audit_events the authoritative source for "last login" derived on
    # /admin/users without needing a separate last_login_at column.
    record_audit_event(
        session,
        event_type="auth.login_succeeded",
        actor_user_id=user.id,
        actor_role=ActorRole.USER,
        subject_type="user",
        subject_id=user.id,
        ctx=ctx,
        metadata={"email": user.email, "auth_provider": "magic_link"},
    )

    await session.commit()

    access_token = create_access_token(
        user_id=str(user.id),
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )

    # Redirect to the same callback page Google OAuth uses.
    return RedirectResponse(
        url=f"{settings.frontend_url}/auth/callback?token={access_token}"
    )


# ── Profile endpoints ───────────────────────────────────────────────────────


@router.get("/me", response_model=UserRead)
async def get_current_user_info(current_user: CurrentUser) -> UserRead:
    """Get current user information."""
    return UserRead.model_validate(current_user)


@router.patch("/me", response_model=UserRead)
async def update_current_user(
    payload: UserUpdate,
    current_user: CurrentUser,
    session: DbSession,
    ctx: AuditCtx,
) -> UserRead:
    """Update the current user's profile.

    Primary caller is the /onboarding page (new magic-link users
    setting their display name for the first time), but also handles
    later profile edits.

    v2.156.0 — fires a ``user.profile_updated`` audit event listing the
    field names that actually changed (not values, to keep audit rows
    light and PII-clean). Idempotent no-op PATCHes do NOT fire the
    event — we compare each incoming field against the current value
    and only record genuinely-changed keys. This closes the "Last
    activity" signal gap: profile edits now land in the audit stream
    alongside auth and entry events.
    """
    # Track which fields actually changed so the audit metadata only
    # records real diffs. Comparing against the *current* value before
    # assignment is the cleanest way — an `is not None` payload that
    # repeats the existing value isn't an edit.
    changed: list[str] = []

    if payload.name is not None and payload.name != current_user.name:
        current_user.name = payload.name
        changed.append("name")
    if payload.email is not None and payload.email != current_user.email:
        # Email changes go through their own flow normally; we accept
        # here for parity with the schema but enforce uniqueness.
        existing = await session.execute(
            select(User).where(User.email == payload.email).where(User.id != current_user.id)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That email is already in use.",
            )
        current_user.email = payload.email
        changed.append("email")
    if payload.employer is not None and payload.employer != current_user.employer:
        current_user.employer = payload.employer
        changed.append("employer")
    if (
        payload.company_contact is not None
        and payload.company_contact != current_user.company_contact
    ):
        current_user.company_contact = payload.company_contact
        changed.append("company_contact")
    if payload.paid_to is not None and payload.paid_to != current_user.paid_to:
        current_user.paid_to = payload.paid_to
        changed.append("paid_to")

    if changed:
        # Only audit when something actually changed. Idempotent no-op
        # PATCHes (all fields unchanged) leave no audit trail — they
        # didn't change state, so they shouldn't show up in the "Last
        # activity" / audit feed as if they did.
        current_user.updated_at = utc_now()
        record_audit_event(
            session,
            event_type="user.profile_updated",
            actor_user_id=current_user.id,
            actor_role=ActorRole.USER,
            subject_type="user",
            subject_id=current_user.id,
            ctx=ctx,
            metadata={"changed": changed},
        )
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.post("/me/password")
async def change_password(
    data: PasswordChange,
    current_user: CurrentUser,
    session: DbSession,
    ctx: AuditCtx,
) -> dict[str, str]:
    """Change password for email-authenticated users."""
    if current_user.auth_provider != AuthProvider.EMAIL:
        record_audit_event(
            session,
            event_type="auth.password_change_failed",
            actor_user_id=current_user.id,
            actor_role=ActorRole.USER,
            subject_type="user",
            subject_id=current_user.id,
            ctx=ctx,
            metadata={"reason": "non_email_account"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change is only available for email accounts",
        )

    if not current_user.password_hash or not verify_password(
        data.current_password, current_user.password_hash
    ):
        record_audit_event(
            session,
            event_type="auth.password_change_failed",
            actor_user_id=current_user.id,
            actor_role=ActorRole.USER,
            subject_type="user",
            subject_id=current_user.id,
            ctx=ctx,
            metadata={"reason": "wrong_current_password"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.password_hash = get_password_hash(data.new_password)
    session.add(current_user)
    record_audit_event(
        session,
        event_type="auth.password_changed",
        actor_user_id=current_user.id,
        actor_role=ActorRole.USER,
        subject_type="user",
        subject_id=current_user.id,
        ctx=ctx,
    )
    await session.commit()

    return {"message": "Password updated successfully"}


@router.get("/me/stats", response_model=UserStats)
async def get_user_stats(
    current_user: CurrentUser,
    session: DbSession,
    entry_id: uuid.UUID | None = Query(
        None,
        description="Specific entry to report stats for. If omitted, picks the user's most recently-updated eligible entry.",
    ),
) -> UserStats:
    """Profile statistics for one of the user's entries.

    Stats are entry-scoped — there is no user-level aggregate. Pass
    `entry_id` to target a specific entry, or omit it to use the user's
    most recently-updated eligible entry as the default.
    """
    return await calculate_user_stats(session, current_user.id, entry_id=entry_id)
