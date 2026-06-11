"""Dashboard announcements API (v2.165.0).

Two routers, mirroring entries.py's split:

* ``user_router`` → mounted at /api/announcements — signed-in users read
  the published feed for the dashboard hero. Auth required (the cards can
  carry pool-internal info — prize splits, nudges — that we don't want on
  an unauthenticated endpoint).
* ``admin_router`` → mounted at /api/admin/announcements — full CRUD.
  Every mutation writes an audit event in the same transaction.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.dependencies import AdminUser, CurrentUser, DbSession
from app.models._datetime import utc_now
from app.models.announcement import Announcement
from app.models.entry import ActorRole
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementRead,
    AnnouncementUpdate,
)
from app.services.audit import AuditContext, audit_context, record_audit_event

user_router = APIRouter()
admin_router = APIRouter()

AuditCtx = Annotated[AuditContext, Depends(audit_context)]

# The hero rotates a handful of cards; cap the feed so a chatty admin
# can't balloon the dashboard payload.
FEED_LIMIT = 10


@user_router.get("/", response_model=list[AnnouncementRead])
async def list_published_announcements(
    session: DbSession, user: CurrentUser
) -> list[Announcement]:
    """Published announcements, newest first, for the dashboard hero."""
    rows = await session.execute(
        select(Announcement)
        .where(Announcement.published.is_(True))
        .order_by(Announcement.created_at.desc())
        .limit(FEED_LIMIT)
    )
    return list(rows.scalars().all())


@admin_router.get("/", response_model=list[AnnouncementRead])
async def list_all_announcements(
    session: DbSession, admin: AdminUser
) -> list[Announcement]:
    """Every announcement (drafts included), newest first."""
    rows = await session.execute(
        select(Announcement).order_by(Announcement.created_at.desc())
    )
    return list(rows.scalars().all())


@admin_router.post(
    "/", response_model=AnnouncementRead, status_code=status.HTTP_201_CREATED
)
async def create_announcement(
    payload: AnnouncementCreate,
    session: DbSession,
    admin: AdminUser,
    ctx: AuditCtx,
) -> Announcement:
    announcement = Announcement(
        tag=payload.tag.strip(),
        tone=payload.tone,
        title=payload.title.strip(),
        body=payload.body.strip(),
        author_name=admin.name or admin.email,
        published=payload.published,
    )
    session.add(announcement)
    record_audit_event(
        session,
        event_type="announcement.created",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="announcement",
        subject_id=announcement.id,
        ctx=ctx,
        metadata={"title": announcement.title, "published": announcement.published},
    )
    await session.commit()
    await session.refresh(announcement)
    return announcement


async def _get_or_404(session: DbSession, announcement_id: UUID) -> Announcement:
    announcement = await session.get(Announcement, announcement_id)
    if announcement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found"
        )
    return announcement


@admin_router.patch("/{announcement_id}", response_model=AnnouncementRead)
async def update_announcement(
    announcement_id: UUID,
    payload: AnnouncementUpdate,
    session: DbSession,
    admin: AdminUser,
    ctx: AuditCtx,
) -> Announcement:
    announcement = await _get_or_404(session, announcement_id)
    changes: dict[str, object] = {}
    for field in ("tag", "tone", "title", "body", "published"):
        value = getattr(payload, field)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        if getattr(announcement, field) != value:
            changes[field] = value
            setattr(announcement, field, value)
    if changes:
        announcement.updated_at = utc_now()
        record_audit_event(
            session,
            event_type="announcement.updated",
            actor_user_id=admin.id,
            actor_role=ActorRole.ADMIN,
            subject_type="announcement",
            subject_id=announcement.id,
            ctx=ctx,
            metadata={"changed": sorted(changes.keys())},
        )
        await session.commit()
        await session.refresh(announcement)
    return announcement


@admin_router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_announcement(
    announcement_id: UUID,
    session: DbSession,
    admin: AdminUser,
    ctx: AuditCtx,
) -> None:
    announcement = await _get_or_404(session, announcement_id)
    record_audit_event(
        session,
        event_type="announcement.deleted",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="announcement",
        subject_id=announcement.id,
        ctx=ctx,
        metadata={"title": announcement.title},
    )
    await session.delete(announcement)
    await session.commit()
