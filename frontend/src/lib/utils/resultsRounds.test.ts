import { describe, expect, it } from 'vitest';
import type { Fixture } from '$types';
import {
	buildRounds,
	NEXT_ROUND,
	ROUND_LABELS,
	roundIdForFixture,
	formatDateRange
} from './resultsRounds';

function fx(partial: Partial<Fixture>): Fixture {
	return {
		id: partial.id ?? crypto.randomUUID(),
		home_team: 'Home',
		away_team: 'Away',
		kickoff: '2026-06-11T18:00:00+00:00',
		stage: 'group',
		group: 'A',
		match_number: 1,
		status: 'scheduled',
		minute: null,
		is_locked: false,
		time_until_lock: null,
		score: null,
		...partial
	} as Fixture;
}

describe('roundIdForFixture', () => {
	it('buckets group fixtures into matchdays by match_number', () => {
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 1 }))).toBe('r1');
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 24 }))).toBe('r1');
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 25 }))).toBe('r2');
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 48 }))).toBe('r2');
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 49 }))).toBe('r3');
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 72 }))).toBe('r3');
	});

	it('maps singular knockout stages', () => {
		expect(roundIdForFixture(fx({ stage: 'round_of_32' }))).toBe('r32');
		expect(roundIdForFixture(fx({ stage: 'round_of_16' }))).toBe('r16');
		expect(roundIdForFixture(fx({ stage: 'quarter_final' }))).toBe('qf');
		expect(roundIdForFixture(fx({ stage: 'semi_final' }))).toBe('sf');
		expect(roundIdForFixture(fx({ stage: 'final' }))).toBe('f');
	});

	it('returns null for unknown stages', () => {
		expect(roundIdForFixture(fx({ stage: 'mystery' }))).toBeNull();
	});

	it('drops the third-place playoff — predictions are not collected for it', () => {
		// Previously bucketed into 'f', which produced a phantom second
		// row in the Finals tab. Now excluded everywhere.
		expect(roundIdForFixture(fx({ stage: 'third_place' }))).toBeNull();
	});
});

describe('buildRounds', () => {
	it('produces all ten rounds in display order with fixtures attached', () => {
		const fixtures = [
			fx({ id: 'a', stage: 'group', match_number: 3, kickoff: '2026-06-12T18:00:00+00:00' }),
			fx({ id: 'b', stage: 'group', match_number: 30, kickoff: '2026-06-19T18:00:00+00:00' }),
			fx({ id: 'c', stage: 'round_of_32', match_number: 73, kickoff: '2026-06-28T18:00:00+00:00' }),
			fx({ id: 'd', stage: 'final', match_number: 104, kickoff: '2026-07-19T18:00:00+00:00' })
		];
		const rounds = buildRounds(fixtures);
		expect(rounds.map((r) => r.id)).toEqual([
			'summary',
			'r1',
			'r2',
			'r3',
			'r32',
			'r16',
			'qf',
			'sf',
			'f',
			'winner'
		]);
		expect(rounds.find((r) => r.id === 'r1')?.fixtureIds).toEqual(['a']);
		expect(rounds.find((r) => r.id === 'r2')?.fixtureIds).toEqual(['b']);
		expect(rounds.find((r) => r.id === 'r32')?.fixtureIds).toEqual(['c']);
		expect(rounds.find((r) => r.id === 'f')?.fixtureIds).toEqual(['d']);
		expect(rounds.find((r) => r.id === 'winner')?.fixtureIds).toEqual([]);
	});

	it('orders fixtures within a round by kickoff', () => {
		const fixtures = [
			fx({ id: 'late', stage: 'group', match_number: 9, kickoff: '2026-06-14T18:00:00+00:00' }),
			fx({ id: 'early', stage: 'group', match_number: 2, kickoff: '2026-06-11T20:00:00+00:00' })
		];
		const r1 = buildRounds(fixtures).find((r) => r.id === 'r1');
		expect(r1?.fixtureIds).toEqual(['early', 'late']);
	});

	it('marks knockout rounds', () => {
		const rounds = buildRounds([]);
		expect(rounds.find((r) => r.id === 'r1')?.isKnockout).toBe(false);
		expect(rounds.find((r) => r.id === 'r32')?.isKnockout).toBe(true);
		expect(rounds.find((r) => r.id === 'f')?.isKnockout).toBe(true);
	});

	it('derives matchdays from per-team kickoff order when match_number is NULL (the real DB shape)', () => {
		// Two teams playing each other three times across three dates —
		// per-team ordinal buckets them into r1 / r2 / r3 despite null
		// match_number on every row.
		const fixtures = [
			fx({
				id: 'md3',
				match_number: null as unknown as number,
				home_team: 'Mexico',
				away_team: 'Canada',
				kickoff: '2026-06-25T18:00:00+00:00'
			}),
			fx({
				id: 'md1',
				match_number: null as unknown as number,
				home_team: 'Mexico',
				away_team: 'Canada',
				kickoff: '2026-06-11T18:00:00+00:00'
			}),
			fx({
				id: 'md2',
				match_number: null as unknown as number,
				home_team: 'Canada',
				away_team: 'Mexico',
				kickoff: '2026-06-18T18:00:00+00:00'
			})
		];
		const rounds = buildRounds(fixtures);
		expect(rounds.find((r) => r.id === 'r1')?.fixtureIds).toEqual(['md1']);
		expect(rounds.find((r) => r.id === 'r2')?.fixtureIds).toEqual(['md2']);
		expect(rounds.find((r) => r.id === 'r3')?.fixtureIds).toEqual(['md3']);
	});
});

describe('formatDateRange', () => {
	it('renders same-day as a single date', () => {
		expect(
			formatDateRange('2026-07-19T16:00:00+00:00', '2026-07-19T20:00:00+00:00')
		).toBe('19 Jul');
	});
	it('renders a cross-day range', () => {
		expect(
			formatDateRange('2026-06-11T18:00:00+00:00', '2026-06-18T20:00:00+00:00')
		).toBe('11 – 18 Jun');
	});
	it('renders a cross-month range with both months', () => {
		expect(
			formatDateRange('2026-06-28T18:00:00+00:00', '2026-07-04T20:00:00+00:00')
		).toBe('28 Jun – 4 Jul');
	});
});

describe('NEXT_ROUND', () => {
	it('chains KO rounds and ends at the final', () => {
		expect(NEXT_ROUND.r32).toBe('r16');
		expect(NEXT_ROUND.r16).toBe('qf');
		expect(NEXT_ROUND.qf).toBe('sf');
		expect(NEXT_ROUND.sf).toBe('f');
		expect(NEXT_ROUND.f).toBeNull();
	});
});

describe('ROUND_LABELS', () => {
	it('has a label for every round', () => {
		for (const id of ['summary', 'r1', 'r2', 'r3', 'r32', 'r16', 'qf', 'sf', 'f', 'winner']) {
			expect(ROUND_LABELS[id as keyof typeof ROUND_LABELS]).toBeTruthy();
		}
	});
});
