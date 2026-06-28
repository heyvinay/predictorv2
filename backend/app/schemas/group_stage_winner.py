"""Pydantic schemas for the Group Stage podium endpoint.

The endpoint URL stays ``/api/leaderboard/group-stage-winner`` (no
client breakage from external consumers) but the response shape upgrades
from a single-winner record to a podium of the top 3 entries plus a
shared composed-narrative + audit flag.

The OpenAPI surface mirrors the dataclasses in
``services/group_stage_winner.py`` field-for-field.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GroupStageEntry(BaseModel):
    """One row on the podium — winner, runner-up, or third-place."""

    entry_id: str
    user_name: str
    entry_name: str
    # Pre-computed display name following the leaderboard convention:
    # bare ``user_name`` when the owner holds a single entry, otherwise
    # ``user_name — short_entry_name`` where ``short_entry_name`` has the
    # owner's name stripped from the front to avoid "James Vella —
    # James Vella 3rd Entry" duplication. Frontend renders this verbatim.
    display_name: str
    final_rank: int
    total_points: int

    # 4-part breakdown — sums to total_points.
    outcome_points: int
    exact_score_extra: int
    rarity_extra: int
    bonus_question_points: int


class GroupStagePodium(BaseModel):
    """Top-3 podium with a winner-centred narrative + audit verification.

    Returned by ``GET /api/leaderboard/group-stage-winner`` (URL preserved
    from v2.181.0 to avoid breaking external consumers; payload shape
    upgraded in v2.183.x to surface the runners-up alongside the champion).
    """

    # Top 3 entries in rank order (entries[0] is the winner). May be
    # shorter than 3 in degenerate cases (pool with < 3 eligible entries).
    entries: list[GroupStageEntry]

    # Story stats — context the narrative draws on. Surfaced separately
    # so the frontend can show them as supporting numbers if it wants.
    champion_pick: str | None
    champion_alive: bool
    finalist_picks: list[str]
    finalists_alive: int
    days_at_top: int
    total_days: int
    runner_up_gap: int | None

    # Pre-composed narrative — card and email both render this verbatim.
    # Refers to runner-up by name, so it lives at podium level (not on
    # the winner entry).
    story_line: str

    # Audit verification claim — drives the "Verified ✓" pill on the
    # card. Currently hard-coded True after the v2.183.x audit pipeline;
    # could gate on a future Competition.audit_verified flag.
    audit_verified: bool

    generated_at: datetime
