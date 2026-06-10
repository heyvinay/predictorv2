import { describe, expect, it } from 'vitest';
import type { Fixture } from '$types';
import type { RoundDef } from '$lib/types/results';
import { defaultRound, roundsWithLive } from './roundsLive';

function fx(id: string, status: string, kickoff: string): Fixture {
	return {
		id,
		home_team: 'H',
		away_team: 'A',
		kickoff,
		stage: 'group',
		group: 'A',
		match_number: 1,
		status,
		minute: null,
		is_locked: false,
		time_until_lock: null,
		score: null
	} as unknown as Fixture;
}

function round(id: string, fixtureIds: string[]): RoundDef {
	return {
		id: id as RoundDef['id'],
		label: id,
		dates: '',
		isKnockout: ['r32', 'r16', 'qf', 'sf', 'f'].includes(id),
		fixtureIds
	};
}

const ROUNDS: RoundDef[] = [
	round('summary', []),
	round('r1', ['a', 'b']),
	round('r2', ['c']),
	round('r3', []),
	round('r32', ['d']),
	round('r16', []),
	round('qf', []),
	round('sf', []),
	round('f', []),
	round('winner', [])
];

describe('roundsWithLive', () => {
	it('is empty when nothing is live', () => {
		const map = new Map([
			['a', fx('a', 'finished', '2026-06-11T18:00:00+00:00')],
			['c', fx('c', 'scheduled', '2026-06-18T18:00:00+00:00')]
		]);
		expect(roundsWithLive(ROUNDS, map).size).toBe(0);
	});

	it('contains the round of a live fixture (halftime counts)', () => {
		const map = new Map([
			['a', fx('a', 'live', '2026-06-11T18:00:00+00:00')],
			['c', fx('c', 'halftime', '2026-06-18T18:00:00+00:00')]
		]);
		const live = roundsWithLive(ROUNDS, map);
		expect(live.has('r1')).toBe(true);
		expect(live.has('r2')).toBe(true);
		expect(live.has('r3')).toBe(false);
	});
});

describe('defaultRound', () => {
	const fixturesByDate = new Map([
		['a', fx('a', 'finished', '2026-06-11T18:00:00+00:00')],
		['b', fx('b', 'finished', '2026-06-14T18:00:00+00:00')],
		['c', fx('c', 'scheduled', '2026-06-19T18:00:00+00:00')],
		['d', fx('d', 'scheduled', '2026-06-28T18:00:00+00:00')]
	]);

	it('LIVE round wins — earliest in tab order on a transition day', () => {
		const map = new Map(fixturesByDate);
		map.set('c', fx('c', 'live', '2026-06-18T18:00:00+00:00'));
		map.set('b', fx('b', 'live', '2026-06-18T15:00:00+00:00'));
		// both r1 (b) and r2 (c) live → earliest tab order = r1
		expect(defaultRound(ROUNDS, map, new Date('2026-06-18T19:00:00+00:00'))).toBe('r1');
	});

	it('falls back to the round whose window contains today', () => {
		expect(defaultRound(ROUNDS, fixturesByDate, new Date('2026-06-12T12:00:00+00:00'))).toBe(
			'r1'
		);
	});

	it('falls back to the last completed round between rounds', () => {
		// 2026-06-16: r1 padded window ended (14 Jun + 1d), r2 not started
		expect(defaultRound(ROUNDS, fixturesByDate, new Date('2026-06-16T12:00:00+00:00'))).toBe(
			'r1'
		);
	});

	it('falls back to r1 before the tournament', () => {
		expect(defaultRound(ROUNDS, fixturesByDate, new Date('2026-06-01T12:00:00+00:00'))).toBe(
			'r1'
		);
	});
});
