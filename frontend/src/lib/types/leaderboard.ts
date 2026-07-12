/**
 * V4 Leaderboard types (v2.164.0).
 *
 * Lives outside the `$lib/types` barrel deliberately — the barrel
 * (types/index.ts) carries uncommitted user WIP and must not be touched.
 * Import directly: `from '$lib/types/leaderboard'`.
 */

import type { LeaderboardEntry } from '$types';

/** Page view switcher state, persisted to localStorage['predictor:lb:view'].
 *  'win_probability' is admin-gated (see +page.svelte's VIEWS builder) —
 *  never persisted-and-restored for a non-admin session. */
export type LbView = 'table' | 'race' | 'insights' | 'win_probability';

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
	/** Live projection (v2.198.0) — present only when the response's
	 *  live_projection_active is true. Banked position/total_points on the
	 *  base type stay banked; these carry the provisional KO projection. */
	projected_position?: number | null;
	projected_total?: number | null;
	live_delta?: number | null;
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
	/** True when entries carry a live KO projection (gates armed + a
	 *  knockout match is live). Surfaces key their LIVE chrome off this. */
	live_projection_active?: boolean;
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
	| 'hottest_streak'
	| 'phoenix'
	| 'slow_burn'
	| 'steady_hand';

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

export interface BonusHitRate {
	question_id: string;
	correct_answers: string[];
	hit_count: number;
	eligible_count: number;
	hit_rate: number; // 0-1
}

export interface BonusHitRatesResponse {
	questions: BonusHitRate[];
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
	bucket_start: number;
	bucket_end: number;
	count: number;
}

export interface YourEntryMarker {
	entry_id: string;
	entry_name: string;
	points: number;
	position: number;
}

export interface PoolDistributionResponse {
	bins: DistBin[];
	bucket_width: number;
	min_points: number;
	max_points: number;
	total_entries: number;
	your_entries: YourEntryMarker[];
	caption: string;
	generated_at: string;
}

// ---------------------------------------------------------------------------
// Group Stage Podium (v2.183.x — upgrade from single-winner GroupStageWinner)
// ---------------------------------------------------------------------------
// Card-and-email payload returned by GET /api/leaderboard/group-stage-winner.
// URL preserved from v2.181.0 to avoid breaking external consumers; payload
// upgraded in v2.183.x to surface the runners-up alongside the champion.
// Null = release flag not flipped yet (admin hasn't pressed the button on
// /admin) → card stays hidden. Frontend NEVER renders a partial card.

export interface GroupStageEntry {
	entry_id: string;
	user_name: string;
	entry_name: string;
	// "Person" when the owner has one entry, "Person — Entry name" when
	// multiple — with the owner-name prefix stripped from entry_name to
	// avoid "James Vella — James Vella 3rd Entry" duplication. Card
	// renders this verbatim, no client-side rowDisplayName needed.
	display_name: string;
	final_rank: number;
	total_points: number;

	// 4-part breakdown — sums to total_points.
	outcome_points: number;
	exact_score_extra: number;
	rarity_extra: number;
	bonus_question_points: number;
}

export interface GroupStagePodium {
	// Top 3 in rank order. entries[0] is the winner. May be shorter than
	// 3 in degenerate cases (pool with <3 eligible entries).
	entries: GroupStageEntry[];

	// Story stats — context the narrative draws on. Available as
	// supporting numbers if the card wants to display them.
	champion_pick: string | null;
	champion_alive: boolean;
	finalist_picks: string[];
	finalists_alive: number;
	days_at_top: number;
	total_days: number;
	runner_up_gap: number | null;

	// Pre-composed narrative — card renders this verbatim. To edit
	// wording, change `_compose_story_line` in the backend service.
	// Refers to runner-up by name, so it lives at podium level.
	story_line: string;

	// Audit verification claim — drives the "Verified ✓" pill.
	audit_verified: boolean;

	generated_at: string;
}

// Re-export under the legacy name for any straggling consumers. New
// code should import GroupStagePodium directly.
/** @deprecated use GroupStagePodium */
export type GroupStageWinner = GroupStagePodium;
