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

export interface OddsWeightedView {
	entries: EntryWinProbability[];
	teams: TeamStageOdds[];
}

export interface OddsCoverage {
	priced: number;
	priceable: number;
}

export interface WinProbabilityResponse {
	entries: EntryWinProbability[];
	teams: TeamStageOdds[];
	meta: WinProbabilityMeta;
	/** Null when nothing in the remaining bracket is priced yet (every
	 *  unresolved match still has at least one TBD side, or the odds API
	 *  has no line for the next real matchup). */
	odds_weighted: OddsWeightedView | null;
	odds_coverage: OddsCoverage;
}
