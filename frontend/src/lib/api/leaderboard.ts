/**
 * Leaderboard API functions.
 *
 * Backend Task D made every breakdown / trajectory / climbers query
 * entry-keyed. URLs that took a `user_id` now take an `entry_id`.
 * `getMyRankTrajectory` still resolves to the current user, but accepts
 * an optional `entryId` query param to pick a specific entry; without
 * it the backend resolves to the user's primary eligible entry.
 */

import { api } from './client';
import type { LeaderboardResponse, PointBreakdown } from '$types';
import type {
	AllTrajectoriesResponse,
	BonusPredictionRead,
	ChampionSurvivalResponse,
	DailyMvpsResponse,
	LbResponseV4,
	MatchMarkersResponse,
	PersonalTrailResponse,
	PoolDistributionResponse,
	RaceStoriesResponse
} from '$lib/types/leaderboard';
import type { ScoringRules } from '$lib/types/results';

export type PhaseFilter = 'phase_1' | 'phase_2' | null;

export async function getLeaderboard(phase?: PhaseFilter): Promise<LeaderboardResponse> {
	const params = new URLSearchParams();
	if (phase) {
		params.set('phase', phase);
	}
	const queryString = params.toString();
	const url = queryString ? `/leaderboard/?${queryString}` : '/leaderboard/';
	return api.get<LeaderboardResponse>(url);
}

export async function getEntryBreakdown(entryId: string): Promise<PointBreakdown> {
	return api.get<PointBreakdown>(`/leaderboard/breakdown/${entryId}`);
}

// ---- V4 leaderboard (v2.164.0) ------------------------------------------

/** Same endpoint as getLeaderboard, typed for the V4 row fields (employer
 *  pool, champion/finalists alive, daily movement). The barrel's
 *  LeaderboardEntry can't be extended (user WIP lockout), so V4 callers
 *  use this wrapper. */
export async function getLeaderboardV4(): Promise<LbResponseV4> {
	return api.get<LbResponseV4>('/leaderboard/');
}

/** GET /api/leaderboard/snapshots — every eligible entry's rank path in
 *  one response. Powers the Race bump chart. */
export async function getAllTrajectories(days = 30): Promise<AllTrajectoriesResponse> {
	return api.get<AllTrajectoriesResponse>(`/leaderboard/snapshots?days=${days}`);
}

/** Bonus reads with settled hit/points/category (v2.164.0 fields). The
 *  legacy api/bonus.ts getBonusPredictions predates these fields. */
export async function getEntryBonusReads(entryId: string): Promise<BonusPredictionRead[]> {
	return api.get<BonusPredictionRead[]>(`/entries/${entryId}/predictions/bonus`);
}

// ---- Rank trajectory + climbers (replaces stubRankTrajectory / stubSteepestClimb) -----

export interface RankSnapshotPoint {
	position: number;
	total_points: number;
	captured_date: string; // ISO date YYYY-MM-DD
}

export interface RankTrajectoryResponse {
	entry_id: string;
	points: RankSnapshotPoint[];
	total_participants: number;
}

export interface SteepestClimberEntry {
	entry_id: string;
	entry_name: string;
	user_id: string;
	user_name: string;
	places: number;
	current_position: number;
	previous_position: number;
}

export interface SteepestClimbersResponse {
	days: number;
	entries: SteepestClimberEntry[];
}

export async function getMyRankTrajectory(
	days: number = 7,
	entryId?: string | null
): Promise<RankTrajectoryResponse> {
	const params = new URLSearchParams({ days: String(days) });
	if (entryId) params.set('entry_id', entryId);
	return api.get<RankTrajectoryResponse>(`/leaderboard/snapshots/me?${params.toString()}`);
}

export async function getEntryTrajectory(
	entryId: string,
	days: number = 7
): Promise<RankTrajectoryResponse> {
	return api.get<RankTrajectoryResponse>(
		`/leaderboard/snapshots/${entryId}?days=${days}`
	);
}

export async function getSteepestClimbers(
	days: number = 7,
	limit: number = 5
): Promise<SteepestClimbersResponse> {
	return api.get<SteepestClimbersResponse>(
		`/leaderboard/climbers?days=${days}&limit=${limit}`
	);
}

/** GET /api/leaderboard/scoring-rules — full scoring config including the
 *  per-stage advancement values. The V4 Results page templates every
 *  point value in user-facing copy from this (no hardcoded numbers). */
export async function getScoringRules(): Promise<ScoringRules> {
	return api.get<ScoringRules>('/leaderboard/scoring-rules');
}

// ---- Race-tab story endpoints (v4 redesign) -----------------------------

export async function getRaceStories(): Promise<RaceStoriesResponse> {
	return api.get<RaceStoriesResponse>('/leaderboard/race-stories');
}

export async function getChampionSurvival(): Promise<ChampionSurvivalResponse> {
	return api.get<ChampionSurvivalResponse>('/leaderboard/champion-survival');
}

export async function getMatchMarkers(days = 14): Promise<MatchMarkersResponse> {
	return api.get<MatchMarkersResponse>(`/leaderboard/match-markers?days=${days}`);
}

// ---- Dashboard widget endpoints -----------------------------------------

export async function getDailyMvps(): Promise<DailyMvpsResponse> {
	return api.get<DailyMvpsResponse>('/leaderboard/daily-mvps');
}

export async function getPersonalTrail(): Promise<PersonalTrailResponse> {
	return api.get<PersonalTrailResponse>('/leaderboard/personal-trail');
}

export async function getPoolDistribution(): Promise<PoolDistributionResponse> {
	return api.get<PoolDistributionResponse>('/leaderboard/pool-distribution');
}
