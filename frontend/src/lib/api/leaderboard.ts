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
