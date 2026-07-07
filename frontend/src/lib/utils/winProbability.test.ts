import { describe, expect, it } from 'vitest';

import type { PhaseBreakdown, PointBreakdown } from '$types';
import type { LbEntryV4 } from '$lib/types/leaderboard';
import type { EntryWinProbability } from '$lib/types/winProbability';
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

describe('joinWinProbabilityRows', () => {
	it('joins probability entries onto their matching leaderboard row, sorted by p_win desc', () => {
		const rows = [
			mkRow({ entry_id: 'e1', user_name: 'Alice' }),
			mkRow({ entry_id: 'e2', user_name: 'Bob' })
		];
		const probabilities: EntryWinProbability[] = [
			{ entry_id: 'e1', p_win: 0.2, p_top3: 0.5, expected_rank: 3 },
			{ entry_id: 'e2', p_win: 0.6, p_top3: 0.9, expected_rank: 1 }
		];

		const joined = joinWinProbabilityRows(rows, probabilities);

		expect(joined.map((j) => j.row.user_name)).toEqual(['Bob', 'Alice']);
		expect(joined[0].p_win).toBe(0.6);
	});

	it('skips a probability entry whose entry_id has no matching row (e.g. pool-filtered out)', () => {
		const rows = [mkRow({ entry_id: 'e1' })];
		const probabilities: EntryWinProbability[] = [
			{ entry_id: 'e1', p_win: 0.3, p_top3: 0.5, expected_rank: 2 },
			{ entry_id: 'ghost', p_win: 0.7, p_top3: 0.9, expected_rank: 1 }
		];

		const joined = joinWinProbabilityRows(rows, probabilities);

		expect(joined).toHaveLength(1);
		expect(joined[0].row.entry_id).toBe('e1');
	});

	it('returns an empty array when there are no probability entries', () => {
		const rows = [mkRow({ entry_id: 'e1' })];
		expect(joinWinProbabilityRows(rows, [])).toEqual([]);
	});
});
