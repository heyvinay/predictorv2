import { describe, expect, it } from 'vitest';
import type { CommunityPredictionWithRank, RoundDef, ScoringRules } from '$lib/types/results';
import {
	isUpset,
	koFinalScore,
	koLoserSide,
	koWinnerSide,
	outcomeOf,
	outcomePayouts,
	poolRows,
	poolSplit,
	prevNextInRound,
	sideCallers,
	spreadGrid
} from './matchDetailV4';

function score(partial: Partial<{
	home_score: number;
	away_score: number;
	home_score_et: number | null;
	away_score_et: number | null;
	home_penalties: number | null;
	away_penalties: number | null;
}>) {
	return {
		home_score: 0,
		away_score: 0,
		home_score_et: null,
		away_score_et: null,
		home_penalties: null,
		away_penalties: null,
		...partial
	};
}

describe('koLoserSide / koWinnerSide', () => {
	it('regulation-decided KO: loser is the side with fewer 90-min goals', () => {
		expect(koLoserSide(score({ home_score: 0, away_score: 1 }))).toBe('home');
		expect(koWinnerSide(score({ home_score: 0, away_score: 1 }))).toBe('away');
	});

	it('ET-decided KO: cumulative-after-ET takes priority over regulation draw', () => {
		const s = score({ home_score: 1, away_score: 1, home_score_et: 2, away_score_et: 1 });
		expect(koLoserSide(s)).toBe('away');
		expect(koWinnerSide(s)).toBe('home');
	});

	it('pens-decided KO: penalty legs override a level ET cumulative', () => {
		// Germany 1-1 Paraguay (1-1 AET) — Paraguay wins pens 4-3.
		const s = score({
			home_score: 1,
			away_score: 1,
			home_score_et: 1,
			away_score_et: 1,
			home_penalties: 3,
			away_penalties: 4
		});
		expect(koLoserSide(s)).toBe('home');
		expect(koWinnerSide(s)).toBe('away');
	});

	it('returns null for a fully level scoreline (no result yet)', () => {
		expect(koLoserSide(score({ home_score: 1, away_score: 1 }))).toBeNull();
		expect(koWinnerSide(score({ home_score: 1, away_score: 1 }))).toBeNull();
	});

	it('returns null when score is missing entirely', () => {
		expect(koLoserSide(null)).toBeNull();
		expect(koWinnerSide(undefined)).toBeNull();
	});

	it('ignores penalty legs that are tied (treats them as unresolved)', () => {
		// Falls through to ET cumulative (also level) and then regulation.
		const s = score({
			home_score: 1,
			away_score: 1,
			home_score_et: 1,
			away_score_et: 1,
			home_penalties: 4,
			away_penalties: 4
		});
		expect(koLoserSide(s)).toBeNull();
	});
});

describe('koFinalScore', () => {
	it('returns regulation score when no ET split exists', () => {
		expect(koFinalScore(score({ home_score: 2, away_score: 2 }))).toEqual({ home: 2, away: 2 });
	});

	it('returns the AET score when the match went to extra time', () => {
		// Belgium 2-2 Senegal (regulation), Belgium win 3-2 after extra time.
		const s = score({ home_score: 2, away_score: 2, home_score_et: 3, away_score_et: 2 });
		expect(koFinalScore(s)).toEqual({ home: 3, away: 2 });
	});

	it('returns the ET score (equal to regulation) for a pens-decided match', () => {
		// Germany 1-1 Paraguay (1-1 AET) — Paraguay wins on penalties.
		const s = score({
			home_score: 1,
			away_score: 1,
			home_score_et: 1,
			away_score_et: 1,
			home_penalties: 3,
			away_penalties: 4
		});
		expect(koFinalScore(s)).toEqual({ home: 1, away: 1 });
	});

	it('returns null when score is missing entirely', () => {
		expect(koFinalScore(null)).toBeNull();
		expect(koFinalScore(undefined)).toBeNull();
	});
});

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

function pred(
	h: number,
	a: number,
	reference = `REF-${h}-${a}-${Math.floor(Math.random() * 1e6)}`,
	rank: number | null = null
): CommunityPredictionWithRank {
	return {
		user_name: `U${reference}`,
		entry_reference: reference,
		entry_name: `E${reference}`,
		home_score: h,
		away_score: a,
		rank
	};
}

describe('outcomeOf / poolSplit', () => {
	it('classifies 1/X/2 and splits the pool', () => {
		expect(outcomeOf(2, 1)).toBe('1');
		expect(outcomeOf(0, 0)).toBe('X');
		expect(outcomeOf(0, 3)).toBe('2');
		const { counts, pcts } = poolSplit([pred(2, 1), pred(1, 0), pred(1, 1), pred(0, 2)]);
		expect(counts).toEqual({ home: 2, draw: 1, away: 1 });
		expect(pcts).toEqual({ home: 50, draw: 25, away: 25 });
	});
});

describe('spreadGrid', () => {
	it('counts picks per cell and clamps big scores into the 3+ bucket', () => {
		const grid = spreadGrid([pred(2, 1), pred(2, 1), pred(0, 0), pred(5, 1)]);
		expect(grid[2][1]).toBe(2);
		expect(grid[0][0]).toBe(1);
		expect(grid[3][1]).toBe(1); // 5-1 clamps to 3+,1
		expect(grid.flat().reduce((s, n) => s + n, 0)).toBe(4);
	});
});

describe('poolRows', () => {
	it('assigns status + parity-engine points and splits banked/missed', () => {
		// 4-entry pool, actual 2-1 (home win). Two correct outcomes → f=0.5
		// → consensus → no rarity. Exact = 5+10, result = 5, miss = 0.
		const preds = [
			pred(2, 1, 'EXACT', 3),
			pred(1, 0, 'RESULT', 1),
			pred(0, 0, 'MISS-X', 2),
			pred(0, 2, 'MISS-2', 4)
		];
		const { banked, missed } = poolRows(preds, { home: 2, away: 1 }, RULES, 'EXACT');
		expect(banked.map((r) => r.reference)).toEqual(['EXACT', 'RESULT']);
		expect(banked[0]).toMatchObject({ status: 'exact', pts: 15, you: true });
		expect(banked[1]).toMatchObject({ status: 'result', pts: 5, you: false });
		expect(missed.map((r) => r.reference)).toEqual(['MISS-X', 'MISS-2']); // rank order
		expect(missed[0].pts).toBe(0);
	});
});

describe('outcomePayouts', () => {
	it('templates base from rules and adds share-driven rarity', () => {
		// 10 entries: 8 home, 1 draw, 1 away.
		const preds = [
			...Array.from({ length: 8 }, (_, i) => pred(1, 0, `H${i}`)),
			pred(1, 1, 'D0'),
			pred(0, 1, 'A0')
		];
		const p = outcomePayouts(preds, RULES);
		expect(p.home.base).toBe(5);
		expect(p.home.rarity).toBe(0); // 80% share → consensus
		expect(p.home.band).toBe('common');
		expect(p.draw.count).toBe(1);
		expect(p.draw.rarity).toBeGreaterThan(0); // 10% share → premium
		expect(p.draw.band).toBe('solo'); // single caller
		expect(p.draw.total).toBe(5 + p.draw.rarity);
	});

	it('pays no rarity and nulls the band while rarity is paused (mode fixed)', () => {
		// Same pool as above — the 10%-share draw earned rarity under
		// logarithmic; under "fixed" the preview must not promise it.
		const preds = [
			...Array.from({ length: 8 }, (_, i) => pred(1, 0, `H${i}`)),
			pred(1, 1, 'D0'),
			pred(0, 1, 'A0')
		];
		const p = outcomePayouts(preds, { ...RULES, mode: 'fixed' });
		for (const side of ['home', 'draw', 'away'] as const) {
			expect(p[side].rarity).toBe(0);
			expect(p[side].total).toBe(p[side].base);
			expect(p[side].band).toBeNull();
		}
		// Counts/shares still flow — the split bar stays informative.
		expect(p.home.count).toBe(8);
		expect(p.home.pct).toBeGreaterThan(0);
	});
});

describe('isUpset (C.3 heuristic)', () => {
	const mostlyHome = (n: number, winners: number) => [
		...Array.from({ length: winners }, (_, i) => pred(0, 1, `W${i}`)),
		...Array.from({ length: n - winners }, (_, i) => pred(1, 0, `L${i}`))
	];

	it('fires below 30% winner share with pool >= 10', () => {
		expect(isUpset(mostlyHome(10, 2), '2')).toBe(true); // 20%
	});
	it('does not fire at >= 30% share', () => {
		expect(isUpset(mostlyHome(10, 3), '2')).toBe(false); // exactly 30%
	});
	it('does not fire in tiny pools', () => {
		expect(isUpset(mostlyHome(9, 1), '2')).toBe(false);
	});
});

describe('sideCallers', () => {
	it('counts callers of a given side', () => {
		const preds = [pred(2, 1), pred(3, 0), pred(1, 1)];
		expect(sideCallers(preds, 'home')).toBe(2);
		expect(sideCallers(preds, 'draw')).toBe(1);
		expect(sideCallers(preds, 'away')).toBe(0);
	});
});

describe('prevNextInRound', () => {
	const rounds: RoundDef[] = [
		{ id: 'summary', label: 'Summary', dates: '', isKnockout: false, fixtureIds: [] },
		{ id: 'r1', label: 'Round 1', dates: '', isKnockout: false, fixtureIds: ['a', 'b', 'c'] }
	];

	it('locates a fixture with neighbours', () => {
		expect(prevNextInRound(rounds, 'b')).toEqual({
			roundId: 'r1',
			label: 'Round 1',
			index: 1,
			count: 3,
			prevId: 'a',
			nextId: 'c'
		});
	});
	it('nulls at the edges and for unknown ids', () => {
		expect(prevNextInRound(rounds, 'a')?.prevId).toBeNull();
		expect(prevNextInRound(rounds, 'c')?.nextId).toBeNull();
		expect(prevNextInRound(rounds, 'zz')).toBeNull();
	});
});
