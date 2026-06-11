import { describe, expect, it } from 'vitest';

import type { Fixture, PhaseBreakdown, PointBreakdown } from '$types';
import type { BonusPredictionRead, LbEntryV4 } from '$lib/types/leaderboard';
import type { ScoringRules } from '$lib/types/results';
import {
	bestOwnSummary,
	ceilingOf,
	deriveStage,
	dnaOf,
	filterByPool,
	foldBonus,
	groupPtsOf,
	initialsOf,
	koPtsOf,
	poolCounts,
	poolOf,
	remainingMatchPoints,
	storyLine
} from './leaderboardV4';

function mkPhase(partial: Partial<PhaseBreakdown> = {}): PhaseBreakdown {
	const base: PhaseBreakdown = {
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
	const merged = { ...base, ...partial };
	merged.match_total =
		merged.match_outcome_points + merged.exact_score_points + merged.hybrid_bonus_points;
	merged.bracket_total =
		merged.group_advance_points +
		merged.group_position_points +
		merged.round_of_32_points +
		merged.round_of_16_points +
		merged.quarter_final_points +
		merged.semi_final_points +
		merged.final_points +
		merged.winner_points;
	merged.total = merged.match_total + merged.bracket_total;
	return merged;
}

function mkBreakdown(
	p1: Partial<PhaseBreakdown> = {},
	bonus = 0
): PointBreakdown {
	const phase1 = mkPhase(p1);
	const phase2 = mkPhase();
	return {
		phase1,
		phase2,
		correct_outcomes: 0,
		exact_scores: 0,
		total_predictions: 0,
		bonus_question_points: bonus,
		match_total: phase1.match_total,
		bracket_total: phase1.bracket_total,
		total: phase1.total + bonus,
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

function mkFixture(partial: Partial<Fixture> = {}): Fixture {
	return {
		id: 'f1',
		home_team: 'Brazil',
		away_team: 'Germany',
		kickoff: '2026-06-15T18:00:00Z',
		stage: 'group',
		group: 'A',
		match_number: null,
		status: 'scheduled',
		minute: null,
		is_locked: false,
		time_until_lock: null,
		score: null,
		venue_city: null,
		venue_country: null,
		venue_country_code: null,
		...partial
	};
}

const RULES: ScoringRules = {
	mode: 'logarithmic',
	match: { correct_outcome: 5, exact_score: 10, rarity_cap: 10 },
	advancement: {
		round_of_32: 20,
		round_of_16: 30,
		quarter_final: 40,
		semi_final: 50,
		final: 75,
		winner: 100
	}
};

describe('poolOf / filterByPool / poolCounts', () => {
	it('maps employers onto pools, defaulting to Guests', () => {
		expect(poolOf('atlas')).toBe('Atlas');
		expect(poolOf('jmfa')).toBe('JMFA');
		expect(poolOf('neither')).toBe('Guests');
		expect(poolOf(null)).toBe('Guests');
		expect(poolOf(undefined)).toBe('Guests');
	});

	it('filters without touching global positions', () => {
		const rows = [
			mkRow({ entry_id: 'a', position: 1, employer: 'atlas' }),
			mkRow({ entry_id: 'b', position: 2, employer: 'jmfa' }),
			mkRow({ entry_id: 'c', position: 3, employer: null })
		];
		const atlas = filterByPool(rows, 'Atlas');
		expect(atlas.map((r) => r.entry_id)).toEqual(['a']);
		expect(atlas[0].position).toBe(1);
		const guests = filterByPool(rows, 'Guests');
		expect(guests[0].position).toBe(3); // global rank retained
		expect(filterByPool(rows, 'All')).toHaveLength(3);
	});

	it('counts pools for pill badges', () => {
		const rows = [
			mkRow({ employer: 'atlas' }),
			mkRow({ employer: 'atlas' }),
			mkRow({ employer: 'neither' })
		];
		expect(poolCounts(rows)).toEqual({ All: 3, Atlas: 2, JMFA: 0, Guests: 1 });
	});
});

describe('deriveStage', () => {
	it('stays group while only group fixtures exist', () => {
		expect(deriveStage([mkFixture()])).toBe('group');
	});

	it('stays group while KO fixtures hold placeholders or empties', () => {
		const fx = [
			mkFixture({ stage: 'round_of_32', home_team: '', away_team: '' }),
			mkFixture({ stage: 'round_of_32', home_team: 'Winner of Match 12', away_team: '1A' })
		];
		expect(deriveStage(fx)).toBe('group');
	});

	it('flips to knockout once a real team is seeded', () => {
		const fx = [mkFixture({ stage: 'round_of_32', home_team: 'Brazil', away_team: '' })];
		expect(deriveStage(fx)).toBe('knockout');
	});
});

describe('dnaOf', () => {
	it('splits points by source and sums to total', () => {
		const b = mkBreakdown(
			{
				match_outcome_points: 40,
				exact_score_points: 30,
				hybrid_bonus_points: 12,
				round_of_32_points: 60
			},
			15
		);
		const dna = dnaOf(b);
		expect(dna).toEqual({ exact: 30, result: 40, rarity: 12, bracket: 60, bonus: 15 });
		expect(dna.exact + dna.result + dna.rarity + dna.bracket + dna.bonus).toBe(b.total);
	});
});

describe('foldBonus', () => {
	const reads: BonusPredictionRead[] = [
		{ question_id: 'q1', answer: 'France', category: 'group_stage', points: 15, hit: true },
		{ question_id: 'q2', answer: 'Egypt', category: 'group_stage', points: 15, hit: false },
		{ question_id: 'q3', answer: 'Morocco', category: 'top_flop', points: 20, hit: true },
		{ question_id: 'q4', answer: 'Italy', category: 'top_flop', points: 20, hit: null }
	];

	it('folds hits into group/knockout buckets', () => {
		const fold = foldBonus(reads);
		expect(fold.group).toBe(15);
		expect(fold.knockout).toBe(20);
		expect(fold.groupHits).toBe(1);
		expect(fold.knockoutHits).toBe(1);
		expect(fold.hits).toBe(2);
		expect(fold.answered).toBe(4);
	});
});

describe('groupPtsOf / koPtsOf', () => {
	it('splits column totals with bonus folded in', () => {
		const row = mkRow({
			breakdown: mkBreakdown({
				match_outcome_points: 40,
				exact_score_points: 30,
				group_advance_points: 60,
				group_position_points: 10,
				round_of_32_points: 40,
				quarter_final_points: 40
			})
		});
		expect(groupPtsOf(row, 15)).toBe(40 + 30 + 60 + 10 + 15);
		expect(koPtsOf(row, 20)).toBe(40 + 40 + 20);
	});
});

describe('ceilingOf / remainingMatchPoints', () => {
	it('adds champion + uncredited finalists + shared remainder', () => {
		const row = mkRow({
			total_points: 100,
			champion_alive: true,
			finalists_alive: 2,
			breakdown: mkBreakdown() // nothing banked from final/winner yet
		});
		expect(ceilingOf(row, RULES, 50)).toBe(100 + 100 + 2 * 75 + 50);
	});

	it('does not re-add credited finalists or a paid champion', () => {
		const row = mkRow({
			total_points: 300,
			champion_alive: true,
			finalists_alive: 2,
			breakdown: mkBreakdown({ final_points: 150, winner_points: 100 })
		});
		// Both finalists credited (150/75=2), winner already paid.
		expect(ceilingOf(row, RULES, 0)).toBe(300);
	});

	it('dead champion adds nothing', () => {
		const row = mkRow({
			total_points: 80,
			champion_alive: false,
			finalists_alive: 0
		});
		expect(ceilingOf(row, RULES, 25)).toBe(105);
	});

	it('counts only unfinished group fixtures for the shared remainder', () => {
		const fx = [
			mkFixture({ status: 'finished' }),
			mkFixture({ status: 'scheduled' }),
			mkFixture({ status: 'live' }),
			mkFixture({ stage: 'round_of_32', status: 'scheduled' })
		];
		// 2 unfinished group fixtures × (5+10+10)
		expect(remainingMatchPoints(fx, RULES)).toBe(50);
	});
});

describe('initialsOf', () => {
	it('builds 2-char initials', () => {
		expect(initialsOf('Samba Kings')).toBe('SK');
		expect(initialsOf('Tinfoil')).toBe('TI');
		expect(initialsOf('  ')).toBe('??');
	});
});

describe('storyLine', () => {
	it('joins movement, champion, and finalist clauses', () => {
		const row = mkRow({
			daily_movement: 2,
			champion_pick: 'Brazil',
			champion_alive: true,
			finalist_picks: ['Brazil', 'France'],
			finalists_alive: 2
		});
		expect(storyLine(row)).toBe(
			'Climbed 2 since yesterday · Brazil title pick alive · 2 of 2 finalists standing'
		);
	});

	it('handles slips and dead picks', () => {
		const row = mkRow({
			daily_movement: -3,
			champion_pick: 'Germany',
			champion_alive: false,
			finalist_picks: ['Germany', 'Spain'],
			finalists_alive: 1
		});
		expect(storyLine(row)).toBe(
			'Slipped 3 since yesterday · Germany title pick out · 1 of 2 finalists standing'
		);
	});
});

describe('bestOwnSummary', () => {
	it('finds the best own entry and gap to the lead', () => {
		const rows = [
			mkRow({ entry_id: 'a', user_id: 'other', position: 1, total_points: 150 }),
			mkRow({ entry_id: 'b', user_id: 'me', position: 3, total_points: 124 }),
			mkRow({ entry_id: 'c', user_id: 'me', position: 9, total_points: 101 })
		];
		expect(bestOwnSummary(rows, 'me')).toEqual({ bestRank: 3, ptsOffLead: 26 });
		expect(bestOwnSummary(rows, 'nobody')).toBeNull();
		expect(bestOwnSummary(rows, null)).toBeNull();
	});
});
