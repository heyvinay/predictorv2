/**
 * Competition API functions.
 */

import { api } from './client';
import type { PhaseStatus } from '$types';

export async function getPhaseStatus(): Promise<PhaseStatus> {
	return api.get<PhaseStatus>('/competition/phase-status');
}

/** Public competition metadata. Shape mirrors the backend's CompetitionInfo
 *  schema in backend/app/api/competition.py. */
export interface CompetitionInfo {
	name: string;
	entry_fee: number;
	is_phase2_active: boolean;
	phase1_deadline: string | null;
	phase2_bracket_deadline: string | null;
	total_players: number;
	paid_players: number;
	/** Eligible-submitted entries — the scoring denominator (what rarity
	 *  divides by, what the leaderboard ranks). One user can hold up to
	 *  5 entries, so this is typically larger than total_players. */
	eligible_entries: number;
}

/** Fetch public competition metadata (no auth required) — used by the /rules
 *  page to render the entry fee, player counts, and lock dates. */
export async function getCompetitionInfo(): Promise<CompetitionInfo> {
	return api.get<CompetitionInfo>('/competition/info');
}

/** Scoring config. The Results page projects per-match rarity bonuses with
 *  the same formula the backend uses. For mode='logarithmic':
 *  R = min(rarity_cap, round(alpha * log2(1 / (2f)))) where f = agrees_outcome
 *  / total and alpha = 10/log2(15) ≈ 2.5596. Per-fixture predictor counts
 *  come from FixtureAgreement.total. Mirrors backend ScoringConfigResponse. */
export interface ScoringConfig {
	mode: 'fixed' | 'hybrid' | 'logarithmic';
	outcome_points: number;
	exact_points: number;
	rarity_cap: number;
}

export async function getScoringConfig(): Promise<ScoringConfig> {
	return api.get<ScoringConfig>('/competition/scoring-config');
}
