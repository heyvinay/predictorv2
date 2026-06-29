import { describe, expect, it } from 'vitest';
import type { BracketPrediction, Fixture } from '$types';
import {
	bracketPicksForRound,
	fixtureKoHits,
	missedR32Picks,
	progressingSplit,
	stagePointsForRound
} from './koPoints';

const BRACKET: BracketPrediction = {
	group_winners: {},
	round_of_32: ['Mexico', 'Senegal', 'Brazil', 'Italy'],
	round_of_16: ['Mexico', 'Brazil'],
	quarter_finals: ['Brazil'],
	semi_finals: ['Brazil'],
	final: ['Brazil'],
	winner: 'Brazil'
};

const RULES_ADVANCEMENT = {
	round_of_32: 20,
	round_of_16: 30,
	quarter_final: 40,
	semi_final: 50,
	final: 75,
	winner: 100
};

function fx(partial: Partial<Fixture>): Fixture {
	return {
		id: partial.id ?? crypto.randomUUID(),
		home_team: 'Mexico',
		away_team: 'Senegal',
		kickoff: '2026-06-28T18:00:00+00:00',
		stage: 'round_of_32',
		group: null,
		match_number: 73,
		status: 'scheduled',
		minute: null,
		is_locked: true,
		time_until_lock: null,
		score: null,
		...partial
	} as Fixture;
}

describe('bracketPicksForRound', () => {
	it('bridges plural API fields to round ids', () => {
		expect(bracketPicksForRound(BRACKET, 'r32')).toEqual(
			new Set(['Mexico', 'Senegal', 'Brazil', 'Italy'])
		);
		expect(bracketPicksForRound(BRACKET, 'qf')).toEqual(new Set(['Brazil']));
		expect(bracketPicksForRound(null, 'r32')).toEqual(new Set());
	});
});

describe('stagePointsForRound', () => {
	it('reads stage-specific values from scoring rules', () => {
		expect(stagePointsForRound(RULES_ADVANCEMENT, 'r32')).toBe(20);
		expect(stagePointsForRound(RULES_ADVANCEMENT, 'sf')).toBe(50);
		expect(stagePointsForRound(RULES_ADVANCEMENT, 'f')).toBe(75);
	});
});

describe('fixtureKoHits', () => {
	const picks = bracketPicksForRound(BRACKET, 'r32');

	it('counts 2 when both teams picked', () => {
		expect(fixtureKoHits(fx({}), picks)).toEqual({ home: true, away: true, hits: 2 });
	});

	it('counts 1 when one team picked', () => {
		expect(fixtureKoHits(fx({ away_team: 'France' }), picks)).toEqual({
			home: true,
			away: false,
			hits: 1
		});
	});

	it('counts 0 for a third_place fixture regardless of picks', () => {
		expect(fixtureKoHits(fx({ stage: 'third_place' }), picks)).toEqual({
			home: false,
			away: false,
			hits: 0
		});
	});

	// Per-side resolution (v2.184.x — supersedes the v2.183.3 all-or-nothing
	// gate). A half-resolved fixture (one side real, other still slot:*)
	// now counts the hit on the RESOLVED side if that team is in the
	// user's picks. The previous behaviour returned hits=0 in this case
	// which hid the user's banked R16-advancement points from the Round
	// Total once R32 winners started flowing through to R16 fixtures.
	// Fully-unresolved fixtures (both sides slot:*) still return hits=0.
	it('counts per-side hits when only one side is a slot placeholder', () => {
		// Mexico (picked) vs slot — counts the home hit
		expect(
			fixtureKoHits(
				fx({ home_team: 'Mexico', away_team: 'slot:round_of_32:537416:away' }),
				picks
			)
		).toEqual({ home: true, away: false, hits: 1 });
		// slot vs Senegal (picked) — counts the away hit
		expect(
			fixtureKoHits(
				fx({ home_team: 'slot:round_of_32:537416:home', away_team: 'Senegal' }),
				picks
			)
		).toEqual({ home: false, away: true, hits: 1 });
		// fully unresolved — no claim either way
		expect(
			fixtureKoHits(
				fx({
					home_team: 'slot:round_of_32:537416:home',
					away_team: 'slot:round_of_32:537416:away'
				}),
				picks
			)
		).toEqual({ home: false, away: false, hits: 0 });
	});
});

describe('progressingSplit', () => {
	it('splits finished-fixture winners by next-round membership', () => {
		const fixtures = [
			fx({
				id: 'w1',
				status: 'finished',
				score: { home_score: 2, away_score: 1, outcome: '1' } as Fixture['score']
			}), // Mexico wins — in r16 picks
			fx({
				id: 'w2',
				home_team: 'Spain',
				away_team: 'Brazil',
				status: 'finished',
				score: { home_score: 0, away_score: 2, outcome: '2' } as Fixture['score']
			}), // Brazil wins — in r16 picks
			fx({
				id: 'w3',
				home_team: 'France',
				away_team: 'Norway',
				status: 'finished',
				score: { home_score: 1, away_score: 0, outcome: '1' } as Fixture['score']
			}), // France wins — NOT in r16 picks
			fx({ id: 'w4', status: 'live' }) // live — excluded
		];
		const next = bracketPicksForRound(BRACKET, 'r16');
		const split = progressingSplit(fixtures, next);
		expect(split.inNext).toEqual(['Mexico', 'Brazil']);
		expect(split.notInNext).toEqual(['France']);
	});
});

describe('missedR32Picks', () => {
	it('lists picks absent from the seeded R32 lineup', () => {
		const fixtures = [
			fx({ home_team: 'Mexico', away_team: 'Senegal' }),
			fx({ id: 'x', home_team: 'Brazil', away_team: 'USA' })
		];
		const picks = bracketPicksForRound(BRACKET, 'r32');
		expect(missedR32Picks(fixtures, picks)).toEqual(['Italy']);
	});

	it('returns empty before the lineup is seeded (placeholder team names)', () => {
		const fixtures = [fx({ home_team: '1A', away_team: '2B' })];
		const picks = bracketPicksForRound(BRACKET, 'r32');
		expect(missedR32Picks(fixtures, picks)).toEqual([]);
	});
});
