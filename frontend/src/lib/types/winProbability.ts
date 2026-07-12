/**
 * Win-probability simulator types.
 *
 * Lives outside the `$lib/types` barrel deliberately — the barrel
 * (types/index.ts) carries uncommitted user WIP and must not be touched.
 * Import directly: `from '$lib/types/winProbability'`.
 */

/** One "if this team lifts the cup" world for a single entry. */
export interface TitleWorld {
	team: string;
	/** P(team is champion) — the marginal shown in parentheses. */
	trophy_odds: number;
	/** P(this entry wins the pool | team champion) — the "wins X%" figure. */
	p_win_given_champion: number;
}

/** One upcoming real-vs-real match and how its result swings the entry's odds. */
export interface DecisiveMatch {
	match_number: number;
	stage: string;
	home_team: string;
	away_team: string;
	p_win_if_home: number;
	p_win_if_away: number;
}

export interface EntryWinProbability {
	entry_id: string;
	p_win: number;
	p_top3: number;
	expected_rank: number;
	/** Per-entry conditional breakdown — populated on BOTH views (uniform
	 *  and odds-weighted), so whichever one the frontend treats as the
	 *  "effective" view carries a consistent Prob%/Proj/card. Optional so
	 *  consumers fall back to defaults; `joinWinProbabilityRows` coerces
	 *  to 0 / []. Powers the inline expanded card in the Win Probability
	 *  tab. */
	projected_points?: number;
	title_worlds?: TitleWorld[];
	decisive_matches?: DecisiveMatch[];
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

/** One completion of the remaining bracket and who wins the pool under it.
 *  `outcomes` maps match_number (stringified in JSON) → winning team, for
 *  the matches that were unresolved. */
export interface ScenarioOutcome {
	outcomes: Record<string, string>;
	weight: number;
	champion_entry_ids: string[];
	champion_points: number;
}

export interface MatchMetaEntry {
	match_number: number;
	home_team: string;
	away_team: string;
	stage: string;
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
	/** Every remaining bracket completion + its pool champion (Path to the
	 *  Trophy). Empty when too many to enumerate, or on the fail path. */
	scenarios: ScenarioOutcome[];
	/** The next real-vs-real matches, for labelling scenarios. */
	match_meta: MatchMetaEntry[];
}

/** Live Polymarket "to win the tournament" odds for one team. `team` is
 *  the internal team name (joined server-side), so it matches plain team
 *  names elsewhere in the app without client canonicalisation. */
export interface ChampionMarketOdds {
	team: string;
	market_odds: number; // 0-1
}

export interface ChampionMarketOddsResponse {
	odds: ChampionMarketOdds[];
	computed_at: string;
}
