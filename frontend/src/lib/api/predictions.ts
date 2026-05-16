/**
 * Predictions API functions.
 *
 * All routes are entry-scoped: every call requires an `entryId` (UUID
 * string). Mirrors `backend/app/api/entry_predictions.py` (mounted at
 * `/api/entries/{entry_id}/predictions/*`).
 *
 * `getCommunityPredictions` is the one exception — it reads aggregated
 * results across all entries for a given fixture and lives under
 * `/api/predictions/...` for now.
 */

import { api } from './client';
import type {
	MatchPrediction,
	MatchPredictionCreate,
	MatchPredictionUpdate,
	BracketPrediction,
	TeamAdvancementPrediction,
	CommunityPredictionsResponse
} from '$types';

export async function getMatchPredictions(entryId: string): Promise<MatchPrediction[]> {
	return api.get<MatchPrediction[]>(`/entries/${entryId}/predictions/matches`);
}

// ---- Social signals (replaces stubSocialSignal / building block for stubHotPick) ----

export interface FixtureAgreement {
	fixture_id: string;
	agrees_exact: number;
	agrees_outcome: number;
	total: number;
}

export async function getAgreements(
	entryId: string,
	fixtureIds?: string[]
): Promise<FixtureAgreement[]> {
	const params = new URLSearchParams();
	if (fixtureIds && fixtureIds.length > 0) {
		for (const id of fixtureIds) params.append('fixture_ids', id);
	}
	const qs = params.toString();
	const base = `/entries/${entryId}/predictions/agreements`;
	const url = qs ? `${base}?${qs}` : base;
	return api.get<FixtureAgreement[]>(url);
}

// ---- Bracket exposure (replaces stubBracketExposure) ----

export interface BracketExposureResponse {
	points_available: number;
	picks_locked: number;
	picks_total: number;
	/** Team name (not code) of the user's predicted tournament winner; null if not picked yet. */
	final_winner: string | null;
	/** The other finalist; null if not predicted or only the winner is set. */
	final_opponent: string | null;
}

export async function getBracketExposure(
	entryId: string,
	phase: 'phase_1' | 'phase_2' = 'phase_1'
): Promise<BracketExposureResponse> {
	return api.get<BracketExposureResponse>(
		`/entries/${entryId}/predictions/bracket-exposure?phase=${phase}`
	);
}

export async function updateMatchPrediction(
	entryId: string,
	fixtureId: string,
	data: MatchPredictionUpdate
): Promise<MatchPrediction> {
	return api.put<MatchPrediction>(
		`/entries/${entryId}/predictions/matches/${fixtureId}`,
		data
	);
}

export async function batchUpdatePredictions(
	entryId: string,
	predictions: MatchPredictionCreate[]
): Promise<MatchPrediction[]> {
	return api.post<MatchPrediction[]>(
		`/entries/${entryId}/predictions/matches/batch`,
		predictions
	);
}

export async function getBracketPredictions(
	entryId: string,
	phase?: 'phase_1' | 'phase_2'
): Promise<BracketPrediction | null> {
	const base = `/entries/${entryId}/predictions/bracket`;
	const url = phase ? `${base}?phase=${phase}` : base;
	return api.get<BracketPrediction | null>(url);
}

export async function updateBracketPredictions(
	entryId: string,
	predictions: TeamAdvancementPrediction[]
): Promise<{ status: string }> {
	return api.put<{ status: string }>(`/entries/${entryId}/predictions/bracket`, {
		predictions
	});
}

export async function getCommunityPredictions(
	fixtureId: string
): Promise<CommunityPredictionsResponse> {
	return api.get<CommunityPredictionsResponse>(
		`/predictions/matches/${fixtureId}/community`
	);
}
