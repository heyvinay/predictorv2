import { describe, expect, it } from 'vitest';

import { oddsScoreline } from './oddsScoreline';
import type { OddsApiMatch } from './oddsCache';

function matchWith(home: string, away: string, prices: [number, number, number]): OddsApiMatch {
	const [h, d, a] = prices;
	return {
		id: `${home}-${away}`,
		sport_key: 'soccer_fifa_world_cup',
		commence_time: '2026-06-15T12:00:00Z',
		home_team: home,
		away_team: away,
		bookmakers: [
			{
				key: 'bet365',
				title: 'Bet365',
				last_update: '2026-06-15T11:00:00Z',
				markets: [
					{
						key: 'h2h',
						outcomes: [
							{ name: home, price: h },
							{ name: 'Draw', price: d },
							{ name: away, price: a }
						]
					}
				]
			}
		]
	};
}

describe('oddsScoreline', () => {
	const fetchedAt = '2026-06-15T12:00:00Z';

	it('happy path: returns a deterministic tuple for a matched fixture', async () => {
		const apiMatches = [matchWith('England', 'Brazil', [2.0, 3.5, 4.0])];
		const result = await oddsScoreline('England', 'Brazil', 'FIX_1', apiMatches, fetchedAt);
		expect(result).not.toBeNull();
		expect(Array.isArray(result)).toBe(true);
		expect(result![0]).toBeGreaterThanOrEqual(0);
		expect(result![1]).toBeGreaterThanOrEqual(0);
	});

	it('determinism: same inputs → identical tuple', async () => {
		const apiMatches = [matchWith('England', 'Brazil', [2.0, 3.5, 4.0])];
		const a = await oddsScoreline('England', 'Brazil', 'FIX_1', apiMatches, fetchedAt);
		const b = await oddsScoreline('England', 'Brazil', 'FIX_1', apiMatches, fetchedAt);
		expect(a).toEqual(b);
	});

	it('returns null when no API match exists for the fixture', async () => {
		const apiMatches = [matchWith('England', 'Brazil', [2.0, 3.5, 4.0])];
		const result = await oddsScoreline('Argentina', 'France', 'FIX_99', apiMatches, fetchedAt);
		expect(result).toBeNull();
	});

	it('returns null when the matched API entry has no usable h2h odds', async () => {
		const apiMatches: OddsApiMatch[] = [
			{
				id: 'm1',
				sport_key: 'soccer_fifa_world_cup',
				commence_time: fetchedAt,
				home_team: 'England',
				away_team: 'Brazil',
				bookmakers: [] // no bookmakers → no h2h odds
			}
		];
		const result = await oddsScoreline('England', 'Brazil', 'FIX_1', apiMatches, fetchedAt);
		expect(result).toBeNull();
	});

	it('alias matching: fixture says "United States", API says "USA"', async () => {
		const apiMatches = [matchWith('USA', 'Mexico', [1.8, 3.2, 4.5])];
		const result = await oddsScoreline(
			'United States',
			'Mexico',
			'FIX_2',
			apiMatches,
			fetchedAt
		);
		expect(result).not.toBeNull();
	});
});
