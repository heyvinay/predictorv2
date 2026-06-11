"""Admin-authored dashboard announcements (V4 Dashboard hero, v2.165.0).

Distinct from broadcast *emails* (`services/broadcast.py`): broadcasts are
fire-and-forget Resend sends with no stored body, while announcements are
persistent in-app news cards that rotate in the dashboard hero. An admin
writes them from /admin/announcements; every signed-in user sees the
published ones.

`tone` drives the tag-pill treatment on the frontend (gold = headline
matchday news, green = good news / payouts, mute = housekeeping). Kept as
a plain string rather than an enum so adding a tone is a frontend-only
change.
"""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models._datetime import utc_datetime_column, utc_now


class Announcement(SQLModel, table=True):
    """One dashboard announcement. Newest published first in the hero."""

    __tablename__ = "announcements"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Short tag-pill label, e.g. "Matchday", "Prizes", "Rules".
    tag: str = Field(max_length=32)
    # Pill tone: "gold" | "green" | "mute" (frontend mapping).
    tone: str = Field(default="gold", max_length=16)

    title: str = Field(max_length=120)
    body: str

    # Denormalized display name — announcements outlive admin renames and
    # the meta line ("Matt · admin · posted 10 Jun") needs no join.
    author_name: str = Field(max_length=80)

    # Unpublish instead of delete to pull a card without losing the text.
    published: bool = Field(default=True, index=True)

    created_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column(index=True)
    )
    updated_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column()
    )
