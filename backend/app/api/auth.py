"""Authentication API routes."""

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
from app.models.entry import ActorRole
from app.models.user import AuthProvider, User
from app.schemas.auth import PasswordChange, Token, UserCreate, UserLogin, UserRead, UserStats
from app.services.audit import AuditContext, audit_context, record_audit_event
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


@router.post("/register", response_model=Token)
async def register(
    user_data: UserCreate, session: DbSession, ctx: AuditCtx
) -> Token:
    """Register a new user with email/password."""
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


@router.get("/me", response_model=UserRead)
async def get_current_user_info(current_user: CurrentUser) -> UserRead:
    """Get current user information."""
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
