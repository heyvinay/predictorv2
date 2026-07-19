import { describe, expect, it } from 'vitest';
import type { Fixture } from '$types';
import type { MatchPredictionWithPoints } from '$lib/types/results';
import {
	buildMatchRows,
	buildSummary,
	type CompareEntryInput
} from './compareEntries';

const FX = (id: string, n: number, home: string, away: string, hs: number, as_: number, stage = 'group'): Fixture =>
	({
		id, home_team: home, away_team: away, kickoff: '2026-06-12T18:00:00Z',
		stage, group: stage === 'group' ? 'A' : null, match_number: n,
		status: 'finished', minute: null, is_locked: true, time_until_lock: null,
		score: { home_score: hs, away_score: as_, home_score_et: null, away_score_et: null, home_penalties: null, away_penalties: null, outcome: hs > as_ ? '1' : hs < as_ ? '2' : 'X' },
		venue_city: null, venue_country: null, venue_country_code: null
	}) as Fixture;

const PICK = (fixtureId: string, hs: number, as_: number, total: number, kind: 'miss' | 'result' | 'exact'): MatchPredictionWithPoints =>
	({
		id: fixtureId + '-p', entry_id: 'e', fixture_id: fixtureId,
		home_score: hs, away_score: as_, phase: 'phase_1',
		locked_at: null, created_at: '', updated_at: '', is_locked: true,
		points: total === 0 ? { base: 0, base_kind: 'miss', rarity: 0, total: 0 } : { base: kind === 'exact' ? 10 : 5, base_kind: kind, rarity: total - (kind === 'exact' ? 10 : 5), total }
	}) as MatchPredictionWithPoints;

const fixtures = new Map<string, Fixture>([
	['f1', FX('f1', 11, 'England', 'Iran', 2, 0)],
	['f2', FX('f2', 42, 'Japan', 'Poland', 1, 1)]
]);

function input(partial: Partial<CompareEntryInput>): CompareEntryInput {
	return {
		entryId: 'e', displayName: 'E', finalRank: 1, totalPoints: 0,
		groupPoints: 0, knockoutPoints: 0, bonusPoints: 0,
		matches: [], bracket: null, bonusReads: [], questionLabels: new Map(),
		...partial
	};
}

describe('buildSummary', () => {
	it('deltas are A minus B per bucket', () => {
		const a = input({ totalPoints: 612, groupPoints: 348, knockoutPoints: 214, bonusPoints: 50 });
		const b = input({ totalPoints: 598, groupPoints: 356, knockoutPoints: 202, bonusPoints: 40 });
		expect(buildSummary(a, b)).toEqual({ total: 14, group: -8, knockout: 12, bonus: 10 });
	});
});

describe('buildMatchRows', () => {
	it('joins picks by fixture and computes delta', () => {
		const a = input({ matches: [PICK('f1', 2, 0, 13.2, 'exact'), PICK('f2', 0, 0, 0, 'miss')] });
		const b = input({ matches: [PICK('f1', 1, 0, 5, 'result'), PICK('f2', 1, 1, 14.1, 'exact')] });
		const rows = buildMatchRows(a, b, fixtures);
		expect(rows).toHaveLength(2);
		const m11 = rows.find((r) => r.fixtureId === 'f1')!;
		expect(m11.label).toBe('M11 · England vs Iran 2–0');
		expect(m11.aPoints).toBeCloseTo(13.2);
		expect(m11.bPoints).toBe(5);
		expect(m11.delta).toBeCloseTo(8.2);
		expect(m11.aKind).toBe('exact');
		expect(m11.bKind).toBe('result');
	});

	it('skips fixtures without a finished score', () => {
		const unf = new Map(fixtures);
		unf.set('f3', { ...FX('f3', 99, 'A', 'B', 0, 0), status: 'scheduled', score: null } as Fixture);
		const a = input({ matches: [PICK('f3', 1, 0, 0, 'miss')] });
		expect(buildMatchRows(a, input({}), unf)).toHaveLength(0);
	});
});

import type { ScoringRules } from '$lib/types/results';
import { buildBonusRows, buildBracketRows, buildSwings, elementValues } from './compareEntries';

const RULES: ScoringRules = {
	mode: 'logarithmic',
	match: { correct_outcome: 5, exact_score: 10, rarity_cap: 5 },
	advancement: { round_of_32: 2, round_of_16: 4, quarter_final: 8, semi_final: 16, final: 32, winner: 64 }
};

const bracket = (over: Partial<import('$types').BracketPrediction>) => ({
	group_winners: {}, round_of_32: [], round_of_16: [],
	quarter_finals: [], semi_finals: [], final: [], winner: '',
	...over
});

describe('buildBracketRows', () => {
	it('per-stage hits vs actual advancement, points from rules', () => {
		const a = input({ bracket: bracket({ semi_finals: ['Argentina', 'France', 'Spain', 'England'], winner: 'Argentina' }) });
		const b = input({ bracket: bracket({ semi_finals: ['Argentina', 'Brazil', 'Spain', 'Portugal'], winner: 'France' }) });
		const actual = { semi_final: new Set(['Argentina', 'France', 'Spain', 'Morocco']), winner: new Set(['Argentina']) };
		const rows = buildBracketRows(a, b, actual, RULES);
		const sf = rows.find((r) => r.stage === 'semi_final')!;
		expect(sf.aHits).toBe(3);
		expect(sf.bHits).toBe(2);
		expect(sf.aPoints).toBe(48); // 3 × 16
		expect(sf.delta).toBe(16);
		const w = rows.find((r) => r.stage === 'winner')!;
		expect(w.aHits).toBe(1);
		expect(w.bHits).toBe(0);
		expect(w.delta).toBe(64);
	});
});

describe('buildBonusRows + buildSwings', () => {
	it('bonus rows join labels; swings rank every differing element by |delta|', () => {
		const labels = new Map([['q1', 'Knockout Top / Flop']]);
		const a = input({
			matches: [PICK('f1', 2, 0, 13.2, 'exact')],
			bonusReads: [{ question_id: 'q1', answer: 'Türkiye', category: 'top_flop', points: 10, hit: true }],
			questionLabels: labels,
			bracket: bracket({ winner: 'Argentina' })
		});
		const b = input({
			matches: [PICK('f1', 1, 0, 5, 'result')],
			bonusReads: [{ question_id: 'q1', answer: 'Belgium', category: 'top_flop', points: 0, hit: false }],
			questionLabels: labels,
			bracket: bracket({ winner: 'France' })
		});
		const actual = { winner: new Set(['Argentina']) };
		const bonusRows = buildBonusRows(a, b);
		expect(bonusRows[0].label).toBe('Knockout Top / Flop');
		expect(bonusRows[0].delta).toBe(10);

		const swings = buildSwings(a, b, fixtures, actual, RULES);
		// winner stage (64) > bonus (10) > match (8.2)
		expect(swings.map((s) => s.kind)).toEqual(['bracket', 'bonus', 'match']);
		expect(swings[0].delta).toBe(64);
		expect(swings[2].delta).toBeCloseTo(8.2);
		// equal elements are excluded
		expect(swings.every((s) => s.delta !== 0)).toBe(true);
	});
});

describe('elementValues', () => {
	it('returns each entry\'s own raw value for a match/bracket/bonus element, in input order', () => {
		const labels = new Map([['q1', 'Knockout Top / Flop']]);
		const a = input({
			matches: [PICK('f1', 2, 0, 13.2, 'exact')],
			bonusReads: [{ question_id: 'q1', answer: 'Türkiye', category: 'top_flop', points: 10, hit: true }],
			questionLabels: labels,
			bracket: bracket({ winner: 'Argentina' })
		});
		const b = input({
			matches: [PICK('f1', 1, 0, 5, 'result')],
			bonusReads: [{ question_id: 'q1', answer: 'Belgium', category: 'top_flop', points: 0, hit: false }],
			questionLabels: labels,
			bracket: bracket({ winner: 'France' })
		});
		const c = input({
			matches: [PICK('f1', 2, 0, 13.2, 'exact')],
			bonusReads: [{ question_id: 'q1', answer: 'Argentina', category: 'top_flop', points: 10, hit: true }],
			questionLabels: labels,
			bracket: bracket({ winner: 'Argentina' })
		});
		const actual = { winner: new Set(['Argentina']) };
		const swings = buildSwings(a, b, fixtures, actual, RULES);

		const matchSwing = swings.find((s) => s.kind === 'match')!;
		expect(elementValues([a, b, c], matchSwing, actual, RULES)).toEqual([13.2, 5, 13.2]);

		const winnerSwing = swings.find((s) => s.kind === 'bracket')!;
		expect(elementValues([a, b, c], winnerSwing, actual, RULES)).toEqual([64, 0, 64]);

		const bonusSwing = swings.find((s) => s.kind === 'bonus')!;
		expect(elementValues([a, b, c], bonusSwing, actual, RULES)).toEqual([10, 0, 10]);
	});

	it('a non-winner bracket stage sums hits × per-stage points for each entry', () => {
		const a = input({ bracket: bracket({ semi_finals: ['Argentina', 'France', 'Spain', 'England'] }) });
		const b = input({ bracket: bracket({ semi_finals: ['Argentina', 'Brazil', 'Spain', 'Portugal'] }) });
		const actual = { semi_final: new Set(['Argentina', 'France', 'Spain', 'Morocco']) };
		const sfSwing = {
			kind: 'bracket' as const,
			label: 'Knockout — Semi-finals',
			why: '',
			delta: 16,
			key: 'semi_final'
		};
		// a has 3 hits (Argentina, France, Spain) × 16 = 48; b has 2 (Argentina, Spain) × 16 = 32
		expect(elementValues([a, b], sfSwing, actual, RULES)).toEqual([48, 32]);
	});
});
