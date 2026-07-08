import { describe, expect, it } from 'vitest';

import type { PhaseBreakdown, PointBreakdown } from '$types';
import type { LbEntryV4 } from '$lib/types/leaderboard';
import type { EntryWinProbability, WinProbabilityResponse } from '$lib/types/winProbability';
import { joinWinProbabilityRows } from './winProbability';

function mkPhase(): PhaseBreakdown {
	return {
		match_outcome_points: 0,
		exact_score_points: 0,
		hybrid_bonus_points: 0,
		group_advance_points: 0,
		group_position_points: 0,
		round_of_32_points: 0,
		round_of_16_points: 0,
		quarter_final_points: 0,
		semi_final_points: 0,
		final_points: 0,
		winner_points: 0,
		match_total: 0,
		bracket_total: 0,
		total: 0
	};
}

function mkBreakdown(): PointBreakdown {
	const phase1 = mkPhase();
	return {
		phase1,
		phase2: mkPhase(),
		correct_outcomes: 0,
		exact_scores: 0,
		total_predictions: 0,
		bonus_question_points: 0,
		match_total: phase1.match_total,
		bracket_total: phase1.bracket_total,
		total: phase1.total,
		match_outcome_points: phase1.match_outcome_points,
		exact_score_points: phase1.exact_score_points,
		hybrid_bonus_points: phase1.hybrid_bonus_points,
		group_advance_points: phase1.group_advance_points,
		group_position_points: phase1.group_position_points,
		round_of_32_points: phase1.round_of_32_points,
		round_of_16_points: phase1.round_of_16_points,
		quarter_final_points: phase1.quarter_final_points,
		semi_final_points: phase1.semi_final_points,
		final_points: phase1.final_points,
		winner_points: phase1.winner_points
	};
}

function mkRow(partial: Partial<LbEntryV4> = {}): LbEntryV4 {
	return {
		entry_id: 'e1',
		entry_reference: 'WC26-000001',
		entry_name: 'Samba Kings',
		user_id: 'u1',
		user_name: 'Alice',
		position: 1,
		total_points: 0,
		breakdown: mkBreakdown(),
		correct_outcomes: 0,
		exact_scores: 0,
		movement: 0,
		...partial
	};
}

/** Builds a minimal WinProbabilityResponse. `oddsEntries` omitted (or
 *  undefined) reproduces the "nothing priced yet" API contract —
 *  `odds_weighted: null` — so callers can exercise the coin-toss
 *  fallback without hand-rolling the whole envelope each time. */
function mkResponse(
	entries: EntryWinProbability[],
	oddsEntries?: EntryWinProbability[]
): WinProbabilityResponse {
	return {
		entries,
		teams: [],
		meta: {
			mode: 'exact',
			unresolved_matches: 1,
			scenario_count: 2,
			computed_at: '2026-07-08T00:00:00Z'
		},
		odds_weighted: oddsEntries ? { entries: oddsEntries, teams: [] } : null,
		odds_coverage: { priced: oddsEntries ? 1 : 0, priceable: 1 }
	};
}

describe('joinWinProbabilityRows', () => {
	it('joins the uniform (coin-toss) entries onto rows when no market is priced, sorted by p_win desc', () => {
		const rows = [
			mkRow({ entry_id: 'e1', user_name: 'Alice' }),
			mkRow({ entry_id: 'e2', user_name: 'Bob' })
		];
		const response = mkResponse([
			{ entry_id: 'e1', p_win: 0.2, p_top3: 0.5, expected_rank: 3 },
			{ entry_id: 'e2', p_win: 0.6, p_top3: 0.9, expected_rank: 1 }
		]);

		const joined = joinWinProbabilityRows(rows, response);

		expect(joined.map((j) => j.row.user_name)).toEqual(['Bob', 'Alice']);
		expect(joined[0].p_win).toBe(0.6);
		expect(joined.every((j) => j.market_based)).toBe(false);
	});

	it('prefers the odds-weighted entries as the "effective" view when a market is priced', () => {
		const rows = [mkRow({ entry_id: 'e1' }), mkRow({ entry_id: 'e2' })];
		const response = mkResponse(
			[
				{ entry_id: 'e1', p_win: 0.5, p_top3: 0.5, expected_rank: 1, projected_points: 200 },
				{ entry_id: 'e2', p_win: 0.5, p_top3: 0.5, expected_rank: 1, projected_points: 190 }
			],
			[
				{ entry_id: 'e1', p_win: 0.9, p_top3: 0.9, expected_rank: 1, projected_points: 231.5 },
				{ entry_id: 'e2', p_win: 0.1, p_top3: 0.1, expected_rank: 2, projected_points: 205.9 }
			]
		);

		const joined = joinWinProbabilityRows(rows, response);
		const byId = new Map(joined.map((j) => [j.row.entry_id, j]));

		expect(byId.get('e1')?.p_win).toBe(0.9);
		expect(byId.get('e1')?.projected_points).toBe(231.5);
		expect(byId.get('e2')?.p_win).toBe(0.1);
		expect(joined.every((j) => j.market_based)).toBe(true);
		// Sort order follows the effective (odds-weighted) p_win, not the uniform one.
		expect(joined.map((j) => j.row.entry_id)).toEqual(['e1', 'e2']);
	});

	it('falls back to the uniform projected_points when no market is priced — never blank', () => {
		const rows = [mkRow({ entry_id: 'e1' })];
		const response = mkResponse([
			{ entry_id: 'e1', p_win: 0.5, p_top3: 0.5, expected_rank: 1, projected_points: 224.8 }
		]);

		const joined = joinWinProbabilityRows(rows, response);

		expect(joined[0].projected_points).toBe(224.8);
		expect(joined[0].market_based).toBe(false);
	});

	it('skips an effective-view entry whose entry_id has no matching row (e.g. pool-filtered out)', () => {
		const rows = [mkRow({ entry_id: 'e1' })];
		const response = mkResponse([
			{ entry_id: 'e1', p_win: 0.3, p_top3: 0.5, expected_rank: 2 },
			{ entry_id: 'ghost', p_win: 0.7, p_top3: 0.9, expected_rank: 1 }
		]);

		const joined = joinWinProbabilityRows(rows, response);

		expect(joined).toHaveLength(1);
		expect(joined[0].row.entry_id).toBe('e1');
	});

	it('returns an empty array when there are no entries in the effective view', () => {
		const rows = [mkRow({ entry_id: 'e1' })];
		expect(joinWinProbabilityRows(rows, mkResponse([]))).toEqual([]);
	});

	it('carries title_worlds and decisive_matches from the effective view for the inline card', () => {
		const rows = [mkRow({ entry_id: 'e1' })];
		const response = mkResponse(
			[{ entry_id: 'e1', p_win: 0.5, p_top3: 0.5, expected_rank: 1 }],
			[
				{
					entry_id: 'e1',
					p_win: 0.9,
					p_top3: 0.9,
					expected_rank: 1,
					title_worlds: [{ team: 'Brazil', trophy_odds: 0.3, p_win_given_champion: 0.4 }],
					decisive_matches: [
						{
							match_number: 90,
							stage: 'semi_final',
							home_team: 'Brazil',
							away_team: 'France',
							p_win_if_home: 0.9,
							p_win_if_away: 0.1
						}
					]
				}
			]
		);

		const joined = joinWinProbabilityRows(rows, response);

		expect(joined[0].title_worlds).toHaveLength(1);
		expect(joined[0].title_worlds[0].team).toBe('Brazil');
		expect(joined[0].decisive_matches).toHaveLength(1);
		expect(joined[0].decisive_matches[0].match_number).toBe(90);
	});
});
