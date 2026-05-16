/**
 * Leaderboard store for standings and points.
 * Supports filtering by phase (overall, phase_1, phase_2).
 */

import { writable, derived } from 'svelte/store';
import * as leaderboardApi from '$api/leaderboard';
import type { PhaseFilter } from '$api/leaderboard';
import * as scoresApi from '$api/scores';
import { user } from './auth';
import { activeEntryId } from './entries';
import type { LeaderboardEntry, LeaderboardResponse, PointBreakdown, LiveMatchScore } from '$types';

// Phase filter type
export type LeaderboardPhase = 'overall' | 'phase_1' | 'phase_2';

// Stores
export const leaderboard = writable<LeaderboardEntry[]>([]);
export const lastCalculated = writable<string | null>(null);
export const totalParticipants = writable<number>(0);
export const leaderboardLoading = writable<boolean>(false);
export const leaderboardError = writable<string | null>(null);
export const leaderboardPhase = writable<LeaderboardPhase>('overall');

// Live scores store
export const liveMatches = writable<LiveMatchScore[]>([]);

// Polling state
let pollInterval: ReturnType<typeof setInterval> | null = null;

// Derived stores

/**
 * Every leaderboard row this user owns. A user can hold multiple
 * entries, so this is plural — never collapse to "one row per user".
 */
export const myLeaderboardRows = derived([leaderboard, user], ([$leaderboard, $user]) => {
	if (!$user) return [] as LeaderboardEntry[];
	return $leaderboard.filter((row) => row.user_id === $user.id);
});

/**
 * The single leaderboard row matching the active entry, or null if
 * the active entry isn't on the board yet (e.g. still draft / ready).
 * Drives the dashboard "my points / my rank" KPI.
 */
export const activeEntryPosition = derived(
	[leaderboard, activeEntryId],
	([$leaderboard, $entryId]) => {
		if (!$entryId) return null;
		return $leaderboard.find((row) => row.entry_id === $entryId) ?? null;
	}
);

export const topThree = derived(leaderboard, ($leaderboard) => $leaderboard.slice(0, 3));

// Convert LeaderboardPhase to API PhaseFilter
function toApiPhase(phase: LeaderboardPhase): PhaseFilter {
	if (phase === 'overall') return null;
	return phase;
}

// Actions
export async function fetchLeaderboard(phase?: LeaderboardPhase): Promise<void> {
	leaderboardLoading.set(true);
	leaderboardError.set(null);

	// Use provided phase or current phase from store
	const effectivePhase = phase ?? 'overall';
	leaderboardPhase.set(effectivePhase);

	try {
		const data: LeaderboardResponse = await leaderboardApi.getLeaderboard(
			toApiPhase(effectivePhase)
		);
		leaderboard.set(data.entries);
		lastCalculated.set(data.last_calculated);
		totalParticipants.set(data.total_participants);
	} catch (e) {
		leaderboardError.set(e instanceof Error ? e.message : 'Failed to load leaderboard');
	} finally {
		leaderboardLoading.set(false);
	}
}

export async function fetchEntryBreakdown(entryId: string): Promise<PointBreakdown | null> {
	try {
		return await leaderboardApi.getEntryBreakdown(entryId);
	} catch (e) {
		return null;
	}
}

// Switch phase and refetch
export async function setPhase(phase: LeaderboardPhase): Promise<void> {
	await fetchLeaderboard(phase);
}

// Polling for live updates (always fetches overall for live data)
export function startPolling(intervalMs: number = 60000): void {
	if (pollInterval) return;

	pollLiveData();
	pollInterval = setInterval(pollLiveData, intervalMs);
}

export function stopPolling(): void {
	if (pollInterval) {
		clearInterval(pollInterval);
		pollInterval = null;
	}
}

// Combined polling function (scores + leaderboard in one request)
// Note: Polling always returns overall leaderboard for live updates
export async function pollLiveData(): Promise<void> {
	leaderboardLoading.set(true);
	leaderboardError.set(null);

	try {
		const data = await scoresApi.pollLiveData();
		leaderboard.set(data.leaderboard);
		liveMatches.set(data.matches);
		lastCalculated.set(data.last_updated);
		totalParticipants.set(data.leaderboard.length);
		// Reset to overall since polling returns overall data
		leaderboardPhase.set('overall');
	} catch (e) {
		leaderboardError.set(e instanceof Error ? e.message : 'Failed to load live data');
	} finally {
		leaderboardLoading.set(false);
	}
}

// Utility functions
export function getMovementIndicator(movement: number): { icon: string; class: string } {
	if (movement > 0) {
		return { icon: '▲', class: 'text-success' };
	} else if (movement < 0) {
		return { icon: '▼', class: 'text-error' };
	}
	return { icon: '–', class: 'text-base-content/50' };
}

export function formatPoints(points: number): string {
	return points.toLocaleString();
}
