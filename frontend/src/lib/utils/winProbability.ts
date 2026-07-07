import type { LbEntryV4 } from '$lib/types/leaderboard';
import type { EntryWinProbability } from '$lib/types/winProbability';

export interface WinProbabilityRow {
	row: LbEntryV4;
	p_win: number;
	p_top3: number;
	expected_rank: number;
}

/** Joins the win-probability API's entry_id-keyed odds onto the
 *  already-loaded leaderboard rows (same data source as Standings/Race),
 *  sorted by P(win) descending. A probability entry with no matching row
 *  (e.g. filtered out of the current pool view) is skipped rather than
 *  rendered as a ghost row with no identity to show. */
export function joinWinProbabilityRows(
	rows: LbEntryV4[],
	probabilities: EntryWinProbability[]
): WinProbabilityRow[] {
	const byId = new Map(rows.map((r) => [r.entry_id, r]));
	const joined: WinProbabilityRow[] = [];
	for (const p of probabilities) {
		const row = byId.get(p.entry_id);
		if (!row) continue;
		joined.push({ row, p_win: p.p_win, p_top3: p.p_top3, expected_rank: p.expected_rank });
	}
	return joined.sort((a, b) => b.p_win - a.p_win);
}
