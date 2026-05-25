/**
 * TypeScript interfaces for the Predictor v2 frontend.
 * Mirrors backend Pydantic schemas.
 */

// Re-export entry types so consumers can `import { Entry, EntryStatus } from '$types'`
export * from './entry';

// Auth types
export interface User {
	id: string;
	email: string;
	name: string | null;
	auth_provider: 'email' | 'google';
	is_admin: boolean;
	is_active: boolean;
	competition_id: string | null;
	created_at: string;
}

export interface Token {
	access_token: string;
	token_type: string;
}

export interface MagicLinkRequest {
	email: string;
}

// Fixture types
export type MatchStatus = 'scheduled' | 'live' | 'halftime' | 'finished' | 'postponed' | 'cancelled';

export interface FixtureScore {
	home_score: number;
	away_score: number;
	home_score_et: number | null;
	away_score_et: number | null;
	home_penalties: number | null;
	away_penalties: number | null;
	outcome: string; // '1', 'X', '2'
}

export interface Fixture {
	id: string;
	home_team: string;
	away_team: string;
	kickoff: string;
	stage: string;
	group: string | null;
	match_number: number | null;
	status: MatchStatus;
	minute: number | null;
	is_locked: boolean;
	time_until_lock: number | null;
	score: FixtureScore | null;
	venue_city: string | null;
	venue_country: string | null;
	venue_country_code: string | null;
}

export interface FixturesByGroup {
	group: string;
	fixtures: Fixture[];
}

export interface LockStatus {
	fixture_id: string;
	is_locked: boolean;
	locks_at: string;
	time_remaining: number | null;
}

// Prediction types
export type PredictionPhase = 'phase_1' | 'phase_2';

export interface MatchPrediction {
	id: string;
	entry_id: string;
	fixture_id: string;
	home_score: number;
	away_score: number;
	phase: PredictionPhase;
	locked_at: string | null;
	created_at: string;
	updated_at: string;
	home_team?: string;
	away_team?: string;
	kickoff?: string;
	is_locked: boolean;
}

export interface MatchPredictionUpdate {
	home_score: number;
	away_score: number;
}

export interface MatchPredictionCreate {
	fixture_id: string;
	home_score: number;
	away_score: number;
}

export interface BracketPrediction {
	group_winners: Record<string, string[]>;
	round_of_32: string[];
	round_of_16: string[];
	quarter_finals: string[];
	semi_finals: string[];
	final: string[];
	winner: string;
}

export interface TeamAdvancementPrediction {
	team: string;
	stage: string;
	group_position: number | null;
}

// Score types
export type ScoreSource = 'api' | 'manual';

export interface Score {
	id: string;
	fixture_id: string;
	home_score: number;
	away_score: number;
	home_score_et: number | null;
	away_score_et: number | null;
	home_penalties: number | null;
	away_penalties: number | null;
	source: ScoreSource;
	verified: boolean;
	outcome: string;
}

export interface LiveMatchScore {
	fixture_id: string;
	home_team: string;
	away_team: string;
	home_score: number;
	away_score: number;
	status: string;
	minute: number | null;
	kickoff: string;
}

export interface LiveScoreResponse {
	matches: LiveMatchScore[];
	last_updated: string;
}

export interface LivePollingResponse {
	matches: LiveMatchScore[];
	leaderboard: LeaderboardEntry[];
	last_updated: string;
}

// Leaderboard types

/** Points breakdown for a single phase */
export interface PhaseBreakdown {
	// Match predictions
	match_outcome_points: number;
	exact_score_points: number;
	hybrid_bonus_points: number;

	// Bracket predictions - by stage
	group_advance_points: number;
	group_position_points: number;
	round_of_32_points: number;
	round_of_16_points: number;
	quarter_final_points: number;
	semi_final_points: number;
	final_points: number;
	winner_points: number;

	// Computed totals (from backend)
	match_total: number;
	bracket_total: number;
	total: number;
}

/** Full breakdown with phase separation */
export interface PointBreakdown {
	phase1: PhaseBreakdown;
	phase2: PhaseBreakdown;

	// Aggregate statistics
	correct_outcomes: number;
	exact_scores: number;
	total_predictions: number;

	// Bonus-question points (cross-phase — locked with Phase 1 but separate
	// from the phase breakdown). Awarded when an admin sets the matching
	// correct answer on /api/admin/bonus/answers.
	bonus_question_points: number;

	// Computed totals (from backend) - combined across phases + bonus
	match_total: number;
	bracket_total: number;
	total: number;

	// Legacy fields (combined across phases, from backend computed fields)
	match_outcome_points: number;
	exact_score_points: number;
	hybrid_bonus_points: number;
	group_advance_points: number;
	group_position_points: number;
	round_of_32_points: number;
	round_of_16_points: number;
	quarter_final_points: number;
	semi_final_points: number;
	final_points: number;
	winner_points: number;
}

// Helper functions for phase breakdowns
export function getPhaseMatchTotal(p: PhaseBreakdown): number {
	return p.match_outcome_points + p.exact_score_points + p.hybrid_bonus_points;
}

export function getPhaseBracketTotal(p: PhaseBreakdown): number {
	return (
		p.group_advance_points +
		p.group_position_points +
		p.round_of_32_points +
		p.round_of_16_points +
		p.quarter_final_points +
		p.semi_final_points +
		p.final_points +
		p.winner_points
	);
}

export function getPhaseTotal(p: PhaseBreakdown): number {
	return getPhaseMatchTotal(p) + getPhaseBracketTotal(p);
}

// Helper to calculate totals from full breakdown (legacy support)
export function getMatchTotal(b: PointBreakdown): number {
	return b.match_outcome_points + b.exact_score_points + b.hybrid_bonus_points;
}

export function getBracketTotal(b: PointBreakdown): number {
	return (
		b.group_advance_points +
		b.group_position_points +
		b.round_of_32_points +
		b.round_of_16_points +
		b.quarter_final_points +
		b.semi_final_points +
		b.final_points +
		b.winner_points
	);
}

// Helper to get knockout total (excluding groups) for a phase
export function getKnockoutTotal(p: PhaseBreakdown): number {
	return (
		p.round_of_32_points +
		p.round_of_16_points +
		p.quarter_final_points +
		p.semi_final_points +
		p.final_points +
		p.winner_points
	);
}

// Helper to get group total for a phase
export function getGroupTotal(p: PhaseBreakdown): number {
	return p.group_advance_points + p.group_position_points;
}

export interface LeaderboardEntry {
	entry_id: string;
	entry_reference: string;
	entry_name: string;
	user_id: string;
	user_name: string;
	position: number;
	total_points: number;
	breakdown: PointBreakdown;
	correct_outcomes: number;
	exact_scores: number;
	movement: number;
}

export interface LeaderboardResponse {
	entries: LeaderboardEntry[];
	last_calculated: string;
	total_participants: number;
	phase: string | null;
}

// Competition/Phase types
export interface PhaseStatus {
	current_phase: PredictionPhase;
	// Phase 1
	phase1_deadline: string | null;
	phase1_locked: boolean;
	// Phase 2
	is_phase2_active: boolean;
	phase2_bracket_deadline: string | null;
	phase2_bracket_locked: boolean;
}

// Bracket configuration types
/** Maps group winner positions (e.g., "1A") to third-place positions (e.g., "3E") */
export type ThirdPlaceMatchup = Record<string, string>;

/** Maps qualifying third-place group combinations (e.g., "EFGHIJKL") to their matchups */
export type ThirdPlaceMappingTable = Record<string, ThirdPlaceMatchup>;

// Standings types
export interface TeamStanding {
	team: string;
	group: string;
	played: number;
	won: number;
	drawn: number;
	lost: number;
	goals_for: number;
	goals_against: number;
	goal_difference: number;
	points: number;
}

export interface ActualStandingsResponse {
	standings: Record<string, TeamStanding[]>;
	qualifying_third_place: TeamStanding[];
}

// Profile types
export interface UserUpdate {
	name: string;
}

export interface UserStats {
	total_match_predictions: number;
	total_team_predictions: number;
	total_predictions: number;
	correct_outcomes: number;
	exact_scores: number;
	accuracy_pct: number;
	total_points: number;
	leaderboard_position: number | null;
	total_participants: number;
	breakdown: PointBreakdown;
}

// Community predictions (for scatter plot on results page)
export interface CommunityPrediction {
	user_name: string;
	entry_reference: string;
	entry_name: string;
	home_score: number;
	away_score: number;
}

export interface CommunityPredictionsResponse {
	fixture_id: string;
	home_team: string;
	away_team: string;
	predictions: CommunityPrediction[];
	actual: FixtureScore | null;
}

// Public user profile types
export interface PublicProfile {
	id: string;
	name: string;
	created_at: string;
	stats: UserStats;
}

export interface UserMatchPredictionView {
	fixture_id: string;
	home_team: string;
	away_team: string;
	kickoff: string;
	stage: string;
	group: string | null;
	status: MatchStatus;
	predicted_home: number;
	predicted_away: number;
	actual_home: number | null;
	actual_away: number | null;
	actual_outcome: string | null;
	is_exact: boolean;
	is_correct_outcome: boolean;
}

export interface BracketSummary {
	stages: Record<string, string[]>;
	phase1_stages: Record<string, string[]>;
	phase2_stages: Record<string, string[]>;
}

export interface UserPredictionsResponse {
	user_id: string;
	user_name: string;
	match_predictions: UserMatchPredictionView[];
	bracket_summary: BracketSummary;
}

// API Response types
export interface ApiError {
	detail: string;
}
