/**
 * V4 Leaderboard types (v2.164.0).
 *
 * Lives outside the `$lib/types` barrel deliberately — the barrel
 * (types/index.ts) carries uncommitted user WIP and must not be touched.
 * Import directly: `from '$lib/types/leaderboard'`.
 */

import type { LeaderboardEntry } from '$types';

/** Page view switcher state, persisted to localStorage['predictor:lb:view']. */
export type LbView = 'table' | 'race' | 'insights';

/** Pool filter, persisted to localStorage['predictor:lb:pool'].
 *  Pools map onto User.employer: atlas → Atlas, jmfa → JMFA,
 *  neither/null → Guests. */
export type LbPool = 'All' | 'Atlas' | 'JMFA' | 'Guests';

/** Tournament stage — derived from fixtures (lineup-based), never user-set. */
export type LbStage = 'group' | 'knockout';

/** LeaderboardEntry as served since v2.164.0 — the V4 fields exist on the
 *  wire but not on the barrel interface (user WIP lockout). */
export type LbEntryV4 = LeaderboardEntry & {
	/** "atlas" | "jmfa" | "neither" | null (pre-onboarding). */
	employer?: string | null;
	champion_pick?: string | null;
	champion_alive?: boolean;
	finalist_picks?: string[];
	finalists_alive?: number;
	/** Rank delta vs yesterday's snapshot; null until one exists. */
	daily_movement?: number | null;
	/** Settled bonus points by category — group_stage → group column,
	 *  top_flop/awards → knockout column. */
	bonus_group_points?: number;
	bonus_knockout_points?: number;
};

export interface LbResponseV4 {
	entries: LbEntryV4[];
	last_calculated: string;
	total_participants: number;
	phase: string | null;
	/**
	 * Public URL of the shared Google Sheet (all-entries picks/points/history).
	 * Null when sheets_sync isn't configured server-side. The leaderboard
	 * page uses this to conditionally render the "View All Entries" button.
	 */
	published_sheet_url: string | null;
}

/** Points DNA — where an entry's points come from. Sums to breakdown.total. */
export interface DnaSplit {
	exact: number;
	result: number;
	rarity: number;
	bracket: number;
	bonus: number;
}

/** One bonus-prediction row as served since v2.164.0 (read routes). */
export interface BonusPredictionRead {
	question_id: string;
	answer: string;
	category: 'group_stage' | 'top_flop' | 'awards' | null;
	points: number | null;
	/** null = question not settled yet. */
	hit: boolean | null;
}

/** Bonus question metadata from GET /api/predictions/bonus/questions. */
export interface BonusQuestionMeta {
	id: string;
	category: 'group_stage' | 'top_flop' | 'awards';
	label: string;
	input_type: string;
	points: number;
}

/** One day's rank + points for an entry (shared with single-entry routes). */
export interface RankPoint {
	position: number;
	total_points: number;
	captured_date: string; // ISO date YYYY-MM-DD
}

/** One entry's labelled rank path for the Race chart. */
export interface EntryTrajectory {
	entry_id: string;
	entry_name: string;
	user_id: string;
	user_name: string;
	points: RankPoint[];
}

/** GET /api/leaderboard/snapshots — every eligible entry's trajectory. */
export interface AllTrajectoriesResponse {
	days: number;
	entries: EntryTrajectory[];
	total_participants: number;
}

/** Folded bonus points per phase column (Q1–Q2 → group, Q3–Q4 → knockout). */
export interface BonusFold {
	group: number;
	knockout: number;
	groupHits: number;
	knockoutHits: number;
	/** Settled-and-hit count across all questions (for "n/4 bonus"). */
	hits: number;
	answered: number;
}

// ---------------------------------------------------------------------------
// Race-tab redesign types (2026-06-22 spec)
// ---------------------------------------------------------------------------

export type RaceViewMode = 'around_me' | 'top15';

export interface MinimapMarker {
	rank: number;
	kind: 'you' | 'leader';
}

export interface RaceSliceDescriptor {
	included: EntryTrajectory[];
	minimapMarkers: MinimapMarker[];
	rankRange: [number, number];
}

export type RaceStoryKind =
	| 'biggest_climb'
	| 'steepest_fall'
	| 'closest_race'
	| 'hottest_streak';

export interface SparklinePoint {
	captured_date: string;
	rank: number;
}

export interface RaceStory {
	kind: RaceStoryKind;
	title: string;
	caption: string;
	subject_entry_id: string;
	compare_entry_id: string | null;
	sparkline: SparklinePoint[];
	compare_sparkline: SparklinePoint[] | null;
}

export interface RaceStoriesResponse {
	stories: RaceStory[];
	generated_at: string;
}

export interface ChampionTeamCount {
	team_code: string;
	team_name: string;
	count: number;
	alive: boolean;
}

export interface ChampionSurvivalResponse {
	alive_count: number;
	total_count: number;
	teams: ChampionTeamCount[];
	generated_at: string;
}

export interface MatchMarker {
	fixture_id: number;
	kickoff: string;
	home_team_code: string;
	away_team_code: string;
	home_score: number;
	away_score: number;
	is_upset: boolean;
	impact_score: number;
}

export interface MatchMarkersResponse {
	markers: MatchMarker[];
	generated_at: string;
}

// ---------------------------------------------------------------------------
// Dashboard widget types (2026-06-22 spec)
// ---------------------------------------------------------------------------

export interface DailyMvp {
	captured_date: string;
	subject_entry_id: string;
	user_name: string;
	entry_name: string;
	day_points: number;
	rank_delta: number;
}

export interface DailyMvpsResponse {
	mvps: DailyMvp[];
	generated_at: string;
}

export interface TrailPoint {
	captured_date: string;
	your_points: number;
	pool_avg_points: number;
}

export interface EntryTrail {
	entry_id: string;
	entry_name: string;
	current_rank: number;
	current_gap: number;
	points: TrailPoint[];
}

export interface PersonalTrailResponse {
	entries: EntryTrail[];
	generated_at: string;
}

export interface DistBin {
	points_delta: number;
	count: number;
}

export interface PoolDistributionResponse {
	user_points: number;
	window_size: number;
	bins: DistBin[];
	next_rank_points_away: number | null;
	next_rank_position: number | null;
	near_count: number;
	caption: string;
	generated_at: string;
}
