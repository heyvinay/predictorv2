"""API shapes for the pool-vs-tournament retrospective (Plan A §8)."""

from pydantic import BaseModel


class MatchCallOut(BaseModel):
    label: str          # "M23 · Morocco 2–0 Belgium"
    pct: float          # share of pool with the correct outcome pick
    exact_count: int


class KoLadderRowOut(BaseModel):
    stage: str          # 'round_of_32' … 'final' | 'winner'
    consensus_had: int
    of: int
    fallen_teams: list[str]


class BonusAnswerOut(BaseModel):
    question_id: str
    label: str
    answer_label: str
    hit_pct: float


class ChampionPickOut(BaseModel):
    team: str
    count: int
    is_actual: bool


class SuperlativeOut(BaseModel):
    emoji: str
    title: str
    body: str


class PersonalWrapOut(BaseModel):
    entry_id: str
    entry_name: str
    final_rank: int
    total_points: int
    group_points: int
    knockout_points: int
    bonus_points: int
    percentile_label: str        # "top 4% of the pool"
    superlatives: list[SuperlativeOut]


class PoolRetrospective(BaseModel):
    group_called_right: int
    group_total: int
    final_called_right_pct: float
    final_winner_team: str | None
    exact_total: int
    exact_avg_per_entry: float
    misses: list[MatchCallOut]
    bankers: list[MatchCallOut]
    ko_ladder: list[KoLadderRowOut]
    bonus: list[BonusAnswerOut]
    champion_distribution: list[ChampionPickOut]
    personal: list[PersonalWrapOut] | None
