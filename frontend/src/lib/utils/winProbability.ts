import type { LbEntryV4 } from '$lib/types/leaderboard';
import type { DecisiveMatch, TitleWorld, WinProbabilityResponse } from '$lib/types/winProbability';

export interface WinProbabilityRow {
	row: LbEntryV4;
	p_win: number;
	p_top3: number;
	expected_rank: number;
	/** Expected final points under the same model as `p_win` (see
	 *  `market_based`). Read by both the Proj column and the inline card. */
	projected_points: number;
	title_worlds: TitleWorld[];
	decisive_matches: DecisiveMatch[];
	/** True when `p_win`/`projected_points`/etc. came from the odds-weighted
	 *  view (a real betting market priced the next match); false when they
	 *  fell back to the uniform coin-toss model. Every row always has a
	 *  probability either way — this just says which model produced it. */
	market_based: boolean;
}

/** Joins the win-probability API's entry_id-keyed "effective view" onto the
 *  already-loaded leaderboard rows (same data source as Standings/Race),
 *  sorted by the effective P(win) descending. A probability entry with no
 *  matching row (e.g. filtered out of the current pool view) is skipped
 *  rather than rendered as a ghost row with no identity to show.
 *
 *  The effective view is `response.odds_weighted.entries` when a live
 *  betting market has priced the next unresolved match, else
 *  `response.entries` (the uniform coin-toss run) — so Prob%, Proj, and the
 *  inline "what has to happen for you to win" card all read one consistent
 *  model instead of two half-populated ones. */
export function joinWinProbabilityRows(
	rows: LbEntryV4[],
	response: WinProbabilityResponse
): WinProbabilityRow[] {
	const marketBased = response.odds_weighted !== null;
	const effective = response.odds_weighted?.entries ?? response.entries;
	const byId = new Map(rows.map((r) => [r.entry_id, r]));
	const joined: WinProbabilityRow[] = [];
	for (const p of effective) {
		const row = byId.get(p.entry_id);
		if (!row) continue;
		joined.push({
			row,
			p_win: p.p_win,
			p_top3: p.p_top3,
			expected_rank: p.expected_rank,
			projected_points: p.projected_points ?? 0,
			title_worlds: p.title_worlds ?? [],
			decisive_matches: p.decisive_matches ?? [],
			market_based: marketBased
		});
	}
	return joined.sort((a, b) => b.p_win - a.p_win);
}
