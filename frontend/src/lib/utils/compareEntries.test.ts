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
		expect(m11.label).toBe('M11 · England 2–0 Iran');
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
