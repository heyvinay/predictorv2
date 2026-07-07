/**
 * Win-probability simulator types.
 *
 * Lives outside the `$lib/types` barrel deliberately — the barrel
 * (types/index.ts) carries uncommitted user WIP and must not be touched.
 * Import directly: `from '$lib/types/winProbability'`.
 */

export interface EntryWinProbability {
	entry_id: string;
	p_win: number;
	p_top3: number;
	expected_rank: number;
}

/** stage_odds keys are singular KO stage names ('round_of_32' .. 'winner'),
 *  each the cumulative P(team reaches AT LEAST that stage). Trophy odds
 *  are stage_odds['winner']. */
export interface TeamStageOdds {
	team: string;
	stage_odds: Record<string, number>;
}

export interface WinProbabilityMeta {
	mode: 'exact' | 'monte_carlo' | 'unavailable';
	unresolved_matches: number;
	scenario_count: number;
	computed_at: string;
}

export interface WinProbabilityResponse {
	entries: EntryWinProbability[];
	teams: TeamStageOdds[];
	meta: WinProbabilityMeta;
}
