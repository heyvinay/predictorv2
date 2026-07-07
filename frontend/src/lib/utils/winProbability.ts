import type { LbEntryV4 } from '$lib/types/leaderboard';
import type { EntryWinProbability } from '$lib/types/winProbability';

export interface WinProbabilityRow {
	row: LbEntryV4;
	p_win: number;
	p_top3: number;
	expected_rank: number;
	/** Odds-weighted P(win) for the same entry, when a second view was
	 *  supplied — undefined (not 0) when there's nothing to compare, so
	 *  the UI can distinguish "no odds column" from "0% under odds". */
	odds_p_win?: number;
}

/** Joins the win-probability API's entry_id-keyed odds onto the
 *  already-loaded leaderboard rows (same data source as Standings/Race),
 *  sorted by P(win) descending. A probability entry with no matching row
 *  (e.g. filtered out of the current pool view) is skipped rather than
 *  rendered as a ghost row with no identity to show.
 *
 *  `oddsWeighted` is optional — passing it merges each entry's
 *  odds-weighted P(win) alongside the uniform one for a side-by-side
 *  comparison; omitting it (or passing undefined) leaves `odds_p_win`
 *  unset on every row. Sort order is always driven by the uniform
 *  P(win) — the odds column is a comparison, not a re-ranking. */
export function joinWinProbabilityRows(
	rows: LbEntryV4[],
	probabilities: EntryWinProbability[],
	oddsWeighted?: EntryWinProbability[]
): WinProbabilityRow[] {
	const byId = new Map(rows.map((r) => [r.entry_id, r]));
	const oddsById = new Map((oddsWeighted ?? []).map((p) => [p.entry_id, p.p_win]));
	const joined: WinProbabilityRow[] = [];
	for (const p of probabilities) {
		const row = byId.get(p.entry_id);
		if (!row) continue;
		joined.push({
			row,
			p_win: p.p_win,
			p_top3: p.p_top3,
			expected_rank: p.expected_rank,
			odds_p_win: oddsById.get(p.entry_id)
		});
	}
	return joined.sort((a, b) => b.p_win - a.p_win);
}
