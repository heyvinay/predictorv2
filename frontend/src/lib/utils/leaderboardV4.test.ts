import { describe, expect, it } from 'vitest';

import type { Fixture, PhaseBreakdown, PointBreakdown } from '$types';
import type { BonusPredictionRead, LbEntryV4 } from '$lib/types/leaderboard';
import type { ScoringRules } from '$lib/types/results';
import {
	bestOwnSummary,
	ceilingOf,
	chipState,
	composeRankDelta,
	deriveStage,
	dnaOf,
	eliminatedTeams,
	filterByPool,
	firstTwoPlusExpand,
	foldBonus,
	groupPtsOf,
	initialsOf,
	koPtsOf,
	multiEntryUserIds,
	poolCounts,
	poolOf,
	remainingMatchPoints,
	rowDisplayName,
	searchRows,
	seededByStage,
	sortRows,
	DEFAULT_LB_SORT,
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

	it('treats slot:-format ingest placeholders as not-real (prod format)', () => {
		// The production DB stores "slot:round_of_32:537430:home" until
		// Football-Data seeds real teams — regression: these read as real
		// teams and flipped the stage to knockout before kickoff.
		const fx = [
			mkFixture({
				stage: 'round_of_32',
				home_team: 'slot:round_of_32:537430:home',
				away_team: 'slot:round_of_32:537430:away'
			})
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

describe('eliminatedTeams / seededByStage / chipState', () => {
	const score = (outcome: string) => ({
		home_score: 1,
		away_score: 0,
		home_score_et: null,
		away_score_et: null,
		home_penalties: null,
		away_penalties: null,
		outcome
	});

	it('marks KO losers eliminated', () => {
		const fx = [
			mkFixture({
				stage: 'quarter_final',
				home_team: 'Brazil',
				away_team: 'Germany',
				status: 'finished',
				score: score('1')
			})
		];
		expect(eliminatedTeams(fx)).toEqual(new Set(['Germany']));
	});

	it('eliminates group non-qualifiers only once R32 is fully real', () => {
		const groupDone = [
			mkFixture({ home_team: 'Brazil', away_team: 'Egypt', status: 'finished' }),
			mkFixture({ home_team: 'France', away_team: 'Italy', status: 'finished' })
		];
		const partial = [
			...groupDone,
			mkFixture({ stage: 'round_of_32', home_team: 'Brazil', away_team: 'Winner of Match 4' })
		];
		expect(eliminatedTeams(partial)).toEqual(new Set());

		const seededFull = [
			...groupDone,
			mkFixture({ stage: 'round_of_32', home_team: 'Brazil', away_team: 'France' })
		];
		expect(eliminatedTeams(seededFull)).toEqual(new Set(['Egypt', 'Italy']));
	});

	it('credits a finished KO match winner with the NEXT stage before lineups update', () => {
		// Backend pays "reached R16" the moment the R32 match finishes —
		// the drawer chips must agree even if no R16 fixture is seeded yet.
		const fx = [
			mkFixture({
				stage: 'round_of_32',
				home_team: 'Brazil',
				away_team: 'Germany',
				status: 'finished',
				score: score('1')
			})
		];
		const seeded = seededByStage(fx);
		expect(seeded.get('round_of_16')).toEqual(new Set(['Brazil']));
	});

	it('seeds stages from lineups and crowns the final winner', () => {
		const fx = [
			mkFixture({ stage: 'semi_final', home_team: 'Brazil', away_team: 'France' }),
			mkFixture({
				stage: 'final',
				home_team: 'Brazil',
				away_team: 'Spain',
				status: 'finished',
				score: score('2')
			})
		];
		const seeded = seededByStage(fx);
		expect(seeded.get('semi_final')).toEqual(new Set(['Brazil', 'France']));
		expect(seeded.get('final')).toEqual(new Set(['Brazil', 'Spain']));
		expect(seeded.get('winner')).toEqual(new Set(['Spain']));
	});

	it('derives chip states', () => {
		const seeded = new Map([['semi_final', new Set(['Brazil'])]]);
		const out = new Set(['Germany']);
		expect(chipState('Brazil', 'semi_final', seeded, out)).toBe('hit');
		expect(chipState('Germany', 'semi_final', seeded, out)).toBe('out');
		expect(chipState('France', 'semi_final', seeded, out)).toBe('pend');
	});
});

describe('searchRows', () => {
	const rows = [
		mkRow({ entry_id: 'a', user_name: 'Karl Schembri', entry_name: 'Route One FC', position: 4 }),
		mkRow({ entry_id: 'b', user_name: 'Elena Galea', entry_name: 'Tiki-Taka', position: 7 }),
		mkRow({ entry_id: 'c', user_name: 'José Müller', entry_name: 'Samba Kings', position: 9 })
	];

	it('matches person or entry name, case-insensitively', () => {
		expect(searchRows(rows, 'karl').map((r) => r.entry_id)).toEqual(['a']);
		expect(searchRows(rows, 'TIKI').map((r) => r.entry_id)).toEqual(['b']);
	});

	it('is accent-insensitive and keeps global positions', () => {
		const hit = searchRows(rows, 'jose muller');
		expect(hit.map((r) => r.entry_id)).toEqual(['c']);
		expect(hit[0].position).toBe(9);
	});

	it('empty or blank query returns everything', () => {
		expect(searchRows(rows, '')).toHaveLength(3);
		expect(searchRows(rows, '   ')).toHaveLength(3);
	});
});

describe('multiEntryUserIds / rowDisplayName', () => {
	it('appends the entry name only for multi-entry owners', () => {
		const rows = [
			mkRow({ entry_id: 'a', user_id: 'u1', user_name: 'Vinay', entry_name: 'Entry 7' }),
			mkRow({ entry_id: 'b', user_id: 'u1', user_name: 'Vinay', entry_name: 'Bold' }),
			mkRow({ entry_id: 'c', user_id: 'u2', user_name: 'Maya', entry_name: 'Solo XI' })
		];
		const multi = multiEntryUserIds(rows);
		expect(rowDisplayName(rows[0], multi)).toBe('Vinay — Entry 7');
		expect(rowDisplayName(rows[1], multi)).toBe('Vinay — Bold');
		expect(rowDisplayName(rows[2], multi)).toBe('Maya');
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

describe('sortRows (v2.168.0)', () => {
	const none = new Set<string>();
	const rows = [
		mkRow({
			entry_id: 'a',
			user_id: 'ua',
			user_name: 'Zara',
			total_points: 50,
			breakdown: mkBreakdown({ match_outcome_points: 30, quarter_final_points: 20 })
		}),
		mkRow({
			entry_id: 'b',
			user_id: 'ub',
			user_name: 'Émile',
			total_points: 50,
			breakdown: mkBreakdown({ match_outcome_points: 10, quarter_final_points: 40 })
		}),
		mkRow({
			entry_id: 'c',
			user_id: 'uc',
			user_name: 'adam',
			total_points: 80,
			breakdown: mkBreakdown({ match_outcome_points: 80 })
		})
	];

	it('default sort: total desc, ties alphabetical A→Z', () => {
		const out = sortRows(rows, DEFAULT_LB_SORT, none);
		// c (80) first; a/b tie at 50 → Émile before Zara (accent-insensitive).
		expect(out.map((r) => r.entry_id)).toEqual(['c', 'b', 'a']);
	});

	it('entry column sorts by display name, case/accent-insensitive', () => {
		const asc = sortRows(rows, { key: 'entry', dir: 'asc' }, none);
		expect(asc.map((r) => r.user_name)).toEqual(['adam', 'Émile', 'Zara']);
		const desc = sortRows(rows, { key: 'entry', dir: 'desc' }, none);
		expect(desc.map((r) => r.user_name)).toEqual(['Zara', 'Émile', 'adam']);
	});

	it('group and knockout columns sort by the rendered cell values', () => {
		const group = sortRows(rows, { key: 'group', dir: 'desc' }, none);
		expect(group.map((r) => r.entry_id)).toEqual(['c', 'a', 'b']); // 80/30/10
		const ko = sortRows(rows, { key: 'knockout', dir: 'desc' }, none);
		expect(ko.map((r) => r.entry_id)).toEqual(['b', 'a', 'c']); // 40/20/0
	});

	it('uses the multi-owner display name for the entry sort', () => {
		const pair = [
			mkRow({ entry_id: 'x1', user_id: 'u9', user_name: 'Bob', entry_name: 'Zulu' }),
			mkRow({ entry_id: 'x2', user_id: 'u9', user_name: 'Bob', entry_name: 'Alpha' })
		];
		const multi = multiEntryUserIds(pair);
		const out = sortRows(pair, { key: 'entry', dir: 'asc' }, multi);
		// "Bob — Alpha" before "Bob — Zulu"
		expect(out.map((r) => r.entry_id)).toEqual(['x2', 'x1']);
	});

	it('does not mutate the input and keeps server positions intact', () => {
		const input = [...rows];
		const out = sortRows(rows, { key: 'entry', dir: 'asc' }, none);
		expect(rows).toEqual(input);
		expect(out.every((r, i) => r.position === rows.find((x) => x.entry_id === r.entry_id)?.position)).toBe(true);
	});
});

// ---------------------------------------------------------------------------
// selectRaceSlice — Race-tab redesign (2026-06-22 spec)
// ---------------------------------------------------------------------------

import { selectRaceSlice } from './leaderboardV4';
import type { EntryTrajectory } from '$lib/types/leaderboard';

function mkTraj(
	entry_id: string,
	rank: number,
	user_id = entry_id,
): EntryTrajectory {
	return {
		entry_id,
		entry_name: `entry-${entry_id}`,
		user_id,
		user_name: `user-${entry_id}`,
		points: [{ position: rank, total_points: 100 - rank, captured_date: '2026-06-22' }],
	};
}

describe('selectRaceSlice', () => {
	const pool: EntryTrajectory[] = Array.from({ length: 50 }, (_, i) =>
		mkTraj(`E${i + 1}`, i + 1, `u-E${i + 1}`),
	);

	it('around_me — user at #27, 7-line slice plus leader ghost', () => {
		const result = selectRaceSlice(pool, 'around_me', 'u-E27');
		const ranks = result.included.map((t) => t.points[0].position).sort((a, b) => a - b);
		expect(ranks).toEqual([1, 24, 25, 26, 27, 28, 29, 30]);
	});

	it('around_me — user at #1, no leader ghost duplicate', () => {
		const result = selectRaceSlice(pool, 'around_me', 'u-E1');
		const ranks = result.included.map((t) => t.points[0].position).sort((a, b) => a - b);
		expect(ranks).toEqual([1, 2, 3, 4, 5, 6, 7]);
	});

	it('top15 — user in top 15, 15 entries', () => {
		const result = selectRaceSlice(pool, 'top15', 'u-E5');
		expect(result.included).toHaveLength(15);
	});

	it('top15 — user outside top 15, user added (16 entries)', () => {
		const result = selectRaceSlice(pool, 'top15', 'u-E27');
		expect(result.included).toHaveLength(16);
		expect(result.included.some((t) => t.entry_id === 'E27')).toBe(true);
	});

	it('null userId (signed-out) — around_me falls back to top15', () => {
		const result = selectRaceSlice(pool, 'around_me', null);
		expect(result.included).toHaveLength(15);
	});

	it('signed-in user with zero entries — around_me falls back to top15', () => {
		const result = selectRaceSlice(pool, 'around_me', 'u-NOT-IN-POOL');
		expect(result.included).toHaveLength(15);
	});

	it('multi-entry minimap marker present', () => {
		const result = selectRaceSlice(pool, 'around_me', 'u-E27');
		expect(result.minimapMarkers.find((m) => m.kind === 'you')?.rank).toBe(27);
	});

	it('rankRange brackets the slice', () => {
		const result = selectRaceSlice(pool, 'around_me', 'u-E27');
		expect(result.rankRange[0]).toBeLessThanOrEqual(1);
		expect(result.rankRange[1]).toBeGreaterThanOrEqual(30);
	});
});

describe('composeRankDelta', () => {
	it('positive: returns ▲ N', () => expect(composeRankDelta(12)).toBe('▲ 12'));
	it('negative: returns ▼ N', () => expect(composeRankDelta(-3)).toBe('▼ 3'));
	it('zero: returns —', () => expect(composeRankDelta(0)).toBe('—'));
});

describe('firstTwoPlusExpand', () => {
	const arr = ['a', 'b', 'c', 'd'];

	it('expanded=false → first 2 + remaining count', () => {
		const r = firstTwoPlusExpand(arr, false);
		expect(r.visible).toEqual(['a', 'b']);
		expect(r.remaining).toBe(2);
	});

	it('expanded=true → all + zero remaining', () => {
		const r = firstTwoPlusExpand(arr, true);
		expect(r.visible).toEqual(arr);
		expect(r.remaining).toBe(0);
	});

	it('≤ 2 items: returns all, zero remaining regardless', () => {
		expect(firstTwoPlusExpand(['x'], false).remaining).toBe(0);
		expect(firstTwoPlusExpand([], false).visible).toEqual([]);
	});
});
