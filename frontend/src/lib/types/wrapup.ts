/** Wrap-up page payloads (Plan C). Import directly, never via $types
 * (V4 convention: barrel is held open by WIP).
 *
 * Mirrors backend/app/schemas/tournament_champion.py (FinalPodium) and
 * backend/app/schemas/pool_retrospective.py (PoolRetrospective) field for
 * field — verified against the real schema files on this branch, not the
 * plan draft. `FinalMatchOut.kickoff` is a Python `datetime | None`, which
 * Pydantic serializes as an ISO 8601 string; typed `string | null` here. */

export interface FinalPodiumEntry {
	entry_id: string;
	user_name: string;
	entry_name: string;
	final_rank: number;
	total_points: number;
	group_points: number;
	knockout_points: number;
	bonus_points: number;
	exact_scores: number;
	rarity_points: number;
	days_at_top: number;
	champion_pick: string | null;
	champion_hit: boolean;
	is_champion: boolean;
}

export interface TriondaOut {
	recipient_name: string | null;
	recipient_entry_id: string | null;
	final_rank: number | null;
	reason: string;
	requires_draw: boolean;
	draw_candidate_names: string[];
}

export interface FinalMatchOut {
	home_team: string;
	away_team: string;
	home_score: number | null;
	away_score: number | null;
	went_to_extra_time: boolean;
	penalties: string | null;
	kickoff: string | null;
	venue: string | null;
	narrative: string | null;
}

export interface AuditSummaryOut {
	run_at: string;
	entries_verified: number;
	matches_rescored: number;
	bonus_questions: number;
	discrepancies: number;
	sources: string[];
}

export interface FinalPodium {
	entries: FinalPodiumEntry[];
	trionda: TriondaOut;
	story_line: string;
	total_days: number;
	final_match: FinalMatchOut | null;
	audit: AuditSummaryOut | null;
}

export interface MatchCallOut {
	label: string;
	pct: number;
	exact_count: number;
}

export interface KoLadderRowOut {
	stage: string;
	consensus_had: number;
	of: number;
	fallen_teams: string[];
}

export interface BonusAnswerOut {
	question_id: string;
	label: string;
	answer_label: string;
	hit_pct: number;
}

export interface ChampionPickOut {
	team: string;
	count: number;
	is_actual: boolean;
}

export interface SuperlativeOut {
	emoji: string;
	title: string;
	body: string;
}

export interface PersonalWrapOut {
	entry_id: string;
	entry_name: string;
	final_rank: number;
	total_points: number;
	group_points: number;
	knockout_points: number;
	bonus_points: number;
	percentile_label: string;
	superlatives: SuperlativeOut[];
}

export interface PoolRetrospective {
	group_called_right: number;
	group_total: number;
	final_called_right_pct: number;
	final_winner_team: string | null;
	exact_total: number;
	exact_avg_per_entry: number;
	misses: MatchCallOut[];
	bankers: MatchCallOut[];
	ko_ladder: KoLadderRowOut[];
	bonus: BonusAnswerOut[];
	champion_distribution: ChampionPickOut[];
	personal: PersonalWrapOut[] | null;
}
