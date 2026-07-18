"""API shapes for the final podium / conclusion payload (Plan A)."""

from datetime import datetime

from pydantic import BaseModel


class FinalPodiumEntry(BaseModel):
    entry_id: str
    user_name: str
    entry_name: str
    final_rank: int
    total_points: int
    group_points: int
    knockout_points: int
    bonus_points: int
    exact_scores: int
    rarity_points: int
    days_at_top: int
    champion_pick: str | None
    champion_hit: bool
    is_champion: bool


class TriondaOut(BaseModel):
    recipient_name: str | None
    recipient_entry_id: str | None
    final_rank: int | None
    reason: str
    requires_draw: bool
    draw_candidate_names: list[str] = []


class FinalMatchOut(BaseModel):
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    went_to_extra_time: bool
    penalties: str | None  # e.g. "4-2" or None
    kickoff: datetime | None
    venue: str | None
    narrative: str | None


class AuditSummaryOut(BaseModel):
    run_at: str
    entries_verified: int
    matches_rescored: int
    bonus_questions: int
    discrepancies: int
    sources: list[str]


class FinalPodium(BaseModel):
    entries: list[FinalPodiumEntry]
    trionda: TriondaOut
    story_line: str
    total_days: int
    final_match: FinalMatchOut | None
    audit: AuditSummaryOut | None
