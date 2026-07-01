/**
 * Championship (tournament-winner) odds API — GET /api/odds/outrights.
 *
 * Separate from the Smart Fill h2h odds cache (`/odds` SvelteKit proxy +
 * `frontend/src/lib/utils/oddsCache.ts`): this hits the FastAPI cache
 * directly like every other v4 endpoint (`$api/leaderboard` etc.), no
 * SvelteKit proxy hop needed.
 */

import { api } from './client';

export interface ChampionshipOddsTeam {
	team: string;
	probability: number; // 0..1, de-vigged + averaged across bookmakers
}

export interface ChampionshipOddsResponse {
	fetchedAt?: string;
	teams: ChampionshipOddsTeam[];
	error?: 'not_configured' | 'fetch_failed';
}

export async function getChampionshipOdds(): Promise<ChampionshipOddsResponse> {
	return api.get<ChampionshipOddsResponse>('/odds/outrights');
}
