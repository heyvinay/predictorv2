import { describe, expect, it } from 'vitest';

import { canonicalize, extractH2HOdds, findOddsForFixture } from './teamMatch';
import type { OddsApiMatch } from './oddsCache';

function makeMatch(overrides: Partial<OddsApiMatch> = {}): OddsApiMatch {
	return {
		id: 'm1',
		sport_key: 'soccer_fifa_world_cup',
		commence_time: '2026-06-15T12:00:00Z',
		home_team: 'England',
		away_team: 'Brazil',
		bookmakers: [],
		...overrides
	};
}

function bookmaker(home: number, draw: number, away: number, homeTeam = 'England', awayTeam = 'Brazil') {
	return {
		key: 'bet365',
		title: 'Bet365',
		last_update: '2026-06-15T11:00:00Z',
		markets: [
			{
				key: 'h2h',
				outcomes: [
					{ name: homeTeam, price: home },
					{ name: 'Draw', price: draw },
					{ name: awayTeam, price: away }
				]
			}
		]
	};
}

describe('canonicalize', () => {
	it('lowercases and trims', () => {
		expect(canonicalize('  England  ')).toBe('england');
	});

	it('collapses internal whitespace', () => {
		expect(canonicalize('South   Korea')).toBe('south korea');
	});

	it('resolves USA alias to United States', () => {
		expect(canonicalize('USA')).toBe('united states');
	});

	it('resolves Korea Republic to South Korea', () => {
		expect(canonicalize('Korea Republic')).toBe('south korea');
	});

	it('passes through unknown names unchanged (just normalised)', () => {
		expect(canonicalize('Belgium')).toBe('belgium');
	});

	it('is idempotent — canonicalising twice gives the same result', () => {
		const once = canonicalize('USA');
		expect(canonicalize(once)).toBe(once);
	});
});

describe('findOddsForFixture', () => {
	const matches: OddsApiMatch[] = [
		makeMatch({ id: 'm1', home_team: 'England', away_team: 'Brazil' }),
		makeMatch({ id: 'm2', home_team: 'USA', away_team: 'Mexico' })
	];

	it('exact hit returns the match', () => {
		const result = findOddsForFixture(
			{ home_team: 'England', away_team: 'Brazil' },
			matches
		);
		expect(result?.id).toBe('m1');
	});

	it('alias hit: fixture says "United States", API says "USA"', () => {
		const result = findOddsForFixture(
			{ home_team: 'United States', away_team: 'Mexico' },
			matches
		);
		expect(result?.id).toBe('m2');
	});

	it('case + whitespace tolerant', () => {
		const result = findOddsForFixture(
			{ home_team: '  england ', away_team: 'BRAZIL' },
			matches
		);
		expect(result?.id).toBe('m1');
	});

	it('miss returns null', () => {
		const result = findOddsForFixture(
			{ home_team: 'Argentina', away_team: 'France' },
			matches
		);
		expect(result).toBeNull();
	});

	it('order-sensitive (home/away swap is a different fixture)', () => {
		const result = findOddsForFixture(
			{ home_team: 'Brazil', away_team: 'England' },
			matches
		);
		expect(result).toBeNull();
	});
});

describe('extractH2HOdds', () => {
	it('averages prices across multiple bookmakers', () => {
		const match = makeMatch({
			bookmakers: [bookmaker(2.0, 3.0, 4.0), bookmaker(2.2, 3.2, 4.4)]
		});
		const odds = extractH2HOdds(match);
		expect(odds?.home).toBeCloseTo(2.1, 6);
		expect(odds?.draw).toBeCloseTo(3.1, 6);
		expect(odds?.away).toBeCloseTo(4.2, 6);
	});

	it('returns the single-bookmaker value when only one is present', () => {
		const match = makeMatch({ bookmakers: [bookmaker(2.0, 3.0, 4.0)] });
		const odds = extractH2HOdds(match);
		expect(odds).toEqual({ home: 2.0, draw: 3.0, away: 4.0 });
	});

	it('skips bookmakers missing the h2h market', () => {
		const match = makeMatch({
			bookmakers: [
				{
					key: 'incomplete',
					title: 'Incomplete',
					last_update: '2026-06-15T11:00:00Z',
					markets: [] // no h2h
				},
				bookmaker(2.0, 3.0, 4.0)
			]
		});
		const odds = extractH2HOdds(match);
		expect(odds).toEqual({ home: 2.0, draw: 3.0, away: 4.0 });
	});

	it('skips bookmakers with partial outcomes (missing one of home/draw/away)', () => {
		const match = makeMatch({
			bookmakers: [
				{
					key: 'partial',
					title: 'Partial',
					last_update: '2026-06-15T11:00:00Z',
					markets: [
						{
							key: 'h2h',
							outcomes: [
								{ name: 'England', price: 1.5 },
								{ name: 'Draw', price: 3.0 }
								// Brazil missing
							]
						}
					]
				},
				bookmaker(2.0, 3.0, 4.0)
			]
		});
		const odds = extractH2HOdds(match);
		expect(odds).toEqual({ home: 2.0, draw: 3.0, away: 4.0 });
	});

	it('returns null when no bookmaker has a complete h2h market', () => {
		const match = makeMatch({ bookmakers: [] });
		const odds = extractH2HOdds(match);
		expect(odds).toBeNull();
	});

	it('matches outcomes via alias (API uses "USA", fixture canonical "United States")', () => {
		const match = makeMatch({
			home_team: 'USA',
			away_team: 'Mexico',
			bookmakers: [bookmaker(1.8, 3.2, 4.5, 'USA', 'Mexico')]
		});
		const odds = extractH2HOdds(match);
		expect(odds).toEqual({ home: 1.8, draw: 3.2, away: 4.5 });
	});
});
