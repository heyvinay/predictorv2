/**
 * Scores API functions.
 */

import { api } from './client';
import type { LiveScoreResponse, LivePollingResponse } from '$types';

export async function getLiveScores(): Promise<LiveScoreResponse> {
	return api.get<LiveScoreResponse>('/scores/live');
}

export async function pollLiveData(): Promise<LivePollingResponse> {
	return api.get<LivePollingResponse>('/scores/poll');
}

/** Payload for the admin manual score editor (/admin/sync). Mirrors the
 *  backend ScoreUpdate schema. `verified: true` locks the score against
 *  the API sync so a manual correction survives the scheduler. */
export interface ScoreUpdatePayload {
	home_score: number;
	away_score: number;
	home_score_et?: number | null;
	away_score_et?: number | null;
	home_penalties?: number | null;
	away_penalties?: number | null;
	verified: boolean;
}

export interface ScoreReadResponse {
	id: string;
	fixture_id: string;
	home_score: number;
	away_score: number;
	home_score_et: number | null;
	away_score_et: number | null;
	home_penalties: number | null;
	away_penalties: number | null;
	source: string;
	verified: boolean;
	outcome: string;
}

/** Admin only — upserts the score, marks the fixture FINISHED, and
 *  invalidates the leaderboard cache (backend behavior). */
export async function updateScore(
	fixtureId: string,
	payload: ScoreUpdatePayload
): Promise<ScoreReadResponse> {
	return api.put<ScoreReadResponse>(`/scores/${fixtureId}`, payload);
}
