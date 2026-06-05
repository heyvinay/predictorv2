import { describe, expect, it } from 'vitest';

import {
	buildSeed,
	hashString,
	impliedProbabilities,
	mulberry32,
	simulateScore
} from './simulateScore';

describe('hashString', () => {
	it('is deterministic — same string always gives same hash', () => {
		expect(hashString('FIX_42_2026-06-15')).toBe(hashString('FIX_42_2026-06-15'));
	});

	it('returns a non-negative 32-bit integer', () => {
		const h = hashString('anything');
		expect(h).toBeGreaterThanOrEqual(0);
		expect(h).toBeLessThan(2 ** 32);
		expect(Number.isInteger(h)).toBe(true);
	});

	it('distinguishes nearby inputs', () => {
		// Tiny variations should produce very different hashes — confidence
		// that the seed varies meaningfully per fixture.
		const a = hashString('FIX_42');
		const b = hashString('FIX_43');
		expect(a).not.toBe(b);
	});
});

describe('mulberry32', () => {
	it('is deterministic — same seed yields same sequence', () => {
		const r1 = mulberry32(42);
		const r2 = mulberry32(42);
		const seq1 = [r1(), r1(), r1(), r1()];
		const seq2 = [r2(), r2(), r2(), r2()];
		expect(seq1).toEqual(seq2);
	});

	it('yields values in [0, 1)', () => {
		const r = mulberry32(99);
		for (let i = 0; i < 100; i++) {
			const v = r();
			expect(v).toBeGreaterThanOrEqual(0);
			expect(v).toBeLessThan(1);
		}
	});

	it('different seeds give different sequences', () => {
		const r1 = mulberry32(1);
		const r2 = mulberry32(2);
		expect(r1()).not.toBe(r2());
	});
});

describe('impliedProbabilities', () => {
	it('removes overround — three probabilities sum to ~1', () => {
		const { home, draw, away } = impliedProbabilities(2.0, 3.5, 4.0);
		const total = home + draw + away;
		expect(total).toBeCloseTo(1.0, 6);
	});

	it('assigns higher probability to the lower (favorite) odds', () => {
		const { home, away } = impliedProbabilities(1.3, 5.0, 9.0);
		expect(home).toBeGreaterThan(away);
		expect(home).toBeGreaterThan(0.65);
	});

	it('handles a balanced book (all three near equal)', () => {
		const { home, draw, away } = impliedProbabilities(3.0, 3.0, 3.0);
		expect(home).toBeCloseTo(1 / 3, 6);
		expect(draw).toBeCloseTo(1 / 3, 6);
		expect(away).toBeCloseTo(1 / 3, 6);
	});
});

describe('buildSeed', () => {
	it('uses day granularity (YYYY-MM-DD), not full timestamp', () => {
		expect(buildSeed('FIX_42', '2026-06-15T12:00:00Z')).toBe('FIX_42_2026-06-15');
		expect(buildSeed('FIX_42', '2026-06-15T23:59:59Z')).toBe('FIX_42_2026-06-15');
	});

	it('different days produce different seeds for the same fixture', () => {
		const a = buildSeed('FIX_42', '2026-06-15T12:00:00Z');
		const b = buildSeed('FIX_42', '2026-06-16T12:00:00Z');
		expect(a).not.toBe(b);
	});
});

describe('simulateScore', () => {
	const FAVORITE_HOME = { home: 1.3, draw: 5.0, away: 9.0 };

	it('is deterministic — same inputs always give same scoreline', () => {
		const seed = hashString('FIX_1_2026-06-15');
		const a = simulateScore(2.0, 3.5, 4.0, seed);
		const b = simulateScore(2.0, 3.5, 4.0, seed);
		expect(a).toEqual(b);
	});

	it('determinism holds across many calls', () => {
		const seed = hashString('FIX_42_2026-06-15');
		const first = simulateScore(2.0, 3.5, 4.0, seed);
		for (let i = 0; i < 100; i++) {
			expect(simulateScore(2.0, 3.5, 4.0, seed)).toEqual(first);
		}
	});

	it('different seeds yield varied scorelines (not all identical)', () => {
		const distinct = new Set<string>();
		for (let i = 0; i < 100; i++) {
			const { hs, as } = simulateScore(2.0, 3.5, 4.0, i);
			distinct.add(`${hs}-${as}`);
		}
		// Should see multiple distinct scorelines across 100 seeds.
		expect(distinct.size).toBeGreaterThan(3);
	});

	it('argmax outcome: heavy favorite wins 100% of seeds (no upset sampling)', () => {
		// After the §8 fix (2026-06-05), simulateScore picks the argmax outcome
		// deterministically — never samples an underdog upset. With FAVORITE_HOME
		// (home odds 1.3 / draw 5.0 / away 9.0 → ~75/15/9 implied probability),
		// home is the argmax outcome on every single seed. The scoreline still
		// varies per seed, but the winning direction does not.
		let homeWins = 0;
		let awayWins = 0;
		let draws = 0;
		const N = 1000;
		for (let i = 0; i < N; i++) {
			const { hs, as } = simulateScore(
				FAVORITE_HOME.home,
				FAVORITE_HOME.draw,
				FAVORITE_HOME.away,
				i
			);
			if (hs > as) homeWins++;
			else if (as > hs) awayWins++;
			else draws++;
		}
		expect(homeWins).toBe(N);
		expect(awayWins).toBe(0);
		expect(draws).toBe(0);
	});

	it('argmax outcome: heavy AWAY favorite wins 100% of seeds', () => {
		// Mirror case — away is the favourite. Confirms the argmax logic
		// orients correctly regardless of which side is heavier.
		const FAVORITE_AWAY = { home: 9.0, draw: 5.0, away: 1.3 };
		let awayWins = 0;
		for (let i = 0; i < 200; i++) {
			const { hs, as } = simulateScore(
				FAVORITE_AWAY.home,
				FAVORITE_AWAY.draw,
				FAVORITE_AWAY.away,
				i
			);
			if (as > hs) awayWins++;
		}
		expect(awayWins).toBe(200);
	});

	it('argmax outcome: draw favourite is picked when draw odds are shortest', () => {
		// Balanced book with shortest draw odds → draw is argmax. Confirms
		// draws aren't suppressed by the home/away tiebreak when draw genuinely
		// leads on probability.
		// Decimal odds chosen so 1/odds normalises to home<draw, away<draw.
		const DRAW_FAVOURITE = { home: 3.5, draw: 2.5, away: 3.5 };
		let draws = 0;
		for (let i = 0; i < 200; i++) {
			const { hs, as } = simulateScore(
				DRAW_FAVOURITE.home,
				DRAW_FAVOURITE.draw,
				DRAW_FAVOURITE.away,
				i
			);
			if (hs === as) draws++;
		}
		expect(draws).toBe(200);
	});

	it('clamps scores to MAX_GOALS = 15 (defensive — tables max at 5)', () => {
		for (let i = 0; i < 200; i++) {
			const { hs, as } = simulateScore(2.0, 3.5, 4.0, i);
			expect(hs).toBeLessThanOrEqual(15);
			expect(as).toBeLessThanOrEqual(15);
			expect(hs).toBeGreaterThanOrEqual(0);
			expect(as).toBeGreaterThanOrEqual(0);
		}
	});
});
