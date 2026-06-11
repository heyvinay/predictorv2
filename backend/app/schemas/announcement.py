"""Pydantic schemas for dashboard announcements (v2.165.0)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Tone = Literal["gold", "green", "mute"]


class AnnouncementRead(BaseModel):
    id: UUID
    tag: str
    tone: str
    title: str
    body: str
    author_name: str
    published: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnnouncementCreate(BaseModel):
    tag: str = Field(min_length=1, max_length=32)
    tone: Tone = "gold"
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=2000)
    published: bool = True


class AnnouncementUpdate(BaseModel):
    """Partial update — only the provided fields change."""

    tag: str | None = Field(default=None, min_length=1, max_length=32)
    tone: Tone | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = Field(default=None, min_length=1, max_length=2000)
    published: bool | None = None
