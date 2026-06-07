import { describe, it, expect } from 'vitest';
import { computeGroupTotals } from '../groupPoints';
import type { Fixture, MatchPrediction } from '$types';

const fix = (
	id: string,
	group: string | null,
	status: 'finished' | 'scheduled' = 'finished',
	homeScore: number = 1,
	awayScore: number = 0
): Fixture => ({
	id,
	home_team: 'X',
	away_team: 'Y',
	kickoff: '2026-06-10T00:00:00Z',
	stage: group ? 'group_stage' : 'round_of_16',
	group,
	match_number: null,
	status,
	minute: null,
	is_locked: true,
	time_until_lock: null,
	score:
		status === 'finished'
			? {
					home_score: homeScore,
					away_score: awayScore,
					home_score_et: null,
					away_score_et: null,
					home_penalties: null,
					away_penalties: null,
					outcome: homeScore > awayScore ? '1' : homeScore === awayScore ? 'X' : '2'
				}
			: null,
	venue_city: null,
	venue_country: null,
	venue_country_code: null
});

const pred = (fixtureId: string, h: number, a: number): MatchPrediction => ({
	id: 'p-' + fixtureId,
	entry_id: 'entry-1',
	fixture_id: fixtureId,
	home_score: h,
	away_score: a,
	phase: 'phase_1',
	locked_at: null,
	created_at: '2026-06-01T00:00:00Z',
	updated_at: '2026-06-01T00:00:00Z',
	is_locked: true
});

describe('computeGroupTotals', () => {
	it('returns 0 for every group with no predictions', () => {
		const t = computeGroupTotals([fix('f1', 'A')], []);
		expect(t.A).toBe(0);
		expect(t.L).toBe(0);
	});

	it('awards 10 (5 outcome + 5 exact) for an exact match in group C', () => {
		const t = computeGroupTotals([fix('f1', 'C', 'finished', 1, 0)], [pred('f1', 1, 0)]);
		expect(t.C).toBe(10);
		expect(t.A).toBe(0);
	});

	it('awards 5 for right outcome wrong score', () => {
		const t = computeGroupTotals([fix('f1', 'B', 'finished', 1, 0)], [pred('f1', 2, 0)]);
		expect(t.B).toBe(5);
	});

	it('awards 0 for wrong outcome', () => {
		const t = computeGroupTotals([fix('f1', 'B', 'finished', 1, 0)], [pred('f1', 0, 2)]);
		expect(t.B).toBe(0);
	});

	it('ignores fixtures with no group (knockouts)', () => {
		const t = computeGroupTotals([fix('f1', null)], [pred('f1', 1, 0)]);
		expect(Object.values(t).every((v) => v === 0)).toBe(true);
	});

	it('ignores unfinished fixtures', () => {
		const t = computeGroupTotals([fix('f1', 'A', 'scheduled')], [pred('f1', 1, 0)]);
		expect(t.A).toBe(0);
	});
});
